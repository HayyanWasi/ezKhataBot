"""Party khata intents: customers, suppliers, diye/liye entries, balances.

The AI only picks one of these intents and fills its fields. Everything else
is code:
  - amounts are checked against the user's own text (app/services/amounts.py)
  - parties are matched against the shop's own list
  - all data access goes through the tools in app/tools/party.py

An entry is built as a "draft". next_step() looks at the draft and either asks
the ONE missing thing (amount -> direction -> which party) or saves it. The
draft is kept in the pending question, so answers ("500", "1", "2") fill it
in without calling the AI again.
"""

import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from psycopg import Connection

from app.core.database import transaction
from app.core.dates import short_date, today
from app.core.phone import normalize_phone
from app.schemas.khata import (
    AddPartyFields,
    ListPartiesFields,
    PartyBalanceFields,
    PartyEntryFields,
    PendingAction,
    SetPartyPhoneFields,
)
from app.services.amounts import confirmed_amount, format_rs, parse_amount_answer, parse_amounts
from app.services.answers import parse_number, pick
from app.handlers.money_steps import MONEY_KEYS, following_draft, money_account, money_line, money_step
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
from app.tools import money as money_tools
from app.tools import party as tools

# Outcome intent name for each kind of draft
_DRAFT_INTENT = {"entry": "party_entry", "opening": "add_party", "add": "add_party"}



# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _business_id(ctx: Context) -> str:
    return str(ctx.business["id"])


def _today(ctx: Context) -> date:
    return today(ctx.business["timezone"])


def balance_line(language: str, name: str, balance: Decimal) -> str:
    if balance > 0:
        return t("balance_get", language, name=name, amount=format_rs(balance))
    if balance < 0:
        return t("balance_give", language, name=name, amount=format_rs(balance))
    return t("balance_settled", language, name=name)


def _short_balance(language: str, balance: Decimal) -> str:
    if balance > 0:
        return t("short_get", language, amount=format_rs(balance))
    if balance < 0:
        return t("short_give", language, amount=format_rs(balance))
    return t("short_settled", language)


def _type_label(language: str, party_type: str) -> str:
    return t(f"type_{party_type}", language)


def _party_label(language: str, party: dict) -> str:
    return f"{party['name']} ({_type_label(language, party['type'])})"


_ask = ask_draft


# What happens after the user picks a party, per purpose: (intent name, fn(ctx, party, data) -> Outcome).
# Other features (statements, reminders) register their own purposes here.
PARTY_CHOICE_HANDLERS: dict[str, tuple[str, Callable[[Context, dict, dict], Outcome]]] = {}


def ask_choose_party(ctx: Context, name: str, matches: list[dict], purpose: str, data: dict) -> Outcome:
    """Several parties match a name: ask which one (entries may also pick 'new party')."""
    options = [{"id": str(p["id"]), "name": p["name"], "type": p["type"], "phone": p.get("phone")} for p in matches]
    labels = [_party_label(ctx.language, p) for p in options]
    if purpose == "entry":
        labels.append(t("new_party_option", ctx.language))
    pending = PendingAction(
        kind="choose_party",
        language=ctx.language,
        expects="choice",
        data={"purpose": purpose, "name": name, "options": options, **data},
    )
    intent_name = "party_entry" if purpose == "entry" else PARTY_CHOICE_HANDLERS[purpose][0]
    return Outcome(intent_name, t("choose_party", ctx.language, name=name, options=numbered(labels)), pending=pending)



def _find(ctx: Context, name: str, party_type: str | None = None) -> list[dict]:
    with transaction() as conn:
        return tools.find_parties(conn, _business_id(ctx), name, party_type)


# ---------------------------------------------------------------------------
# Entry drafts: ask one missing thing at a time, then save
# ---------------------------------------------------------------------------


def new_draft(mode: str, **values) -> dict:
    """mode: 'entry' (diye/liye), 'opening' (new party with old balance), 'add' (new party only).
    Everything in a draft is JSON-safe: it is stored in the pending question."""
    draft = {
        "mode": mode, "party_name": None, "party_type": None, "account_id": None, "new_type": None,
        "force_new": False, "phone": None, "direction": None, "amount": None, "date": None, "note": None,
        "queue": [],  # more drafts to go through after this one (rows from a photo)
        "source_message_id": None, "source_line": 0,  # a photo row: saved against the photo message
        **MONEY_KEYS,  # paid in cash / a bank (see app/handlers/money_steps.py)
    }
    draft.update(values)
    return draft


def next_step(ctx: Context, draft: dict) -> Outcome:
    language, mode, name = ctx.language, draft["mode"], draft["party_name"]

    if not name:
        return _ask(ctx, "entry_party", "text", draft, t("ask_party", language))
    draft["party_name"] = name = tools.nice_name(name)  # "ali" -> "Ali" in replies and when saved

    if mode != "add":
        if draft["amount"] is None:
            return _ask(ctx, "entry_amount", "amount", draft, t("ask_amount", language, name=name))
        if draft["direction"] is None:
            key = "ask_opening_direction" if mode == "opening" else "ask_direction"
            question = t(key, language, name=name, amount=format_rs(Decimal(draft["amount"])))
            return _ask(ctx, "entry_direction", "choice", draft, question)

    if draft["account_id"] is None:
        # An entry uses an existing party when the name matches one
        if mode == "entry" and not draft["force_new"]:
            matches = _find(ctx, name, draft["party_type"])
            if len(matches) == 1:
                draft["account_id"], draft["party_name"] = str(matches[0]["id"]), matches[0]["name"]
            elif matches:
                return ask_choose_party(ctx, name, matches, "entry", {"draft": draft})

    if draft["account_id"] is None:
        # A new party: its type is asked unless the user said it while adding
        if draft["new_type"] is None:
            if mode != "entry" and draft["party_type"]:
                draft["new_type"] = draft["party_type"]
            else:
                return _ask(ctx, "new_party_type", "choice", draft, t("ask_party_type", language, name=name))
        same = [p for p in _find(ctx, name, draft["new_type"]) if p["name"].lower() == name.lower()]
        if same:
            party_type = _type_label(language, draft["new_type"])
            return Outcome(_DRAFT_INTENT[mode], t("party_exists", language, name=same[0]["name"], type=party_type))

    question = money_step(ctx, draft)  # paid in cash / a bank: which bank? opening cash?
    if question:
        return question

    saved = _save(ctx, draft)
    if draft.get("queue"):  # save this one, then ask about the next draft in the same reply
        return chain(saved, continue_draft(ctx, following_draft(draft)))
    return saved


def _save(ctx: Context, draft: dict) -> Outcome:
    language, mode = ctx.language, draft["mode"]
    business_id, user_id = _business_id(ctx), ctx.user["id"]

    def commit(conn: Connection) -> str:
        account_id, name = draft["account_id"], draft["party_name"]
        lines = []
        if account_id is None:
            created = tools.create_party(conn, business_id, draft["new_type"], name, draft["phone"], user_id)
            account_id = created["id"]
            if mode != "entry":
                lines.append(t("party_added", language, name=name, type=_type_label(language, draft["new_type"])))
        if mode == "add":
            return lines[0]

        amount, entry_date = Decimal(draft["amount"]), date.fromisoformat(draft["date"])
        paid = money_account(conn, ctx, draft, entry_date)  # None = khata only (udhaar)
        tools.record_entry(
            conn,
            business_id=business_id,
            account_id=account_id,
            direction=draft["direction"],
            amount=amount,
            entry_date=entry_date,
            note=draft["note"],
            message_id=draft.get("source_message_id") or ctx.message_id,
            user_id=user_id,
            opening=mode == "opening",
            source_line=draft.get("source_line", 0),
            money_account_id=paid[0] if paid else None,
        )
        if mode == "entry":
            key = "entry_gave" if draft["direction"] == "gave" else "entry_got"
            lines.append(t(key, language, name=name, amount=format_rs(amount), date=short_date(entry_date)))
        lines.append(balance_line(language, name, tools.get_balance(conn, business_id, account_id)))
        if paid:
            money_id, money_name, money_type = paid
            balance = money_tools.get_balance(conn, business_id, money_id)
            lines.append(money_line(language, money_name, money_type, balance))
        return "\n".join(lines)

    return Outcome(_DRAFT_INTENT[mode], commit=commit)


# ---------------------------------------------------------------------------
# Intents
# ---------------------------------------------------------------------------


@intent(
    "party_entry",
    "User records money or goods GIVEN TO or RECEIVED FROM a customer or supplier (khata entry). "
    "direction is from the SHOP's side: "
    '"gave" = the shop gave money/goods to the party, e.g. "Ali ko 500 diye", "Ali ko udhaar diya", '
    '"Rohaan ko payment ki", "Ali ne 500 liye" (Ali took). '
    '"got" = the shop received money/goods from the party, e.g. "Ali se 300 mile", "Ali ne 300 diye" '
    '(Ali gave), "Rohaan se maal liya", "Ali ne paise wapis kiye". '
    "Use null when the message does not say who gave to whom (e.g. \"Ali 500\"). "
    'paid_via: "cash" when it clearly says real money was paid or paid back (wapas/wapis, payment, ada, '
    'cash, nakad, "paise wapas"); "bank" when a bank or wallet is named (JazzCash, Easypaisa, Meezan, '
    '"account mein bheje"); null for udhaar, goods (maal/saman) or when it is not clear. '
    "Salary or wages paid to a worker is NOT a party entry (use cash_entry). "
    "A message that lists ITEMS with quantities (\"100 belt\", \"10 kg cheeni\") is NOT a party entry, even when "
    "a party is named: items coming in = stock_in, going back = stock_out, SOLD to a customer (\"Ali ko 2 packet "
    "surf udhaar diye\", \"customer ne 4 darjan ande liye\") = create_bill. "
    "question: true when the user only ASKS whether it happened (\"Rohaan ko 500 diye?\", \"kya Ali ne paise diye "
    "the\", \"Ali ko 500 diye ya nahi\") - then nothing is saved, the khata is checked.",
    fields=PartyEntryFields,
    fields_hint=(
        '{"party_name": string | null (as written, e.g. "Ali"), '
        '"party_type": "customer" | "supplier" | null (only if the user says it), '
        '"direction": "gave" | "got" | null, "amount": number | null, '
        '"date": "YYYY-MM-DD" | null, "note": string | null (item or reason, e.g. "cheeni"), '
        '"paid_via": "cash" | "bank" | null, "bank_name": string | null, "question": true | false}'
    ),
    examples=[
        "Ali ko 500 udhaar diye", "Ali se 300 mile", "Rohaan se 5000 ka maal liya kal",
        "Ali ne 200 wapis kiye", "Bilal ko 5000 payment ki", "Ali ne 1000 JazzCash pe bheje",
        "علی کو 500 دیے", "gave 200 to Bilal",
    ],
    needs_business=True,
    owner_only=True,
)
def party_entry(ctx: Context, fields: PartyEntryFields) -> Outcome:
    if fields.question or asks_question(ctx.text):
        return _answer_entry_question(ctx, fields)
    entry_date = fields.date or _today(ctx)
    if entry_date > _today(ctx):
        return Outcome("party_entry", t("future_date", ctx.language))
    amount = confirmed_amount(ctx.text, fields.amount)  # must be written in the message
    draft = new_draft(
        "entry",
        party_name=fields.party_name,
        party_type=fields.party_type,
        direction=fields.direction,
        amount=str(amount) if amount is not None else None,
        date=entry_date.isoformat(),
        note=fields.note,
        via="bank" if fields.bank_name else paid_via(ctx.text, fields.paid_via),
        bank_name=fields.bank_name,
    )
    return next_step(ctx, draft)


# "Ali ko 500 diye?" asks, it doesn't tell. Code decides too, so a question is never saved
# even when the AI misses it.
_QUESTION = re.compile(
    r"[?؟]\s*$|\b(ya nahi|ya nhi|ya nahin|or not|did i|have i|kya maine|kia maine)\b|^\s*(kya|kia|کیا)\b",
    re.IGNORECASE,
)


def asks_question(text: str) -> bool:
    return bool(_QUESTION.search(text))


def _answer_entry_question(ctx: Context, fields: PartyEntryFields) -> Outcome:
    """Was it given / received? Look in the khata and say haan or nahi, then show the khata."""
    language = ctx.language
    if not fields.party_name:
        return list_parties(ctx, ListPartiesFields())
    matches = _find(ctx, fields.party_name)
    if not matches:
        return Outcome("party_balance", t("asked_entry_no_party", language, name=fields.party_name))
    if len(matches) > 1:
        return ask_choose_party(ctx, fields.party_name, matches, "balance", {})
    party = matches[0]
    amount = confirmed_amount(ctx.text, fields.amount)
    with transaction() as conn:
        entries = tools.recent_entries(conn, _business_id(ctx), party["id"], limit=50)
    found = next(
        (e for e in entries
         if e["transaction_type"] != "opening_balance"
         and (amount is None or abs(e["amount"]) == amount)
         and (fields.direction is None or (e["amount"] > 0) == (fields.direction == "gave"))
         and (fields.date is None or e["transaction_date"] == fields.date)),
        None,
    )
    if found:
        verb = "verb_gave" if found["amount"] > 0 else "verb_got"
        answer = t("asked_entry_yes", language, date=short_date(found["transaction_date"]),
                   text=f"{party['name']} · {t(verb, language)} {format_rs(found['amount'])}")
    else:
        what = f"{party['name']} · {t('verb_got' if fields.direction == 'got' else 'verb_gave', language)}"
        what += f" {format_rs(amount)}" if amount is not None else ""
        answer = t("asked_entry_no", language, text=what) if fields.direction or amount else ""
    khata = _show_balance(ctx, party).reply
    return Outcome("party_balance", f"{answer}\n\n{khata}" if answer else khata)


# Words that mean real money was paid (not udhaar / goods). Code decides, so the same sentence
# always gives the same result; the AI's paid_via is only used when none of these words is there.
_PAYMENT_WORDS = {"payment", "wapas", "wapis", "wapsi", "lota", "lotaye", "lotae", "ada", "cash", "nakad",
                  "naqad", "paid", "returned", "ادا", "واپس", "نقد", "کیش"}
_CREDIT_WORDS = {"udhaar", "udhar", "udhari", "saman", "samaan", "maal", "credit", "ادھار", "سامان", "مال"}


def paid_via(text: str, ai_value: str | None) -> str | None:
    words = set(re.findall(r"\w+", text.lower()))
    if words & _CREDIT_WORDS:
        return None
    if words & _PAYMENT_WORDS:
        return "cash"
    return ai_value


@intent(
    "add_party",
    "User adds a NEW customer or supplier, optionally with a phone number and an old (opening) balance. "
    'opening_direction: "will_get" = the party owes the shop ("pehle ke 2000 lene hain"), '
    '"will_give" = the shop owes the party ("pehle ke 2000 dene hain").',
    fields=AddPartyFields,
    fields_hint=(
        '{"name": string, "type": "customer" | "supplier" | null, "phone": string | null, '
        '"opening_amount": number | null, "opening_direction": "will_get" | "will_give" | null}'
    ),
    examples=[
        "Bilal naya customer hai 03001234567", "Rohaan supplier add karo, pehle ke 2000 dene hain",
        "add customer Ahmed", "نیا گاہک احمد",
    ],
    needs_business=True,
    owner_only=True,
)
def add_party(ctx: Context, fields: AddPartyFields) -> Outcome:
    phone = None
    if fields.phone:
        try:
            phone = normalize_phone(fields.phone)
        except ValueError:
            return Outcome("add_party", t("invalid_phone", ctx.language))

    has_opening = fields.opening_amount is not None or fields.opening_direction is not None
    amount = confirmed_amount(ctx.text, fields.opening_amount) if has_opening else None
    direction = {"will_get": "gave", "will_give": "got"}.get(fields.opening_direction or "")
    draft = new_draft(
        "opening" if has_opening else "add",
        party_name=fields.name,
        party_type=fields.type,
        phone=phone,
        direction=direction,
        amount=str(amount) if amount is not None else None,
        date=_today(ctx).isoformat(),
    )
    return next_step(ctx, draft)


@intent(
    "set_party_phone",
    "User gives the phone number of an EXISTING customer or supplier.",
    fields=SetPartyPhoneFields,
    fields_hint='{"party_name": string, "phone": string}',
    examples=["Ali ka number 03001234567", "Rohaan's number is 0321 1234567"],
    needs_business=True,
    owner_only=True,
)
def set_party_phone(ctx: Context, fields: SetPartyPhoneFields) -> Outcome:
    try:
        phone = normalize_phone(fields.phone)
    except ValueError:
        return Outcome("set_party_phone", t("invalid_phone", ctx.language))
    matches = _find(ctx, fields.party_name)
    if not matches:
        return Outcome("set_party_phone", t("party_not_found", ctx.language, name=fields.party_name))
    if len(matches) > 1:
        return ask_choose_party(ctx, fields.party_name, matches, "phone", {"phone": phone})
    return _save_phone(ctx, matches[0], phone)


def _save_phone(ctx: Context, party: dict, phone: str) -> Outcome:
    business_id = _business_id(ctx)

    def commit(conn: Connection) -> str:
        tools.set_party_phone(conn, business_id, party["id"], phone)
        return t("phone_saved", ctx.language, name=party["name"])

    return Outcome("set_party_phone", commit=commit)


@intent(
    "party_balance",
    "User asks about ONE customer or supplier: who they are, their details, balance, khata or entries.",
    fields=PartyBalanceFields,
    fields_hint='{"party_name": string | null}',
    examples=["Ali ka hisaab", "Ali ka khata dikhao", "Ali kon hai?", "Bilal ki details", "how much does Bilal owe",
              "علی کا حساب"],
    needs_business=True,
)
def party_balance(ctx: Context, fields: PartyBalanceFields) -> Outcome:
    if not fields.party_name:
        return list_parties(ctx, ListPartiesFields())
    matches = _find(ctx, fields.party_name)
    if not matches:
        return Outcome("party_balance", t("party_not_found", ctx.language, name=fields.party_name))
    if len(matches) > 1:
        return ask_choose_party(ctx, fields.party_name, matches, "balance", {})
    return _show_balance(ctx, matches[0])


def _show_balance(ctx: Context, party: dict) -> Outcome:
    language, business_id = ctx.language, _business_id(ctx)
    with transaction() as conn:
        balance = tools.get_balance(conn, business_id, party["id"])
        entries = tools.recent_entries(conn, business_id, party["id"])

    lines = [f"*{_party_label(language, party)}*" + (f" · 📞 {party['phone']}" if party.get("phone") else ""),
             balance_line(language, party["name"], balance)]
    if entries:
        lines.append("")
        for e in entries:
            verb = "verb_opening" if e["transaction_type"] == "opening_balance" else (
                "verb_gave" if e["amount"] > 0 else "verb_got"
            )
            lines.append(
                f"{short_date(e['transaction_date'])} · {t(verb, language)} {format_rs(e['amount'])}"
                f" → {_short_balance(language, e['running_balance'])}"
            )
    else:
        lines.append(t("no_entries", language))
    return Outcome("party_balance", "\n".join(lines))


@intent(
    "list_parties",
    "User asks for ALL parties' balances or totals: who owes the shop, whom the shop owes, customer/supplier list.",
    fields=ListPartiesFields,
    fields_hint='{"type": "customer" | "supplier" | null}',
    examples=["sab ka hisaab", "kis kis se lene hain", "suppliers ko kitne dene hain", "customer list"],
    needs_business=True,
)
def list_parties(ctx: Context, fields: ListPartiesFields) -> Outcome:
    language = ctx.language
    with transaction() as conn:
        rows = tools.list_balances(conn, _business_id(ctx), fields.type)
    if not rows:
        return Outcome("list_parties", t("no_parties", language))

    total_get = sum((r["balance"] for r in rows if r["balance"] > 0), Decimal(0))
    total_give = sum((-r["balance"] for r in rows if r["balance"] < 0), Decimal(0))
    items = [f"{r['name']} — {_short_balance(language, r['balance'])}" for r in rows[:10]]
    reply = t(
        "party_list", language, get=format_rs(total_get), give=format_rs(total_give), items=numbered(items)
    )
    return Outcome("list_parties", reply)


# ---------------------------------------------------------------------------
# Answers to pending questions
# ---------------------------------------------------------------------------

_GAVE_WORDS = {"diye", "diya", "di", "de", "gave", "given", "lene", "get", "دیے", "دیا", "لینے"}
_GOT_WORDS = {"liye", "liya", "li", "mile", "mila", "got", "received", "dene", "give", "لیے", "لیا", "ملے", "ملا", "دینے"}


def _draft(pending: PendingAction) -> dict:
    return dict(pending.data["draft"])


def _retry(ctx: Context, pending: PendingAction, question: str) -> Outcome:
    """Answer didn't fit: ask the same question again, keeping the draft."""
    return Outcome(_DRAFT_INTENT[pending.data["draft"]["mode"]], question, pending=pending)


@pending_resolver("entry_party")
def resolve_entry_party(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    draft["party_name"] = answer.strip()
    return next_step(ctx, draft)


@pending_resolver("entry_amount")
def resolve_entry_amount(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    amount = parse_amount_answer(answer)
    if amount is None:
        amounts = parse_amounts(answer)
        amount = amounts[0] if len(amounts) == 1 else None
    if amount is None:
        return _retry(ctx, pending, t("ask_amount", ctx.language, name=pending.data["draft"]["party_name"]))
    draft = _draft(pending)
    draft["amount"] = str(amount)
    return next_step(ctx, draft)


@pending_resolver("entry_direction")
def resolve_entry_direction(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    number = parse_number(answer)
    words = set(answer.lower().split())
    if number == 1 or (number is None and words & _GAVE_WORDS and not words & _GOT_WORDS):
        draft["direction"] = "gave"
    elif number == 2 or (number is None and words & _GOT_WORDS and not words & _GAVE_WORDS):
        draft["direction"] = "got"
    return next_step(ctx, draft)  # asks again if still unknown


@pending_resolver("new_party_type")
def resolve_new_party_type(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    text = answer.lower()
    number = parse_number(answer)
    if number == 1 or (number is None and any(w in text for w in ("customer", "gahak", "grahak", "گاہک"))):
        draft["new_type"] = "customer"
    elif number == 2 or (number is None and any(w in text for w in ("supplier", "sapplier", "سپلائر"))):
        draft["new_type"] = "supplier"
    return next_step(ctx, draft)  # asks again if still unknown


@pending_resolver("choose_party")
def resolve_choose_party(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    data, options = pending.data, pending.data["options"]
    purpose = data["purpose"]

    if purpose == "entry" and parse_number(answer) == len(options) + 1:  # "new party"
        draft = dict(data["draft"])
        draft["force_new"] = True
        return next_step(ctx, draft)

    chosen = pick(answer, options, lambda p: p["name"])
    if chosen is None:
        labels = [_party_label(ctx.language, p) for p in options]
        if purpose == "entry":
            labels.append(t("new_party_option", ctx.language))
        return Outcome(
            "choose_party", t("invalid_choice", ctx.language, n=len(labels), options=numbered(labels)), pending=pending
        )

    if purpose == "entry":
        draft = dict(data["draft"])
        draft["account_id"], draft["party_name"] = chosen["id"], chosen["name"]
        return next_step(ctx, draft)
    _, handle = PARTY_CHOICE_HANDLERS[purpose]
    return handle(ctx, chosen, data)


PARTY_CHOICE_HANDLERS.update({
    "balance": ("party_balance", lambda ctx, party, data: _show_balance(ctx, party)),
    "phone": ("set_party_phone", lambda ctx, party, data: _save_phone(ctx, party, data["phone"])),
})


for _mode, _intent in _DRAFT_INTENT.items():
    DRAFT_STEPS[_mode] = (_intent, next_step)
