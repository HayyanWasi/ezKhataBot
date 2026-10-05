"""Questions shared by every draft that moves real money (party payment, cash
entry, transfer): which bank? and, the first time cash is used, how much cash
is in the shop now?

Draft keys used here (all JSON-safe, kept in the pending question):
    via               "cash" | "bank" | None (None = khata only, no money moved)
    bank_name         the bank/wallet the user named, e.g. "JazzCash"
    money_account_id  the chosen bank's id (cash is looked up at save time)
    new_bank          a bank name to create at save time (the user said haan)
    opening_cash      the cash in the shop before this entry ("0" if skipped)
"""

from datetime import date
from decimal import Decimal

from psycopg import Connection

from app.core.database import transaction
from app.schemas.khata import PendingAction
from app.services.amounts import format_rs, parse_amount_answer
from app.services.answers import is_skip, parse_yes_no, pick
from app.services.registry import DRAFT_STEPS, Context, Outcome, ask_draft, continue_draft, pending_resolver
from app.services.replies import numbered, t
from app.tools import money as tools

_GENERIC_BANK_WORDS = {"bank", "account", "wallet", "online", "bank account", "بینک", "اکاؤنٹ"}

MONEY_KEYS = {"via": None, "bank_name": None, "money_account_id": None, "new_bank": None, "opening_cash": None}


def _is_owner(ctx: Context) -> bool:
    return ctx.business["role"] == "owner"


def uses_cash(draft: dict) -> bool:
    return draft["mode"] == "transfer" or draft.get("via") == "cash"


def money_step(ctx: Context, draft: dict) -> Outcome | None:
    """The next money question for this draft, or None when nothing is missing."""
    business_id, language = ctx.business["id"], ctx.language

    if draft.get("via") == "bank" and draft["money_account_id"] is None and draft["new_bank"] is None:
        name = draft["bank_name"]
        if name and name.strip().lower() in _GENERIC_BANK_WORDS:  # "bank mein jama" names no bank
            name = draft["bank_name"] = None
        with transaction() as conn:
            banks = tools.find_banks(conn, business_id, name)
        if len(banks) == 1:
            draft["money_account_id"], draft["bank_name"] = str(banks[0]["id"]), banks[0]["name"]
        elif banks:
            options = [{"id": str(b["id"]), "name": b["name"]} for b in banks]
            question = t("choose_bank", language, options=numbered([b["name"] for b in options]))
            return ask_draft(ctx, "choose_bank", "choice", draft, question, options=options)
        elif not _is_owner(ctx):
            return Outcome(draft_intent(draft), t("bank_owner_only", language))
        elif name:
            return ask_draft(ctx, "confirm_new_bank", "yes_no", draft, t("confirm_new_bank", language, name=name))
        else:
            return ask_draft(ctx, "bank_name", "choice_or_name", draft, t("ask_bank_name", language))

    if uses_cash(draft) and draft["opening_cash"] is None:
        with transaction() as conn:
            has_cash = tools.get_cash_account(conn, business_id) is not None
        if not has_cash:
            return ask_draft(ctx, "opening_cash", "amount_or_skip", draft, t("ask_opening_cash", language))
    return None


BIG_AMOUNT = Decimal(1_000_000)


def check_step(ctx: Context, draft: dict, types: tuple[str, ...], signed: Decimal,
               account_id: str | None = None) -> Outcome | None:
    """Last check before a typed entry is saved: a very large amount ("Ali ko 5000000 diye"), or the
    same entry saved a minute ago ("rickshaw 100" sent twice), is asked with haan/nahi. None = save."""
    if draft.get("checked") or draft.get("source_message_id"):  # photo rows have their own confirm
        return None
    amount = abs(signed)
    if amount >= BIG_AMOUNT:
        question = t("confirm_big_amount", ctx.language, amount=format_rs(amount))
    else:
        with transaction() as conn:
            if not tools.saved_just_now(conn, ctx.business["id"], types, signed, account_id):
                return None
        question = t("confirm_repeat_entry", ctx.language, amount=format_rs(amount))
    return ask_draft(ctx, "confirm_entry", "yes_no", draft, question)


def following_draft(draft: dict) -> dict:
    """The next queued draft (rows from a photo). The opening cash, once answered, is passed on so it
    isn't asked again: the cash account is only created when this reply is committed."""
    following = dict(draft["queue"][0], queue=draft["queue"][1:])
    if following.get("opening_cash") is None:
        following["opening_cash"] = draft.get("opening_cash")
    return following


def draft_intent(draft: dict) -> str:
    return DRAFT_STEPS[draft["mode"]][0]


def money_account(conn: Connection, ctx: Context, draft: dict, entry_date: date) -> tuple | None:
    """Inside the commit: the (id, name, type) of the cash/bank account this draft moves money in,
    creating the cash account (with its opening cash) or a new bank when needed. None = khata only."""
    business_id, user_id = ctx.business["id"], ctx.user["id"]
    if draft.get("via") == "bank":
        if draft["money_account_id"] is None:
            bank = tools.create_bank(conn, business_id, draft["new_bank"], None, user_id)
            draft["money_account_id"], draft["bank_name"] = str(bank["id"]), bank["name"]
        return draft["money_account_id"], draft["bank_name"], "bank"
    if draft.get("via") == "cash":
        return cash_account(conn, ctx, draft, entry_date), tools.CASH_NAME, "cash"
    return None


def cash_account(conn: Connection, ctx: Context, draft: dict, entry_date: date):
    opening = Decimal(draft["opening_cash"]) if draft.get("opening_cash") else None
    return tools.ensure_cash_account(conn, ctx.business["id"], ctx.user["id"], opening, entry_date)


def money_line(language: str, name: str, account_type: str, balance: Decimal) -> str:
    """💵 Cash: Rs 4,500  /  🏦 JazzCash: Rs 1,000  /  ⚠️ Cash: -Rs 300"""
    icon = "💵" if account_type == "cash" else "🏦"
    name = t("cash_name", language) if account_type == "cash" else name
    if balance < 0:
        return f"⚠️ {name}: -{format_rs(balance)}"
    return f"{icon} {name}: {format_rs(balance)}"


# ---------------------------------------------------------------------------
# Answers
# ---------------------------------------------------------------------------


def _draft(pending: PendingAction) -> dict:
    return dict(pending.data["draft"])


@pending_resolver("choose_bank")
def resolve_choose_bank(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    options = pending.data["options"]
    chosen = pick(answer, options, lambda b: b["name"])
    if chosen is None:
        labels = [b["name"] for b in options]
        question = t("invalid_choice", ctx.language, n=len(labels), options=numbered(labels))
        return Outcome(draft_intent(pending.data["draft"]), question, pending=pending)
    draft = _draft(pending)
    draft["money_account_id"], draft["bank_name"] = chosen["id"], chosen["name"]
    return continue_draft(ctx, draft)


@pending_resolver("confirm_new_bank")
def resolve_confirm_new_bank(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    draft = _draft(pending)
    if yes is None:
        return Outcome(draft_intent(draft), t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome(draft_intent(draft), t("image_cancelled", ctx.language))
    draft["new_bank"] = draft["bank_name"].strip()
    return continue_draft(ctx, draft)


@pending_resolver("bank_name")
def resolve_bank_name(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    draft["bank_name"] = answer.strip()
    return continue_draft(ctx, draft)  # finds it, or asks "add as new?"


@pending_resolver("opening_cash")
def resolve_opening_cash(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    amount = parse_amount_answer(answer)
    if amount is None and not (answer.strip() == "0" or is_skip(answer)):
        return Outcome(draft_intent(draft), t("ask_opening_cash", ctx.language), pending=pending)
    draft["opening_cash"] = str(amount) if amount is not None else "0"
    return continue_draft(ctx, draft)


@pending_resolver("confirm_entry")
def resolve_confirm_entry(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    draft = _draft(pending)
    if yes is None:
        return Outcome(draft_intent(draft), t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome(draft_intent(draft), t("cancelled", ctx.language))
    draft["checked"] = True
    return continue_draft(ctx, draft)
