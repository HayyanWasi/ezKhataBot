"""Cash book intents: money in / out, expenses, cash sales, banks, transfers, reports.

The AI only picks one of these intents and fills its fields. Everything else is
code: amounts are checked against the user's own text, banks and expense
categories are matched against the shop's own lists, and all data access goes
through app/tools/money.py.

A cash entry is a "draft" like a party entry: next_step() asks the ONE missing
thing (amount -> in or out -> which bank -> opening cash -> category) or saves it.

Staff can add cash entries (in, out, expense, sale). Banks and transfers are owner only.
"""

from datetime import date
from decimal import Decimal

from psycopg import Connection

from app.core.database import transaction
from app.core.dates import short_date, today
from app.handlers.money_steps import (
    MONEY_KEYS,
    cash_account,
    check_step,
    following_draft,
    money_account,
    money_line,
    money_step,
)
from app.schemas.khata import (
    AddBankFields,
    CashEntryFields,
    MoneyReportFields,
    PendingAction,
    TransferFields,
)
from app.services import pdf
from app.services.amounts import confirmed_amount, format_rs, parse_amount_answer, parse_amounts
from app.services.answers import parse_number, pick
from app.services.registry import (
    DRAFT_STEPS,
    Context,
    Outcome,
    ask_draft,
    chain,
    continue_draft,
    intent,
    pending_resolver,
)
from app.services.replies import numbered, t
from app.tools import money as tools


def _today(ctx: Context) -> date:
    return today(ctx.business["timezone"])


def _entry_date(ctx: Context, value: date | None) -> date | None:
    """The entry's date (today if not said), or None if it is in the future."""
    day = value or _today(ctx)
    return None if day > _today(ctx) else day


def new_cash_draft(**values) -> dict:
    """Everything in a draft is JSON-safe: it is stored in the pending question."""
    draft = {
        "mode": "cash", "direction": None, "amount": None, "date": None, "note": None,
        "sale": False, "category_word": None, "category_id": None, "category_name": None,
        "new_category": None, "remember_word": False,
        "queue": [], "source_message_id": None, "source_line": 0,
        **MONEY_KEYS, "via": "cash",
    }
    draft.update(values)
    return draft


# ---------------------------------------------------------------------------
# Cash entry draft: ask what's missing, then save
# ---------------------------------------------------------------------------


def next_step(ctx: Context, draft: dict) -> Outcome:
    language = ctx.language
    if draft["amount"] is None:
        return ask_draft(ctx, "cash_amount", "amount", draft, t("ask_cash_amount", language))
    if draft["direction"] is None:
        question = t("ask_cash_direction", language, amount=format_rs(Decimal(draft["amount"])))
        return ask_draft(ctx, "cash_direction", "choice", draft, question)

    question = money_step(ctx, draft)  # which bank? opening cash?
    if question:
        return question

    word = draft["category_word"]
    if draft["direction"] == "out" and word and draft["category_id"] is None and draft["new_category"] is None:
        with transaction() as conn:
            known = tools.category_for_word(conn, ctx.business["id"], word)
            categories = tools.list_categories(conn, ctx.business["id"])
        if known:
            draft["category_id"], draft["category_name"] = str(known["id"]), known["name"]
        else:
            options = [{"id": None, "name": _title(word)}] + [{"id": str(c["id"]), "name": c["name"]} for c in categories]
            labels = [t("new_category_option", language, name=options[0]["name"])] + [c["name"] for c in categories]
            question = t("ask_category", language, word=word, options=numbered(labels))
            return ask_draft(ctx, "choose_category", "choice_or_name", draft, question, options=options)

    amount = Decimal(draft["amount"])
    signed = amount if draft["direction"] == "in" else -amount
    question = check_step(ctx, draft, ("cash_in", "cash_out", "sale"), signed)
    if question:  # a very large amount, or the same entry a minute ago
        return question

    saved = _save(ctx, draft)
    if draft.get("queue"):  # rows from a photo: save this one, then ask about the next
        return chain(saved, continue_draft(ctx, following_draft(draft)))
    return saved


def _title(word: str) -> str:
    word = word.strip()
    return word[:1].upper() + word[1:]


def _save(ctx: Context, draft: dict) -> Outcome:
    language = ctx.language
    business_id, user_id = ctx.business["id"], ctx.user["id"]

    def commit(conn: Connection) -> str:
        amount, entry_date = Decimal(draft["amount"]), date.fromisoformat(draft["date"])
        account_id, account_name, account_type = money_account(conn, ctx, draft, entry_date)

        category_id, category_name = draft["category_id"], draft["category_name"]
        if draft["new_category"]:
            category = tools.create_category(conn, business_id, draft["new_category"], user_id)
            category_id, category_name = category["id"], category["name"]
        if category_id and draft["category_word"] and (draft["new_category"] or draft["remember_word"]):
            tools.remember_word(conn, business_id, draft["category_word"], category_id)

        came_in = draft["direction"] == "in"
        kind = "sale" if draft["sale"] and came_in else ("cash_in" if came_in else "cash_out")
        tools.record_transaction(
            conn,
            business_id=business_id,
            type=kind,
            entry_date=entry_date,
            legs=[(account_id, amount if came_in else -amount)],
            note=draft["note"] or draft["category_word"],
            message_id=draft["source_message_id"] or ctx.message_id,
            user_id=user_id,
            category_id=category_id,
            source_line=draft["source_line"],
        )

        detail = f" · {category_name or draft['note']}" if (category_name or draft["note"]) else ""
        if kind == "sale":
            line = t("sale_saved", language, amount=format_rs(amount), date=short_date(entry_date))
        else:
            key = "money_in_saved" if came_in else "money_out_saved"
            line = t(key, language, amount=format_rs(amount), detail=detail, date=short_date(entry_date))
        balance = tools.get_balance(conn, business_id, account_id)
        return line + "\n" + money_line(language, account_name, account_type, balance)

    return Outcome("cash_entry", commit=commit)


# Words for moving money, never an expense category ("nikaal" -> no "Nikaal" category)
_NOT_A_CATEGORY = {
    "nikaal", "nikal", "nikale", "nikala", "nikali", "nikaale", "nikaala", "nikaali", "nikalna", "nikaalna",
    "gaye", "gae", "gaya", "gya", "diye", "diya", "di", "de", "liye", "liya", "aaye", "aae", "aaya", "aya", "mile",
    "mila", "out", "in", "cash", "paise", "paisa", "raqam", "kharcha", "kharch", "expense", "jama", "withdraw",
    "nikalwaye", "nikalwaya", "نکالے", "نکالا", "خرچہ",
}


@intent(
    "cash_entry",
    "Money INTO or OUT OF the shop's cash/bank with NO party khata: expenses (bijli, kiraya, chai, a worker's"
    " salary, transport), cash sales, cash in/out (\"500 gae\", \"cash out 500\", \"3000 aaye\", \"kharcha 200\"). "
    "direction: \"in\" (aaye, mile, sale, bikri) / \"out\" (gaye, nikale, kharcha, bill bhara, salary di) / null."
    " category_word: the expense word as written; a bare word + amount (\"rickshaw 300\") is \"out\" with that "
    "word. is_sale: a sale. bank_name: only if named. A correction of a saved entry is edit_entry; selling "
    "ITEMS with counts is create_bill.",
    fields=CashEntryFields,
    fields_hint=(
        '{"direction": "in" | "out" | null, "amount": number | null, "date": "YYYY-MM-DD" | null, '
        '"note": string | null, "category_word": string | null, "is_sale": true | false, '
        '"bank_name": string | null}'
    ),
    examples=[
        "500 gae aaj", "cash out 500", "3000 aaye", "bijli ka bill 3000", "chai 200", "aaj 20000 ki sale hui",
        "Ahmed ko salary 15000 di", "JazzCash mein 1000 aaye", "بجلی کا بل 3000",
    ],
    needs_business=True,
)
def cash_entry(ctx: Context, fields: CashEntryFields) -> Outcome:
    entry_date = _entry_date(ctx, fields.date)
    if entry_date is None:
        return Outcome("cash_entry", t("future_date", ctx.language))
    amount = confirmed_amount(ctx.text, fields.amount)
    direction = "in" if fields.is_sale else fields.direction
    word = fields.category_word
    if word and word.strip().lower() in _NOT_A_CATEGORY:  # "cash mai se 2000 nikaal liye": a verb, not an expense
        word = None
    if direction is None and word:  # "rickshaw 300": an expense word means money went out
        direction = "out"
    draft = new_cash_draft(
        direction=direction,
        amount=str(amount) if amount is not None else None,
        date=entry_date.isoformat(),
        note=fields.note,
        sale=bool(fields.is_sale),
        category_word=word if direction != "in" else None,
        via="bank" if fields.bank_name else "cash",
        bank_name=fields.bank_name,
    )
    return next_step(ctx, draft)


# ---------------------------------------------------------------------------
# Transfer: cash <-> bank (owner only)
# ---------------------------------------------------------------------------


def next_transfer_step(ctx: Context, draft: dict) -> Outcome:
    language = ctx.language
    if draft["amount"] is None:
        return ask_draft(ctx, "cash_amount", "amount", draft, t("ask_cash_amount", language))

    question = money_step(ctx, draft)  # which bank? opening cash?
    if question:
        return question

    if draft["direction"] is None:
        question = t(
            "ask_transfer_direction", language, amount=format_rs(Decimal(draft["amount"])),
            bank=draft["bank_name"] or draft["new_bank"],
        )
        return ask_draft(ctx, "transfer_direction", "choice", draft, question)
    return _save_transfer(ctx, draft)


def _save_transfer(ctx: Context, draft: dict) -> Outcome:
    language = ctx.language
    business_id = ctx.business["id"]

    def commit(conn: Connection) -> str:
        amount, entry_date = Decimal(draft["amount"]), date.fromisoformat(draft["date"])
        cash_id = cash_account(conn, ctx, draft, entry_date)
        bank_id, bank_name, _ = money_account(conn, ctx, draft, entry_date)
        to_bank = draft["direction"] == "to_bank"
        tools.record_transaction(
            conn,
            business_id=business_id,
            type="transfer",
            entry_date=entry_date,
            legs=[(cash_id, -amount if to_bank else amount), (bank_id, amount if to_bank else -amount)],
            note=None,
            message_id=ctx.message_id,
            user_id=ctx.user["id"],
        )
        cash = t("cash_name", language)
        source, target = (cash, bank_name) if to_bank else (bank_name, cash)
        lines = [t("transfer_saved", language, amount=format_rs(amount), source=source, target=target,
                   date=short_date(entry_date))]
        lines.append(money_line(language, cash, "cash", tools.get_balance(conn, business_id, cash_id)))
        lines.append(money_line(language, bank_name, "bank", tools.get_balance(conn, business_id, bank_id)))
        return "\n".join(lines)

    return Outcome("transfer_money", commit=commit)


@intent(
    "transfer_money",
    "Money between the shop's cash and its OWN bank/wallet: \"to_bank\" (bank mein jama karaye), \"from_bank\" "
    "(bank / ATM se nikale).",
    fields=TransferFields,
    fields_hint=(
        '{"direction": "to_bank" | "from_bank" | null, "bank_name": string | null, '
        '"amount": number | null, "date": "YYYY-MM-DD" | null}'
    ),
    examples=["bank se 10000 nikale", "10000 Meezan mein jama karaye", "ATM se 5000 nikale"],
    needs_business=True,
    owner_only=True,
)
def transfer_money(ctx: Context, fields: TransferFields) -> Outcome:
    entry_date = _entry_date(ctx, fields.date)
    if entry_date is None:
        return Outcome("transfer_money", t("future_date", ctx.language))
    amount = confirmed_amount(ctx.text, fields.amount)
    draft = {
        "mode": "transfer", "direction": fields.direction, "amount": str(amount) if amount is not None else None,
        "date": entry_date.isoformat(), "queue": [], **MONEY_KEYS, "via": "bank", "bank_name": fields.bank_name,
    }
    return next_transfer_step(ctx, draft)


# ---------------------------------------------------------------------------
# Add a bank (owner only)
# ---------------------------------------------------------------------------


@intent(
    "add_bank",
    "User adds the shop's own bank account or wallet (JazzCash, Easypaisa, Meezan ...), optionally with its "
    "account number and current balance.",
    fields=AddBankFields,
    fields_hint='{"name": string, "account_number": string | null, "opening_amount": number | null}',
    examples=["JazzCash account add karo", "Meezan bank add karo account 0123456789, 20000 hain"],
    needs_business=True,
    owner_only=True,
)
def add_bank(ctx: Context, fields: AddBankFields) -> Outcome:
    language, business_id = ctx.language, ctx.business["id"]
    with transaction() as conn:
        same = [b for b in tools.find_banks(conn, business_id, fields.name)
                if b["name"].lower().replace(" ", "") == fields.name.lower().replace(" ", "")]
    if same:
        return Outcome("add_bank", t("bank_exists", language, name=same[0]["name"]))
    opening = confirmed_amount(ctx.text, fields.opening_amount)
    number = "".join(ch for ch in fields.account_number or "" if ch.isalnum()) or None

    def commit(conn: Connection) -> str:
        bank = tools.create_bank(conn, business_id, fields.name, number, ctx.user["id"])
        if opening:
            tools.record_transaction(
                conn, business_id=business_id, type="opening_balance", entry_date=_today(ctx),
                legs=[(bank["id"], opening)], note=None, message_id=ctx.message_id, user_id=ctx.user["id"],
            )
        balance = tools.get_balance(conn, business_id, bank["id"])
        return t("bank_added", language, name=bank["name"]) + "\n" + money_line(language, bank["name"], "bank", balance)

    return Outcome("add_bank", commit=commit)


# ---------------------------------------------------------------------------
# Report: in / out / balance for a day or a period, and the PDF
# ---------------------------------------------------------------------------


def _period(start: date, end: date) -> str:
    return short_date(start) if start == end else f"{short_date(start)} – {short_date(end)}"


@intent(
    "money_report",
    "CASH or a BANK (not a party): cash in hand, money in/out, expenses, the cash book, for a day or a month,"
    " or a PDF. account: \"cash\", a bank name, or null for all. Sales totals are bill_report.",
    fields=MoneyReportFields,
    fields_hint=(
        '{"account": "cash" | string | null, "start_date": "YYYY-MM-DD" | null, "end_date": "YYYY-MM-DD" | null, '
        '"pdf": true | false}  (a month -> its first and last day; "aaj" -> today for both; none said -> both null)'
    ),
    examples=["aaj ka hisaab", "aaj ka cash dikhao", "yeh cash 3800 kya hai", "is month ka kya scene hai",
              "kitna cash hai", "September ka cash", "JazzCash ka hisaab", "cash book PDF bhejo"],
    needs_business=True,
)
def money_report(ctx: Context, fields: MoneyReportFields) -> Outcome:
    language, business_id = ctx.language, ctx.business["id"]
    now = _today(ctx)
    end = min(fields.end_date or now, now)
    start = fields.start_date or (end if fields.end_date else now)
    if start > end:
        return Outcome("money_report", t("future_date", language))

    wanted = (fields.account or "").strip()
    with transaction() as conn:
        cash = tools.get_cash_account(conn, business_id)
        banks = tools.find_banks(conn, business_id)
        if wanted and wanted.lower() not in ("cash", "کیش", "nakad", "galla"):
            matches = tools.find_banks(conn, business_id, wanted)
            if not matches:
                return Outcome("money_report", t("bank_not_found", language, name=wanted))
            main, others = matches[0], []
        else:
            main = cash or (banks[0] if banks else None)
            others = [b for b in banks if main is None or b["id"] != main["id"]]  # bank balances under the cash
        if main is None:
            return Outcome("money_report", t("no_money_yet", language))

        summary = tools.money_summary(conn, business_id, main["id"], start, end)
        rows = tools.money_rows(conn, business_id, main["id"], start, end) if fields.pdf else []
        other_lines = [
            money_line(language, b["name"], "bank", tools.get_balance(conn, business_id, b["id"])) for b in others
        ]

    name = t("cash_name", language) if main["type"] == "cash" else main["name"]
    reply = t(
        "money_report", language, name=name, period=_period(start, end),
        opening=_signed_rs(summary["opening"]), money_in=format_rs(summary["money_in"]),
        money_out=format_rs(summary["money_out"]), closing=_signed_rs(summary["closing"]),
    )
    if summary["categories"]:
        items = "\n".join(f"• {c['name']}: {format_rs(c['total'])}" for c in summary["categories"])
        reply += "\n\n" + t("report_expenses", language, items=items)
    if other_lines:
        reply += "\n\n" + t("report_other_accounts", language, items="\n".join(other_lines))

    attachment = pdf.cash_book_pdf(ctx.business, {**main, "name": name}, summary, rows, start, end) if fields.pdf else None
    return Outcome("money_report", reply, attachment=attachment)


def _signed_rs(value: Decimal) -> str:
    return f"-{format_rs(value)}" if value < 0 else format_rs(value)


# ---------------------------------------------------------------------------
# Answers to pending questions
# ---------------------------------------------------------------------------

_IN_WORDS = {"aaye", "aae", "aya", "aaya", "aai", "in", "mile", "mila", "jama", "آئے", "آیا", "ملے"}
_OUT_WORDS = {"gaye", "gae", "gaya", "gya", "out", "nikale", "nikala", "kharcha", "diye", "گئے", "گیا", "نکالے"}


def _draft(pending: PendingAction) -> dict:
    return dict(pending.data["draft"])


@pending_resolver("cash_amount")
def resolve_cash_amount(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    amount = parse_amount_answer(answer)
    if amount is None:
        amounts = parse_amounts(answer)
        amount = amounts[0] if len(amounts) == 1 else None
    draft = _draft(pending)
    if amount is not None:
        draft["amount"] = str(amount)
    return continue_draft(ctx, draft)  # asks again if still missing


@pending_resolver("cash_direction")
def resolve_cash_direction(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    number = parse_number(answer)
    words = set(answer.lower().split())
    if number == 1 or (number is None and words & _IN_WORDS and not words & _OUT_WORDS):
        draft["direction"] = "in"
        draft["category_word"] = None  # categories are for expenses only
    elif number == 2 or (number is None and words & _OUT_WORDS and not words & _IN_WORDS):
        draft["direction"] = "out"
    return next_step(ctx, draft)  # asks again if still unknown


@pending_resolver("transfer_direction")
def resolve_transfer_direction(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    number = parse_number(answer)
    if number in (1, 2):
        draft["direction"] = "to_bank" if number == 1 else "from_bank"
    return next_transfer_step(ctx, draft)


@pending_resolver("choose_category")
def resolve_choose_category(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    """A number from the list, an existing category's name, or a new name."""
    draft, options = _draft(pending), pending.data["options"]
    chosen = pick(answer, options, lambda c: c["name"])
    if chosen is None and parse_number(answer) is not None:  # a number outside the list
        labels = [t("new_category_option", ctx.language, name=options[0]["name"])] + [c["name"] for c in options[1:]]
        question = t("invalid_choice", ctx.language, n=len(labels), options=numbered(labels))
        return Outcome("cash_entry", question, pending=pending)
    if chosen is None:
        draft["new_category"] = _title(answer)
    elif chosen["id"] is None:
        draft["new_category"] = chosen["name"]
    else:
        draft["category_id"], draft["category_name"] = chosen["id"], chosen["name"]
        draft["remember_word"] = True
    return next_step(ctx, draft)


DRAFT_STEPS["cash"] = ("cash_entry", next_step)
DRAFT_STEPS["transfer"] = ("transfer_money", next_transfer_step)
