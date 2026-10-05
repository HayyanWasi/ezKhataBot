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
    RenamePartyFields,
    SetPartyPhoneFields,
)
from app.services.amounts import confirmed_amount, format_rs, parse_amount_answer, parse_amounts
from app.services.answers import bought_by, parse_number, parse_yes_no, pick
from app.handlers.money_steps import (
    MONEY_KEYS,
    check_step,
    following_draft,
    money_account,
    money_line,
    money_step,
)
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
from app.tools import stock as stock_tools

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

    if not name or name.strip().lower() in _NOT_A_NAME:  # "3k supplier ko diya": which supplier?
        draft["party_name"] = None
        key = "ask_party" if mode == "entry" else "ask_new_party_name"
        return _ask(ctx, "entry_party", "text", draft, t(key, language))
    draft["party_name"] = name = tools.nice_name(name)  # "ali" -> "Ali" in replies and when saved

    if mode != "entry" and not draft["party_type"] and draft["new_type"] is None:
        same = [p for p in _find(ctx, name) if p["name"].lower() == name.lower()]
        if same:  # "ali add kr" when Ali is already there: no second Ali
            party_type = _type_label(language, same[0]["type"])
            return Outcome(_DRAFT_INTENT[mode], t("party_already", language, name=same[0]["name"], type=party_type))

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
    if mode != "add":  # a very large amount, or the same entry a minute ago: asked first
        amount = Decimal(draft["amount"])
        signed = amount if draft["direction"] == "gave" else -amount
        types = ("gave", "got") if draft["account_id"] else ()  # a new party has no earlier entry
        question = check_step(ctx, draft, types, signed, draft["account_id"])
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
    "Money or goods GIVEN TO or RECEIVED FROM a customer/supplier (khata). direction, from the shop's side: "
    "\"gave\" = the shop gave (\"Ali ko 500 diye\", \"Ali ne 500 liye\", \"Rohaan ko payment ki\"); \"got\" = the shop "
    "received (\"Ali se 300 mile\", \"Ali ne 300 diye\", \"Ali ne paise wapis kiye\"); null if it is not said who "
    "gave (\"Ali 500\"). paid_via: \"cash\" if real money was paid (wapas, payment, ada, cash, nakad), \"bank\" if "
    "a bank or wallet is named, else null (udhaar, maal). Not for a worker's salary (cash_entry) or ITEMS "
    "with counts (\"10 kg cheeni\": stock_in / stock_out / create_bill). question: true when the user only ASKS"
    " (\"Rohaan ko 500 diye?\", \"Ali ko 500 diye ya nahi\"): nothing is saved.",
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
    sold = fields.direction != "got" or bought_by(ctx.text, fields.party_name)
    if sold and fields.paid_via is None and fields.party_name:
        goods = shop_goods(ctx, ctx.text)
        if goods:  # "Sameer ne udhar kiya 1 sock": the shop's own item with a count is a sale on udhaar
            return _as_bill(ctx, fields, goods, entry_date)
    amount = confirmed_amount(ctx.text, fields.amount)  # must be written in the message
    draft = new_draft(
        "entry",
        party_name=fields.party_name,
        party_type=fields.party_type,
        # "Ali ko 500", "ali ko 500 daldo": no word says who gave, so it is asked, never guessed
        direction=fields.direction if direction_written(ctx.text) else None,
        amount=str(amount) if amount is not None else None,
        date=entry_date.isoformat(),
        note=fields.note,
        via="bank" if fields.bank_name else paid_via(ctx.text, fields.paid_via),
        bank_name=fields.bank_name,
    )
    return next_step(ctx, draft)


_COUNT_WORDS = {"aik": 1, "ek": 1, "ik": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
                "chay": 6, "chhe": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10}
_COUNTED = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?|" + "|".join(_COUNT_WORDS) + r")\s+([^\W\d_]+(?:\s+[^\W\d_]+)?)", re.IGNORECASE
)


def shop_goods(ctx: Context, text: str, count_needed: bool = True) -> list[tuple[dict, Decimal]]:
    """The shop's own stock items written in the text with a count ("1 sock", "aik juicer") ->
    [(item, count)]. Only a sure match on an item's name counts, never a guess.
    count_needed=False: an item named without a count ("jitne ka sock hai") counts as 1."""
    found: dict = {}
    with transaction() as conn:
        def item(word: str) -> dict | None:
            matches = stock_tools.find_item(conn, ctx.business["id"], word, partial=False)
            return matches[0] if len(matches) == 1 else None

        for count, words in _COUNTED.findall(text):
            first = words.split()[0]
            hit = item(words) or item(first)
            if hit:
                found.setdefault(hit["id"], (hit, Decimal(_COUNT_WORDS.get(count.lower(), count))))
        if not found and not count_needed:
            for word in re.findall(r"[^\W\d_]+", text):
                hit = item(word)
                if hit:
                    found.setdefault(hit["id"], (hit, Decimal(1)))
    return list(found.values())


def _as_bill(ctx: Context, fields: PartyEntryFields, goods: list[tuple[dict, Decimal]], entry_date: date) -> Outcome:
    """A customer took the shop's items on credit: an udhaar bill (stock goes down, the khata goes up)."""
    from dataclasses import replace

    from app.handlers import bills  # bills imports this module
    from app.schemas.khata import CreateBillFields, StockLine

    lines = [StockLine(name=item["name"], qty=str(count)) for item, count in goods]
    # "aik sock" -> the count must be written for the bill's checks: add it in digits
    text = ctx.text + " " + " ".join(f"{count} {item['name']}" for item, count in goods)
    bill = CreateBillFields(customer_name=fields.party_name, items=lines, paid_via="udhaar",
                            date=entry_date if fields.date else None)
    return bills.create_bill(replace(ctx, text=text), bill)


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


# Words that tell which way money or goods went. Without one ("Ali ko 500", "500rs ali ko") the
# direction is asked.
_DIRECTION_WORDS = {
    "diye", "diya", "di", "dia", "de", "dey", "diay", "dye", "dediye", "dediya", "dedia", "dedi", "dedye",
    "liye", "liya", "li", "lia", "le", "lie", "leliye", "leliya", "lelia", "lelya", "mile", "mila", "mili",
    "aaye", "aae", "aaya", "aya", "aye", "aai", "ayi", "gaye", "gae", "gya", "gaya", "bheje", "bheja", "bheji",
    "bhejy", "wapas", "wapis", "wapsi", "lota", "lotaye", "lotae", "ada", "jama", "udhaar", "udhar", "udhari",
    "lene", "lena", "dene", "dena", "baqi", "baaki", "kharida", "kharide", "kharidi", "khareeda", "khareedi",
    "becha", "beche", "bechi", "payment", "pay", "paid", "gave", "give", "given", "got", "received", "took",
    "sent", "returned", "lent", "borrowed", "owes", "owe", "credit",
    "دیے", "دیا", "دی", "دئیے", "لیے", "لیا", "لی", "ملے", "ملا", "آئے", "آیا", "بھیجے", "بھیجا", "ادا", "واپس",
    "ادھار", "جمع", "لینے", "دینے",
}
# Words for a kind of party, not a name: "supplier ko 3000 diye" names nobody
_NOT_A_NAME = {"supplier", "suppliers", "customer", "customers", "party", "banda", "bande", "admi", "aadmi",
               "dukandar", "grahak", "gahak", "wala", "wale", "koi", "سپلائر", "گاہک"}


def direction_written(text: str) -> bool:
    return bool(set(re.findall(r"\w+", text.lower())) & _DIRECTION_WORDS)


def paid_via(text: str, ai_value: str | None) -> str | None:
    words = set(re.findall(r"\w+", text.lower()))
    if words & _CREDIT_WORDS:
        return None
    if words & _PAYMENT_WORDS:
        return "cash"
    return ai_value


@intent(
    "add_party",
    "A NEW customer or supplier, maybe with phone and old balance: opening_direction \"will_get\" = they owe "
    "the shop (\"pehle ke 2000 lene hain\"), \"will_give\" = the shop owes them (\"dene hain\").",
    fields=AddPartyFields,
    fields_hint=(
        '{"name": string | null (null when no name is written, e.g. "ek aur customer add karo"), '
        '"type": "customer" | "supplier" | null, "phone": string | null, '
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


@intent(
    "rename_party",
    "CHANGE the NAME of an existing customer / supplier (a typo). Not an entry's amount or note (edit_entry).",
    fields=RenamePartyFields,
    fields_hint='{"party_name": string (the name now), "new_name": string}',
    examples=["aleem ka naam saleem kardo", "urqan hatake furqan kardo"],
    needs_business=True,
    owner_only=True,
)
def rename_party(ctx: Context, fields: RenamePartyFields) -> Outcome:
    new = (fields.new_name or "").strip()
    # The new name must be written in the message: the AI never makes one up
    if not fields.party_name or not new or new.lower() not in ctx.text.lower():
        return Outcome("rename_party", t("rename_how", ctx.language))
    matches = _find(ctx, fields.party_name)
    if not matches:
        return Outcome("rename_party", t("party_not_found", ctx.language, name=fields.party_name))
    exact = [p for p in matches if p["name"].lower() == fields.party_name.strip().lower()]
    if len(exact) == 1:
        matches = exact
    if len(matches) > 1:
        return ask_choose_party(ctx, fields.party_name, matches, "rename", {"new_name": new})
    return _ask_rename(ctx, matches[0], new)


def _ask_rename(ctx: Context, party: dict, new: str) -> Outcome:
    new = tools.nice_name(new)
    taken = [p for p in _find(ctx, new, party["type"]) if p["name"].lower() == new.lower() and p["id"] != party["id"]]
    if taken:  # two parties can't share a name: an entry would not know which one
        return Outcome("rename_party", t("rename_exists", ctx.language, name=taken[0]["name"],
                                          type=_type_label(ctx.language, party["type"])))
    question = t("confirm_rename", ctx.language, old=party["name"], new=new)
    pending = PendingAction(kind="confirm_rename", language=ctx.language, expects="yes_no",
                            data={"account_id": str(party["id"]), "old": party["name"], "new": new})
    return Outcome("rename_party", question, pending=pending)


@pending_resolver("confirm_rename")
def resolve_confirm_rename(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("rename_party", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("rename_party", t("cancelled", ctx.language))
    business_id, data = _business_id(ctx), pending.data

    def commit(conn: Connection) -> str:
        name = tools.rename_party(conn, business_id, data["account_id"], data["new"])
        balance = tools.get_balance(conn, business_id, data["account_id"])
        renamed = t("party_renamed", ctx.language, old=data["old"], new=name)
        return f"{renamed}\n{balance_line(ctx.language, name, balance)}"

    return Outcome("rename_party", commit=commit)


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


_CUSTOMER_WORDS = {"customer", "customers", "costumer", "costumers", "grahak", "gahak", "gaahak", "گاہک", "گاہکوں"}
_SUPPLIER_WORDS = {"supplier", "suppliers", "suplier", "supliers", "sapplier", "vendor", "vendors", "wholesaler",
                   "dealer", "سپلائر", "سپلائرز"}
# Which side of the khata a question asks about. "give" = the shop owes them, "get" = they owe the shop.
_GIVE_SIDE = re.compile(
    r"\b(hum|ham|mujh|mjh|hamare|humare|hmare|mere|apne)\s*(pe|par|pr|per|upar|uper|oper)\b"
    r"|\bko\s+(dene|dena|deny|deney|dainay)\b"
    r"|\b(humne|hamne|hmne|maine|mene|mainy|hum\s+ne|ham\s+ne|mai\s+ne|main\s+ne)\b(\s+\w+)?\s+(dene|dena|deny)\b"
    r"|\b(we|i)\s+owe\b|\bpayable\b|ہم\s*پر|مجھ\s*پر|کو\s*دینے"
)
_GET_SIDE = re.compile(
    r"\b(se|say|sy|sey)\s+(lene|lena|leny|leney|lainay)\b"
    r"|\b(?<!hum\s)(?<!ham\s)(?<!mai\s)(?<!main\s)ne(\s+\w+)?\s+(dene|dena|deny)\b"
    r"|\bowes?\s+(me|us)\b|\breceivables?\b|سے\s*لینے"
)
_BARE_GIVE = re.compile(r"\b(dene|dena|deny|deney|dainay)\b|دینے")
_BARE_GET = re.compile(r"\b(lene|lena|leny|leney|lainay)\b|لینے")


def asked_party_type(text: str) -> str | None:
    """customer / supplier only when the user wrote that word (the AI guessed "supplier" for "hum pe udhaar")."""
    words = set(re.findall(r"\w+", text.lower()))
    customer, supplier = bool(words & _CUSTOMER_WORDS), bool(words & _SUPPLIER_WORDS)
    return ("customer" if customer else "supplier") if customer != supplier else None


def asked_side(text: str) -> tuple[str | None, bool]:
    """("give" | "get" | None, whether the text decided it). Both sides asked -> (None, True): show all."""
    text = text.lower()
    give, get = bool(_GIVE_SIDE.search(text)), bool(_GET_SIDE.search(text))
    if not give and not get:
        give, get = bool(_BARE_GIVE.search(text)), bool(_BARE_GET.search(text))
    if give and get:
        return None, True
    if give or get:
        return ("give" if give else "get"), True
    return None, False


@intent(
    "list_parties",
    "User asks for ALL parties' balances or totals: who owes the shop, whom the shop owes, customer/supplier list.",
    fields=ListPartiesFields,
    fields_hint=('{"type": "customer" | "supplier" | null, "side": "get" | "give" | null} '
                 '(give: the shop owes them, "hum pe kis ka udhaar"; get: they owe the shop)'),
    examples=["sab ka hisaab", "sab udhar dikhao", "kis kis se lene hain", "hum pe kis kis ka udhaar hai",
              "suppliers ko kitne dene hain", "customer list"],
    needs_business=True,
)
def list_parties(ctx: Context, fields: ListPartiesFields) -> Outcome:
    language = ctx.language
    party_type = asked_party_type(ctx.text)
    side, decided = asked_side(ctx.text)
    if not decided:
        side = fields.side  # no side words the code knows; the AI's reading, both totals are still shown
    with transaction() as conn:
        rows = tools.list_balances(conn, _business_id(ctx), party_type)
        if not rows and party_type:
            any_party = bool(tools.list_balances(conn, _business_id(ctx)))
    if not rows:
        if party_type and any_party:
            return Outcome("list_parties", t("no_parties_type", language, type=_type_label(language, party_type)))
        return Outcome("list_parties", t("no_parties", language))

    # All money is worked out here from the saved balances, never by the AI
    total_get = sum((r["balance"] for r in rows if r["balance"] > 0), Decimal(0))
    total_give = sum((-r["balance"] for r in rows if r["balance"] < 0), Decimal(0))
    get, give = format_rs(total_get), format_rs(total_give)
    if side == "give":
        rows = [r for r in rows if r["balance"] < 0]
    elif side == "get":
        rows = [r for r in rows if r["balance"] > 0]
    if side and not rows:
        return Outcome("list_parties", t(f"nobody_{side}", language, get=get, give=give))

    items = numbered([f"{r['name']} — {_short_balance(language, r['balance'])}" for r in rows[:10]])
    if len(rows) > 10:
        items += "\n" + t("list_more", language, n=len(rows) - 10)
    reply = t(f"party_list_{side}" if side else "party_list", language, get=get, give=give, items=items)
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
    if amount is None:  # "jitne ka sock hai": the item's sale price x count
        goods = shop_goods(ctx, answer, count_needed=False)
        if len(goods) == 1 and goods[0][0]["sale_price"] is not None:
            amount = goods[0][0]["sale_price"] * goods[0][1]
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
    "rename": ("rename_party", lambda ctx, party, data: _ask_rename(ctx, party, data["new_name"])),
})


for _mode, _intent in _DRAFT_INTENT.items():
    DRAFT_STEPS[_mode] = (_intent, next_step)
