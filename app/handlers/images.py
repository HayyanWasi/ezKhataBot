"""Photo entries: a register page, bill or payment screenshot -> khata and cash book rows.

    photo -> OCR (Google Vision, image only) -> LLM (OCR text only) -> rows
          -> code checks every row -> preview -> "haan" -> save the complete rows
          -> then ask about the missing parts, one question at a time

Nothing is saved before the user says haan. Each amount must be written in the
photo's text. New names are asked once for all ("1) Sab customer 2) Sab supplier
3) Chhor do"). Every row is saved against the PHOTO's message (source_line = the
row number), so the photo stays with the entry as proof and can't be saved twice.
Which categories can be saved is in app/services/image_rows.py.
"""

from datetime import date
from decimal import Decimal

from psycopg import Connection

from app.ai.extractor import extract_rows
from app.ai.llm import AIError
from app.core.config import get_settings
from app.core.database import transaction
from app.core.dates import now, short_date
from app.handlers.cash import new_cash_draft
from app.handlers.money_steps import money_line
from app.handlers.party import balance_line, new_draft
from app.schemas.khata import ExtractedRow, PendingAction
from app.services.amounts import confirmed_amount, format_rs, parse_amount_answer
from app.services.answers import is_skip, parse_number, parse_yes_no
from app.services.image_rows import ROW_SAVERS, RowSaver
from app.services.ocr import OCRError, read_text
from app.services.registry import Context, Outcome, chain, continue_draft, intent, pending_resolver
from app.services.replies import t
from app.tools import money as money_tools
from app.tools import party as party_tools

_OCR_ERRORS = {"off": "ocr_unavailable", "too_big": "ocr_too_big"}


# ---------------------------------------------------------------------------
# Read the photo -> preview
# ---------------------------------------------------------------------------


def read_image(ctx: Context) -> Outcome:
    language = ctx.language
    try:
        ocr = read_text(ctx.image_path)
    except OCRError as e:
        return Outcome("read_image", t(_OCR_ERRORS.get(e.reason, "ocr_failed"), language))
    if not ocr.text.strip():
        return Outcome("read_image", t("image_nothing_found", language))

    return preview_rows(ctx, ocr.text, ocr.layout)


def preview_rows(ctx: Context, text: str, layout: str | None = None, from_message: bool = False) -> Outcome:
    """Rows in a photo's text (or in a typed message with several entries) -> preview + "haan/nahi"."""
    language = ctx.language
    try:
        extraction = extract_rows(text, now(ctx.business["timezone"]), layout, from_message=from_message)
    except AIError:
        return Outcome("read_image", t("ocr_failed", language))

    source = f"{text}\n{layout or ''}"  # amounts are checked against what the photo / message says
    rows = [r for r in extraction.rows if r.category != "other"][: get_settings().ocr_max_rows]
    if from_message:
        rows = [_owed_direction(r, text) for r in rows]
    items = [ROW_SAVERS[r.category].prepare(ctx, r, source) for r in rows if r.category in ROW_SAVERS]
    later = [r for r in rows if r.category not in ROW_SAVERS]
    if not items and not later:
        return Outcome("read_image", t("image_nothing_found", language))

    # Group rows by section (a heading per section); number them in that order
    order = list(dict.fromkeys(ROW_SAVERS[i["category"]].section for i in items))
    items = sorted(items, key=lambda i: order.index(ROW_SAVERS[i["category"]].section))
    lines = [t("message_found" if from_message else "image_found", language, n=len(items) + len(later))]
    for n, item in enumerate(items, 1):
        item["row"] = n  # saved as source_line: unique per row of this photo
        section = ROW_SAVERS[item["category"]].section
        if n == 1 or section != ROW_SAVERS[items[n - 2]["category"]].section:
            lines.append(t(section, language))
        lines.append(f"{'❓ ' if not item['ready'] else ''}{n}) {item['line']}")
    if later:
        lines.append(t("image_section_later", language))
        lines += [f"• {_later_line(language, r, source)}" for r in later]
    warning = _total_warning(language, extraction.written_total, rows, source) or _bill_warning(
        language, extraction, rows, source
    )
    if warning:
        lines.append(warning)

    if not items:  # only rows we cannot save: nothing to confirm
        return Outcome("read_image", "\n".join(lines))

    new_names = list({i["name"].lower(): i["name"] for i in items if i.get("is_new")}.values())
    lines.append(t("image_confirm", language))
    data = {"items": items, "new_names": new_names, "photo_message_id": str(ctx.message_id)}
    pending = PendingAction(kind="confirm_image", language=language, expects="yes_no", data=data)
    return Outcome("read_image", "\n".join(lines), pending=pending)


@intent(
    "many_entries",
    "TWO OR MORE separate MONEY entries in one message (khata, expenses, cash), often one per line: \"Abbas se"
    " 500 lene hain / Hayyan ko 100 diye / chai 50\". Not with stock items or sales (use \"then\"). Never one "
    "entry.",
    fields_hint="{}",
    examples=["Ali ko 500 diye, Bilal se 300 mile, chai 100", "Abbas se 500 lene hain\nShahrukh ko 200 dene hain"],
    needs_business=True,
    owner_only=True,
)
def many_entries(ctx: Context, fields) -> Outcome:
    return preview_rows(ctx, ctx.text, from_message=True)


_WILL_GET = ("lene hain", "lene hai", "lena hai", "lene he", "lainay", "lene", "لینے")  # the party owes the shop
_WILL_GIVE = ("dene hain", "dene hai", "dena hai", "dene he", "dainay", "dene", "دینے")  # the shop owes the party


def _owed_direction(row: ExtractedRow, text: str) -> ExtractedRow:
    """'Abbas se 500 lene hain' = the shop will get (gave); 'Shahrukh ko 500 dene hain' = the shop owes (got).
    Decided from the row's own line in code: the AI mixes up 'se ... lene' with 'se liye'."""
    if row.category != "party_entry" or not row.party_name:
        return row
    line = next((l.lower() for l in text.splitlines() if row.party_name.lower() in l.lower()), "")
    if any(w in line for w in _WILL_GET):
        return row.model_copy(update={"direction": "gave"})
    if any(w in line for w in _WILL_GIVE):
        return row.model_copy(update={"direction": "got"})
    return row


def _later_line(language: str, row: ExtractedRow, source: str) -> str:
    amount = confirmed_amount(source, row.amount)
    label = t(f"cat_{row.category}", language)
    detail = row.note or row.party_name
    if detail and detail.lower() == label.lower():  # "Counter sale · counter sale"
        detail = None
    parts = [label, detail, format_rs(amount) if amount else None]
    return " · ".join(p for p in parts if p)


def _total_warning(language: str, written_total, rows: list[ExtractedRow], source: str) -> str | None:
    """A total written on the sheet that doesn't match the rows hints at a misread."""
    written = confirmed_amount(source, written_total)
    if written is None:
        return None
    amounts = [confirmed_amount(source, r.amount) for r in rows]
    total = sum((a for a in amounts if a is not None), Decimal(0))
    if total == written:
        return None
    return t("image_total_mismatch", language, written=format_rs(written), sum=format_rs(total))


def _bill_warning(language: str, extraction, rows: list[ExtractedRow], source: str) -> str | None:
    """A bill is saved as its total: if its item lines don't add up to it, a number was probably misread."""
    if extraction.kind != "bill" or len(rows) != 1 or not extraction.item_amounts:
        return None
    total = confirmed_amount(source, rows[0].amount)
    items = [confirmed_amount(source, a) for a in extraction.item_amounts]
    if total is None or None in items:
        return None
    items_sum = sum(items, Decimal(0))
    if items_sum == total:
        return None
    return t("image_bill_mismatch", language, total=format_rs(total), sum=format_rs(items_sum))


def _row_date(ctx: Context, row: ExtractedRow) -> str:
    today = now(ctx.business["timezone"]).date()
    return (row.date if row.date and row.date <= today else today).isoformat()


# ---------------------------------------------------------------------------
# Confirm -> (new names) -> (opening cash) -> save -> ask about missing parts
# ---------------------------------------------------------------------------


@pending_resolver("confirm_image")
def resolve_confirm_image(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("read_image", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("read_image", t("image_cancelled", ctx.language))
    if pending.data["new_names"]:
        question = t("image_new_names", ctx.language, names=", ".join(pending.data["new_names"]))
        ask = PendingAction(kind="image_new_parties", language=ctx.language, expects="choice", data=pending.data)
        return Outcome("read_image", question, pending=ask)
    return _save_items(ctx, {**pending.data, "new_type": None})


@pending_resolver("image_new_parties")
def resolve_image_new_parties(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    choice = parse_number(answer)
    data = pending.data
    if choice == 1:
        return _save_items(ctx, {**data, "new_type": "customer"})
    if choice == 2:
        return _save_items(ctx, {**data, "new_type": "supplier"})
    if choice == 3:  # skip every row with a new name
        return _save_items(ctx, {**data, "new_type": None, "items": [i for i in data["items"] if not i.get("is_new")]})
    question = t("image_new_names", ctx.language, names=", ".join(data["new_names"]))
    return Outcome("read_image", question, pending=pending)


@pending_resolver("image_opening_cash")
def resolve_image_opening_cash(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    amount = parse_amount_answer(answer)
    if amount is None and not (answer.strip() == "0" or is_skip(answer)):
        return Outcome("read_image", t("ask_opening_cash", ctx.language), pending=pending)
    return _save_items(ctx, {**pending.data, "opening_cash": str(amount) if amount is not None else "0"})


def _save_items(ctx: Context, data: dict) -> Outcome:
    """data: items, new_type, photo_message_id, and opening_cash once asked."""
    items = data["items"]
    ready = [i for i in items if i["ready"]]
    missing = [i for i in items if not i["ready"]]
    if not ready and not missing:
        return Outcome("read_image", t("image_cancelled", ctx.language))

    # Cash rows need the shop's opening cash the first time (asked once, before saving)
    if data.get("opening_cash") is None and any(i["ready"] and i.get("via") == "cash" for i in items):
        with transaction() as conn:
            has_cash = money_tools.get_cash_account(conn, ctx.business["id"]) is not None
        if not has_cash:
            ask = PendingAction(kind="image_opening_cash", language=ctx.language, expects="amount_or_skip", data=data)
            return Outcome("read_image", t("ask_opening_cash", ctx.language), pending=ask)

    state = {
        "new_type": data.get("new_type"),
        "photo_message_id": data.get("photo_message_id") or str(ctx.message_id),
        "opening_cash": data.get("opening_cash"),
    }
    saved = None
    if ready:
        def commit(conn: Connection) -> str:
            for n, item in enumerate(ready):
                ROW_SAVERS[item["category"]].save(conn, ctx, item, item.get("row", n), state)
            reply = [t("image_saved", ctx.language, n=len(ready))]
            summaries = dict.fromkeys(ROW_SAVERS[i["category"]].summary for i in ready)  # once each
            for summary in summaries:
                reply += summary(conn, ctx, state)
            return "\n".join(reply)

        saved = Outcome("read_image", commit=commit)

    drafts = [
        ROW_SAVERS[i["category"]].follow_up(ctx, i, state)
        for i in missing
        if ROW_SAVERS[i["category"]].follow_up
    ]
    if not drafts:
        return saved or Outcome("read_image", t("image_cancelled", ctx.language))
    question = continue_draft(ctx, dict(drafts[0], queue=drafts[1:]))  # asks the first missing part
    return chain(saved, question) if saved else question


# ---------------------------------------------------------------------------
# Party rows (Feature 1)
# ---------------------------------------------------------------------------


def _party_prepare(ctx: Context, row: ExtractedRow, source: str) -> dict:
    amount = confirmed_amount(source, row.amount)
    item = {
        "category": "party_entry",
        "name": row.party_name,
        "direction": row.direction,
        "amount": str(amount) if amount is not None else None,
        "date": _row_date(ctx, row),
        "note": row.note,
        "account_id": None,
        "is_new": False,
        "several": False,  # the name matches more than one party
    }
    if row.party_name:
        with transaction() as conn:
            matches = party_tools.find_parties(conn, ctx.business["id"], row.party_name)
        if len(matches) == 1:
            item["account_id"], item["name"] = str(matches[0]["id"]), matches[0]["name"]
        elif matches:
            item["several"] = True
        else:
            item["is_new"] = True
    item["ready"] = bool(item["name"] and item["amount"] and item["direction"] and not item["several"])
    item["line"] = _party_line(ctx.language, item)
    return item


def _party_line(language: str, item: dict) -> str:
    day = short_date(date.fromisoformat(item["date"]))
    amount = format_rs(Decimal(item["amount"])) if item["amount"] else None
    if item["ready"]:
        key = "image_row_gave" if item["direction"] == "gave" else "image_row_got"
        line = t(key, language, date=day, name=item["name"], amount=amount)
        return f"{line} {t('image_new', language)}" if item["is_new"] else line
    if not item["name"]:
        problem = t("image_missing_party", language)
    elif item["several"]:
        problem = t("image_missing_choice", language, name=item["name"])
    elif not amount:
        problem = t("image_missing_amount", language)
    else:
        problem = t("image_missing_direction", language)
    parts = [item["name"] or "?", amount, f"{problem} ({t('image_ask_later', language)})"]
    return " · ".join(p for p in parts if p)


def _party_save(conn: Connection, ctx: Context, item: dict, line: int, state: dict) -> None:
    business_id, user_id = ctx.business["id"], ctx.user["id"]
    created = state.setdefault("created", {})  # new names created in this photo: lower(name) -> id
    touched = state.setdefault("touched", {})  # account id -> name, for the balance lines
    account_id = item["account_id"]
    if account_id is None:
        key = item["name"].lower()
        if key not in created:
            created[key] = party_tools.create_party(
                conn, business_id, state["new_type"], item["name"], None, user_id
            )["id"]
        account_id = created[key]
    party_tools.record_entry(
        conn,
        business_id=business_id,
        account_id=account_id,
        direction=item["direction"],
        amount=Decimal(item["amount"]),
        entry_date=date.fromisoformat(item["date"]),
        note=item["note"],
        message_id=state["photo_message_id"],
        user_id=user_id,
        source_line=line,
    )
    touched[str(account_id)] = item["name"]


def _party_summary(conn: Connection, ctx: Context, state: dict) -> list[str]:
    return [
        balance_line(ctx.language, name, party_tools.get_balance(conn, ctx.business["id"], account_id))
        for account_id, name in state.get("touched", {}).items()
    ]


def _party_follow_up(ctx: Context, item: dict, state: dict) -> dict:
    """An entry draft for a row with something missing; Feature 1's questions fill it in."""
    return new_draft(
        "entry",
        party_name=item["name"],
        direction=item["direction"],
        amount=item["amount"],
        date=item["date"],
        note=item["note"],
        new_type=state["new_type"] if item.get("is_new") else None,
        source_message_id=state["photo_message_id"],
        source_line=item.get("row", 0),
    )


ROW_SAVERS["party_entry"] = RowSaver(
    section="image_section_party",
    prepare=_party_prepare,
    save=_party_save,
    summary=_party_summary,
    follow_up=_party_follow_up,
)


# ---------------------------------------------------------------------------
# Cash book rows (Feature 2): expense, cash in / out, sale, bank
# ---------------------------------------------------------------------------


def _cash_prepare(ctx: Context, row: ExtractedRow, source: str) -> dict:
    category = row.category
    if category == "bank":  # the shop's own bank: got = money came in, gave = went out
        direction = {"got": "in", "gave": "out"}.get(row.direction)
    else:
        direction = "out" if category in ("expense", "cash_out") else "in"
    amount = confirmed_amount(source, row.amount)
    item = {
        "category": category,
        "direction": direction,
        "amount": str(amount) if amount is not None else None,
        "date": _row_date(ctx, row),
        "note": row.note,
        "word": row.note if category == "expense" else None,  # "bijli" -> the shop's category
        "sale": category == "sale",
        "via": "bank" if category == "bank" else "cash",
        "bank_name": row.bank_name,
        "money_account_id": None,
        "category_id": None,
        "category_name": None,
    }
    with transaction() as conn:
        if item["via"] == "bank":
            banks = money_tools.find_banks(conn, ctx.business["id"], row.bank_name)
            if len(banks) == 1:
                item["money_account_id"], item["bank_name"] = str(banks[0]["id"]), banks[0]["name"]
        if item["word"]:
            known = money_tools.category_for_word(conn, ctx.business["id"], item["word"])
            if known:
                item["category_id"], item["category_name"] = str(known["id"]), known["name"]
    item["ready"] = bool(
        item["amount"] and item["direction"]
        and (item["via"] == "cash" or item["money_account_id"])
        and (not item["word"] or item["category_id"])
    )
    item["line"] = _cash_line(ctx.language, item)
    return item


def _cash_line(language: str, item: dict) -> str:
    day = short_date(date.fromisoformat(item["date"]))
    label = t(f"cat_{item['category']}", language)
    detail = item["category_name"] or item["bank_name"] or item["note"]
    if detail and detail.lower() == label.lower():
        detail = None
    amount = format_rs(Decimal(item["amount"])) if item["amount"] else None
    parts = [day, label, detail, amount]
    if not item["ready"]:
        if not amount:
            problem = t("image_missing_amount", language)
        elif not item["direction"]:
            problem = t("image_missing_in_out", language)
        elif item["via"] == "bank" and not item["money_account_id"]:
            problem = t("image_missing_bank", language)
        else:
            problem = t("image_missing_category", language)
        parts.append(f"{problem} ({t('image_ask_later', language)})")
    return " · ".join(p for p in parts if p)


def _cash_save(conn: Connection, ctx: Context, item: dict, line: int, state: dict) -> None:
    business_id, user_id = ctx.business["id"], ctx.user["id"]
    entry_date, amount = date.fromisoformat(item["date"]), Decimal(item["amount"])
    if item["via"] == "bank":
        account = (item["money_account_id"], item["bank_name"], "bank")
    else:
        opening = Decimal(state["opening_cash"]) if state.get("opening_cash") else None
        cash_id = money_tools.ensure_cash_account(conn, business_id, user_id, opening, entry_date)
        account = (cash_id, money_tools.CASH_NAME, "cash")
    came_in = item["direction"] == "in"
    money_tools.record_transaction(
        conn,
        business_id=business_id,
        type="sale" if item["sale"] else ("cash_in" if came_in else "cash_out"),
        entry_date=entry_date,
        legs=[(account[0], amount if came_in else -amount)],
        note=item["note"],
        message_id=state["photo_message_id"],
        user_id=user_id,
        category_id=item["category_id"],
        source_line=line,
    )
    state.setdefault("money", {})[str(account[0])] = account


def _cash_summary(conn: Connection, ctx: Context, state: dict) -> list[str]:
    return [
        money_line(ctx.language, name, kind, money_tools.get_balance(conn, ctx.business["id"], account_id))
        for account_id, name, kind in state.get("money", {}).values()
    ]


def _cash_follow_up(ctx: Context, item: dict, state: dict) -> dict:
    """A cash draft for a row with something missing; the cash book's questions fill it in."""
    return new_cash_draft(
        direction=item["direction"],
        amount=item["amount"],
        date=item["date"],
        note=item["note"],
        sale=item["sale"],
        category_word=item["word"],
        category_id=item["category_id"],
        category_name=item["category_name"],
        via=item["via"],
        bank_name=item["bank_name"],
        money_account_id=item["money_account_id"],
        opening_cash=state.get("opening_cash"),
        source_message_id=state["photo_message_id"],
        source_line=item.get("row", 0),
    )


for _category in ("expense", "cash_in", "cash_out", "sale"):
    ROW_SAVERS[_category] = RowSaver(
        section="image_section_cash", prepare=_cash_prepare, save=_cash_save, summary=_cash_summary,
        follow_up=_cash_follow_up,
    )
ROW_SAVERS["bank"] = RowSaver(
    section="image_section_bank", prepare=_cash_prepare, save=_cash_save, summary=_cash_summary,
    follow_up=_cash_follow_up,
)
