"""Photo entries: a register page, bill or payment screenshot -> khata rows.

    photo -> OCR (Google Vision, image only) -> LLM (OCR text only) -> rows
          -> code checks every row -> preview -> "haan" -> save the complete rows
          -> then ask about the missing parts, one question at a time

Nothing is saved before the user says haan. Each amount must be written in the
photo's text. New names are asked once for all ("1) Sab customer 2) Sab supplier
3) Chhor do"). Rows of categories without a saver yet (expense, sale, ...) are
shown but not saved; see app/services/image_rows.py.
"""

from datetime import date
from decimal import Decimal

from psycopg import Connection

from app.ai.extractor import extract_rows
from app.ai.llm import AIError
from app.core.config import get_settings
from app.core.database import transaction
from app.core.dates import now, short_date
from app.handlers.party import balance_line, new_draft, next_step
from app.schemas.khata import ExtractedRow, PendingAction
from app.services.amounts import confirmed_amount, format_rs
from app.services.answers import parse_number, parse_yes_no
from app.services.image_rows import ROW_SAVERS, RowSaver
from app.services.ocr import OCRError, read_text
from app.services.registry import Context, Outcome, chain, pending_resolver
from app.services.replies import numbered, t
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

    try:
        extraction = extract_rows(ocr.text, now(ctx.business["timezone"]), ocr.layout)
    except AIError:
        return Outcome("read_image", t("ocr_failed", language))

    source = f"{ocr.text}\n{ocr.layout}"  # amounts are checked against what the photo says
    rows = [r for r in extraction.rows if r.category != "other"][: get_settings().ocr_max_rows]
    items = [ROW_SAVERS[r.category].prepare(ctx, r, source) for r in rows if r.category in ROW_SAVERS]
    later = [r for r in rows if r.category not in ROW_SAVERS]
    if not items and not later:
        return Outcome("read_image", t("image_nothing_found", language))

    # Group rows by category (a heading per category); number them in that order
    order = list(dict.fromkeys(i["category"] for i in items))
    items = sorted(items, key=lambda i: order.index(i["category"]))
    lines = [t("image_found", language, n=len(items) + len(later))]
    for n, item in enumerate(items, 1):
        if n == 1 or item["category"] != items[n - 2]["category"]:
            lines.append(t(ROW_SAVERS[item["category"]].section, language))
        lines.append(f"{'❓ ' if not item['ready'] else ''}{n}) {item['line']}")
    if later:
        lines.append(t("image_section_later", language))
        lines += [f"• {_later_line(language, r, source)}" for r in later]
    warning = _total_warning(language, extraction.written_total, rows, source)
    if warning:
        lines.append(warning)

    if not items:  # only rows we cannot save yet: nothing to confirm
        return Outcome("read_image", "\n".join(lines))

    new_names = list({i["name"].lower(): i["name"] for i in items if i.get("is_new")}.values())
    lines.append(t("image_confirm", language))
    pending = PendingAction(
        kind="confirm_image", language=language, expects="yes_no", data={"items": items, "new_names": new_names}
    )
    return Outcome("read_image", "\n".join(lines), pending=pending)


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


# ---------------------------------------------------------------------------
# Confirm -> (new names) -> save -> ask about missing parts
# ---------------------------------------------------------------------------


@pending_resolver("confirm_image")
def resolve_confirm_image(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("read_image", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("read_image", t("image_cancelled", ctx.language))
    items, new_names = pending.data["items"], pending.data["new_names"]
    if new_names:
        question = t("image_new_names", ctx.language, names=", ".join(new_names))
        ask = PendingAction(kind="image_new_parties", language=ctx.language, expects="choice", data=pending.data)
        return Outcome("read_image", question, pending=ask)
    return _save_items(ctx, items, new_type=None)


@pending_resolver("image_new_parties")
def resolve_image_new_parties(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    choice = parse_number(answer)
    items = pending.data["items"]
    if choice == 1:
        return _save_items(ctx, items, new_type="customer")
    if choice == 2:
        return _save_items(ctx, items, new_type="supplier")
    if choice == 3:  # skip every row with a new name
        return _save_items(ctx, [i for i in items if not i.get("is_new")], new_type=None)
    question = t("image_new_names", ctx.language, names=", ".join(pending.data["new_names"]))
    return Outcome("read_image", question, pending=pending)


def _save_items(ctx: Context, items: list[dict], new_type: str | None) -> Outcome:
    ready = [i for i in items if i["ready"]]
    missing = [i for i in items if not i["ready"]]
    if not ready and not missing:
        return Outcome("read_image", t("image_cancelled", ctx.language))

    saved = None
    if ready:
        def commit(conn: Connection) -> str:
            state: dict = {"new_type": new_type}
            for line, item in enumerate(ready):  # source_line keeps each row unique for this message
                ROW_SAVERS[item["category"]].save(conn, ctx, item, line, state)
            reply = [t("image_saved", ctx.language, n=len(ready))]
            for category in dict.fromkeys(i["category"] for i in ready):
                reply += ROW_SAVERS[category].summary(conn, ctx, state)
            return "\n".join(reply)

        saved = Outcome("read_image", commit=commit)

    drafts = [
        ROW_SAVERS[i["category"]].follow_up(ctx, i, {"new_type": new_type})
        for i in missing
        if ROW_SAVERS[i["category"]].follow_up
    ]
    if not drafts:
        return saved or Outcome("read_image", t("image_cancelled", ctx.language))
    question = next_step(ctx, dict(drafts[0], queue=drafts[1:]))  # asks the first missing part
    return chain(saved, question) if saved else question


# ---------------------------------------------------------------------------
# Party rows (Feature 1)
# ---------------------------------------------------------------------------


def _party_prepare(ctx: Context, row: ExtractedRow, source: str) -> dict:
    today = now(ctx.business["timezone"]).date()
    amount = confirmed_amount(source, row.amount)
    entry_date = row.date if row.date and row.date <= today else today
    item = {
        "category": "party_entry",
        "name": row.party_name,
        "direction": row.direction,
        "amount": str(amount) if amount is not None else None,
        "date": entry_date.isoformat(),
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
        message_id=ctx.message_id,
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
    )


ROW_SAVERS["party_entry"] = RowSaver(
    section="image_section_party",
    prepare=_party_prepare,
    save=_party_save,
    summary=_party_summary,
    follow_up=_party_follow_up,
)

