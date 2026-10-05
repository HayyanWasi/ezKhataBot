"""Stock book intents: items, stock in / out (with the supplier and payment), reports.

The AI only picks one of these intents and fills its fields (item words, quantities,
rates as written). Everything else is code:
  - every quantity and rate must be written in the message (app/services/amounts.py)
  - items are matched against the shop's own list (app/tools/stock.py); an unknown
    word gets one AI guess ("jurab" -> Socks) that the user confirms, then it is remembered
  - stock never goes below 0: a stock out is re-checked inside the commit, with the items locked

A stock in / out is a "draft" like a cash entry: next_step() asks the ONE missing thing
(which item -> unit of a new item -> quantity -> payment -> supplier -> rate -> bank) or saves it.

Staff can view stock, and do stock in (cash / stock only) and stock out.
Items, prices, and stock bought on udhaar or through a bank are owner only.
"""

import re
from datetime import date
from decimal import Decimal

from psycopg import Connection

from app.ai.items import guess_item
from app.core.database import transaction
from app.core.dates import short_date, today
from app.db import crud
from app.handlers.money_steps import MONEY_KEYS, money_account, money_line, money_step
from app.handlers.party import balance_line
from app.schemas.khata import (
    AddItemFields,
    CreateBillFields,
    EditItemFields,
    ItemFields,
    PendingAction,
    StockInFields,
    StockLine,
    StockOutFields,
    StockReportFields,
)
from app.services import barcode, pdf
from app.services.amounts import confirmed_amount, format_rs, parse_amount_answer, parse_amounts
from app.services.answers import CASH_WORDS, ONLINE_WORDS, UDHAAR_WORDS, bought_by, parse_number, parse_yes_no, pick
from app.services.ocr import OCRError, read_text
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
from app.tools import party as party_tools
from app.tools import stock as tools

_DRAFT_INTENT = {"item_add": "add_item", "stock_in": "stock_in", "stock_out": "stock_out"}
_TEXT_LIMIT = 30  # lines in a text report; the PDF has everything


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _is_owner(ctx: Context) -> bool:
    return ctx.business["role"] == "owner"


def _today(ctx: Context) -> date:
    return today(ctx.business["timezone"])


def _title(word: str) -> str:
    word = " ".join(word.split())
    return word[:1].upper() + word[1:]


def fmt_qty(value: Decimal) -> str:
    """150 / 2.5 / 1,200 (no trailing zeros)."""
    value = Decimal(value)
    if value == value.to_integral():
        return f"{value:,.0f}"
    return f"{value.normalize():f}"


def _signed_qty(value: Decimal) -> str:
    return f"+{fmt_qty(value)}" if value > 0 else f"-{fmt_qty(-value)}"


# Common units: what shopkeepers write -> how we save it. Anything else is saved as written.
_UNITS = {
    "pcs": ("pcs", "pc", "piece", "pieces", "adad", "dana", "danay", "nag", "عدد", "پیس"),
    "kg": ("kg", "kgs", "kilo", "kilogram", "kilograms", "کلو"),
    "gram": ("g", "gm", "gram", "grams", "گرام"),
    "litre": ("l", "ltr", "litre", "liter", "litres", "liters", "لیٹر"),
    "ml": ("ml",),
    "darjan": ("darjan", "dozen", "dz", "درجن"),
    "meter": ("m", "meter", "metre", "meters", "میٹر"),
    "gaz": ("gaz", "yard", "گز"),
    "feet": ("ft", "feet", "foot", "فٹ"),
    "packet": ("packet", "packets", "pkt", "pack", "پیکٹ"),
    "carton": ("carton", "cartons", "ctn", "کارٹن"),
    "box": ("box", "boxes", "dabba", "dabbe", "ڈبہ"),
    "bori": ("bori", "boriyan", "bag", "bags", "بوری"),
    "bottle": ("bottle", "bottles", "botal", "بوتل"),
    "jora": ("jora", "joray", "pair", "pairs", "جوڑا"),
    "roll": ("roll", "rolls"),
    "set": ("set", "sets"),
}
_UNIT_BY_WORD = {word: unit for unit, words in _UNITS.items() for word in words}
UNIT_OPTIONS = ["pcs", "kg", "darjan", "litre", "meter", "packet"]


def normal_unit(text: str | None) -> str | None:
    if not text:
        return None
    word = " ".join(text.lower().strip(" .").split())
    return _UNIT_BY_WORD.get(word, word) or None


def _qty_of(text: str, value: object) -> Decimal | None:
    """A quantity the AI read, only if it is written in the message."""
    return confirmed_amount(text, value)


def _item_names(conn: Connection, business_id) -> list[str]:
    return [i["name"] for i in tools.list_items(conn, business_id)]


# ---------------------------------------------------------------------------
# Which item? (shared by every stock intent)
# ---------------------------------------------------------------------------

# purpose -> (intent name, fn(ctx, item_id, data) -> Outcome), called once the item is known
ITEM_HANDLERS: dict[str, tuple[str, object]] = {}


def _purpose_intent(purpose: str, data: dict) -> str:
    if purpose == "line":  # a stock in / out (or bill) draft
        return DRAFT_STEPS[data["draft"]["mode"]][0]
    return ITEM_HANDLERS[purpose][0]


def with_item(ctx: Context, word: str, purpose: str, data: dict, *, allow_new: bool = False,
              guessed: bool = False) -> Outcome:
    """Find the item the user means, asking when needed, then call the purpose's handler."""
    intent_name = _purpose_intent(purpose, data)
    with transaction() as conn:
        matches = tools.find_item(conn, ctx.business["id"], word)
        names = [] if matches else _item_names(conn, ctx.business["id"])
    if len(matches) == 1:
        return ITEM_HANDLERS[purpose][1](ctx, str(matches[0]["id"]), data)

    base = {"purpose": purpose, "word": word, "allow_new": allow_new, "data": data}
    if matches:
        options = [{"id": str(m["id"]), "name": m["name"]} for m in matches[:8]]
        labels = [f"{o['name']}" for o in options] + ([t("new_item_option", ctx.language)] if allow_new else [])
        pending = PendingAction(kind="choose_item", language=ctx.language, expects="choice",
                                data={**base, "options": options})
        return Outcome(intent_name, t("choose_item", ctx.language, word=word, options=numbered(labels)),
                       pending=pending)

    guess = None if guessed else guess_item(word, names)
    if guess:
        pending = PendingAction(kind="same_item", language=ctx.language, expects="yes_no",
                                data={**base, "name": guess})
        return Outcome(intent_name, t("ask_same_item", ctx.language, word=word, name=guess), pending=pending)
    return _no_item(ctx, word, purpose, data, allow_new)


def _no_item(ctx: Context, word: str, purpose: str, data: dict, allow_new: bool) -> Outcome:
    if allow_new:
        return ITEM_HANDLERS[purpose][1](ctx, None, data)  # None = a new item named `word`
    return Outcome(_purpose_intent(purpose, data), t("item_not_found", ctx.language, name=word))


def _remember(ctx: Context, word: str, item_id: str) -> Outcome:
    """Save that `word` means this item (runs in the commit, before what follows)."""
    business_id = ctx.business["id"]

    def commit(conn: Connection) -> str:
        tools.remember_word(conn, business_id, word, item_id)
        return ""

    return Outcome("remember_item", commit=commit)


@pending_resolver("choose_item")
def resolve_choose_item(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    data, options = pending.data, pending.data["options"]
    handler = ITEM_HANDLERS[data["purpose"]][1]
    if data["allow_new"] and parse_number(answer) == len(options) + 1:
        return handler(ctx, None, data["data"])
    chosen = pick(answer, options, lambda o: o["name"])
    if chosen is None:
        labels = [o["name"] for o in options] + ([t("new_item_option", ctx.language)] if data["allow_new"] else [])
        question = t("invalid_choice", ctx.language, n=len(labels), options=numbered(labels))
        return Outcome(_purpose_intent(data["purpose"], data["data"]), question, pending=pending)
    return chain(_remember(ctx, data["word"], chosen["id"]), handler(ctx, chosen["id"], data["data"]))


@pending_resolver("same_item")
def resolve_same_item(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    data = pending.data
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome(_purpose_intent(data["purpose"], data["data"]), t("answer_yes_no", ctx.language),
                       pending=pending)
    if not yes:
        return _no_item(ctx, data["word"], data["purpose"], data["data"], data["allow_new"])
    with transaction() as conn:
        found = [i for i in tools.find_item(conn, ctx.business["id"], data["name"]) if i["name"] == data["name"]]
    if not found:  # deleted meanwhile
        return Outcome(_purpose_intent(data["purpose"], data["data"]),
                       t("item_not_found", ctx.language, name=data["name"]))
    item_id = str(found[0]["id"])
    return chain(_remember(ctx, data["word"], item_id), ITEM_HANDLERS[data["purpose"]][1](ctx, item_id, data["data"]))


# ---------------------------------------------------------------------------
# Add an item (owner)
# ---------------------------------------------------------------------------


def _add_step(ctx: Context, draft: dict) -> Outcome:
    item = draft["item"]
    with transaction() as conn:
        same = [i for i in tools.find_item(conn, ctx.business["id"], item["name"])
                if tools._singular(i["name"].lower()) == tools._singular(item["name"].lower())]
    if same:
        found = same[0]
        return Outcome("add_item", t("item_exists", ctx.language, name=found["name"], qty=fmt_qty(found["qty"]),
                                      unit=found["unit"]))
    if not item["unit"]:
        question = t("ask_unit", ctx.language, name=item["name"], options=numbered(UNIT_OPTIONS))
        return ask_draft(ctx, "stock_unit", "choice_or_name", draft, question, line=-1)
    return _save_item(ctx, draft)


def _save_item(ctx: Context, draft: dict) -> Outcome:
    language, item = ctx.language, draft["item"]
    business_id, user_id = ctx.business["id"], ctx.user["id"]

    def commit(conn: Connection) -> str:
        category = item["category"]
        if category:  # use the shop's existing spelling of a category
            existing = {(i["category"] or "").lower(): i["category"] for i in tools.list_items(conn, business_id)}
            category = existing.get(category.lower(), _title(category))
        created = tools.create_item(
            conn, business_id, name=_title(item["name"]), unit=item["unit"], user_id=user_id, category=category,
            sale_price=_dec(item["sale_price"]), purchase_price=_dec(item["purchase_price"]),
            low_stock_level=_dec(item["low_stock_level"]), barcode=item.get("barcode"),
        )
        qty = _dec(item["qty"])
        if qty:
            tools.record_stock(
                conn, business_id=business_id, type="stock_opening", entry_date=_today(ctx),
                moves=[(created["id"], qty, _dec(item["purchase_price"]))], legs=[], note=None,
                message_id=ctx.message_id, user_id=user_id,
            )
        lines = [t("item_added", language, name=created["name"], category=f" · {category}" if category else "")]
        lines.append(_item_line(language, created, qty or Decimal(0)))
        if category:
            lines.append(t("item_category_hint", language))
        return "\n".join(lines)

    return Outcome("add_item", commit=commit)


def _dec(value) -> Decimal | None:
    return Decimal(value) if value not in (None, "") else None


def _item_line(language: str, item: dict, qty: Decimal) -> str:
    """📦 Stock: 100 pcs · Sale Rs 30 · Purchase Rs 20"""
    parts = [t("stock_qty", language, qty=fmt_qty(qty), unit=item["unit"])]
    if item.get("sale_price") is not None:
        parts.append(t("sale_price", language, amount=format_rs(item["sale_price"])))
    if item.get("purchase_price") is not None:
        parts.append(t("purchase_price", language, amount=format_rs(item["purchase_price"])))
    return "📦 " + " · ".join(parts)


@intent(
    "add_item",
    "A NEW stock item, with unit, sale price (\"30 ki bechta hun\"), purchase price (\"20 ki aati hai\"), qty and"
    " low-stock alert if said. category: your guess, a short English shop category (Grocery, Clothing ...).",
    fields=AddItemFields,
    fields_hint=(
        '{"name": string, "unit": string | null (pcs, kg, darjan, litre ... as written), "category": string | null, '
        '"sale_price": number | null, "purchase_price": number | null, "qty": number | null, '
        '"low_stock_level": number | null}'
    ),
    examples=["socks add karo 30 ki bechta hun 20 ki aati hai 100 pcs", "naya item cheeni kg 150 rupay",
              "add item Surf Excel packet sale 250"],
    needs_business=True,
    owner_only=True,
)
def add_item(ctx: Context, fields: AddItemFields) -> Outcome:
    text = ctx.text
    item = {
        "name": _title(fields.name), "unit": normal_unit(fields.unit), "category": fields.category,
        "sale_price": _str(confirmed_amount(text, fields.sale_price)),
        "purchase_price": _str(confirmed_amount(text, fields.purchase_price)),
        "qty": _str(_qty_of(text, fields.qty) or _counted_qty(text)),
        "low_stock_level": _str(_qty_of(text, fields.low_stock_level)),
    }
    draft = {"mode": "item_add", "item": item, "queue": []}
    return _add_step(ctx, draft)


def _counted_qty(text: str) -> Decimal | None:
    """A count like "5 pcs" or "10 kg" written in the message, when the AI left the quantity out (one only)."""
    units = "|".join(re.escape(u) for aliases in _UNITS.values() for u in sorted(aliases, key=len, reverse=True))
    found = re.findall(rf"(?<![\w.])(\d+(?:\.\d+)?)\s*(?:{units})(?![\w])", text, re.IGNORECASE)
    return Decimal(found[0]) if len(found) == 1 else None


def _str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


# ---------------------------------------------------------------------------
# Stock in / out drafts
# ---------------------------------------------------------------------------


def new_stock_draft(mode: str, lines: list[StockLine], text: str, **values) -> dict:
    """Everything in a draft is JSON-safe: it is stored in the pending question."""
    draft = {
        "mode": mode, "lines": [
            {"word": line.name, "qty": _str(_qty_of(text, line.qty)), "unit": normal_unit(line.unit),
             "rate": _str(confirmed_amount(text, line.rate)), "item_id": None, "name": None, "item_unit": None,
             "purchase_price": None, "sale_price": None, "new": False}
            for line in lines if line.name
        ],
        "supplier_name": None, "account_id": None, "new_supplier": False, "pay": None, "paid_amount": None,
        "date": None, "note": None, "queue": [], "source_message_id": None, "source_line": 0,
        **MONEY_KEYS, "via": None,
    }
    draft.update(values)
    return draft


def next_step(ctx: Context, draft: dict) -> Outcome:
    if draft["mode"] == "item_add":
        return _add_step(ctx, draft)
    language, mode = ctx.language, draft["mode"]
    if not draft["lines"]:
        return Outcome(mode, t("stock_which_items", language))

    for n, line in enumerate(draft["lines"]):
        if line["item_id"] is None and not line["new"]:
            allow_new = mode == "stock_in" and _is_owner(ctx)
            return with_item(ctx, line["word"], "line", {"draft": draft, "line": n}, allow_new=allow_new)
        if line["new"] and not line["unit"]:
            question = t("ask_unit_new", language, name=line["name"], options=numbered(UNIT_OPTIONS))
            return ask_draft(ctx, "stock_unit", "choice_or_name", draft, question, line=n)
        if line["qty"] is None:
            unit = line["unit"] if line["new"] else line["item_unit"]
            question = t("ask_stock_qty", language, name=line["name"], unit=unit)
            return ask_draft(ctx, "stock_qty", "amount", draft, question, line=n)

    if mode == "stock_out":
        short = _shortage(ctx, draft)
        return Outcome("stock_out", short) if short else _save(ctx, draft)

    # Stock in: how was it paid?
    if draft["pay"] is None:
        question = t("ask_stock_pay", language, items=_items_text(draft))
        return ask_draft(ctx, "stock_pay", "choice", draft, question)
    if not _is_owner(ctx) and (draft["pay"] in ("udhaar", "bank") or draft["via"] == "bank"):
        return Outcome("stock_in", t("stock_owner_only_money", language))
    if draft["pay"] == "udhaar" and draft["account_id"] is None and not draft["new_supplier"]:
        question = _supplier_step(ctx, draft)
        if question:
            return question
    if draft["pay"] != "none":
        for n, line in enumerate(draft["lines"]):
            if line["rate"] is None and line["purchase_price"] is None:
                question = t("ask_stock_rate", language, name=line["name"],
                             unit=line["unit"] if line["new"] else line["item_unit"])
                return ask_draft(ctx, "stock_rate", "amount", draft, question, line=n)

    draft["via"] = {"cash": "cash", "bank": "bank"}.get(draft["pay"])
    if draft["pay"] == "udhaar" and draft["paid_amount"]:  # part paid now, the rest udhaar
        draft["via"] = "bank" if draft["bank_name"] else "cash"
    question = money_step(ctx, draft)  # which bank? opening cash?
    if question:
        return question
    return _save(ctx, draft)


def _items_text(draft: dict) -> str:
    return ", ".join(
        f"{fmt_qty(Decimal(line['qty']))} {line['unit'] if line['new'] else line['item_unit']} {line['name']}"
        for line in draft["lines"]
    )


def _shortage(ctx: Context, draft: dict) -> str | None:
    """The refusal text if any item has less stock than asked for, else None."""
    ids = [line["item_id"] for line in draft["lines"]]
    with transaction() as conn:
        stock = tools.stock_of(conn, ctx.business["id"], ids)
    return _short_text(ctx.language, draft["lines"], stock)


def _short_text(language: str, lines: list[dict], stock: dict[str, Decimal]) -> str | None:
    wanted: dict[str, Decimal] = {}
    for line in lines:
        wanted[line["item_id"]] = wanted.get(line["item_id"], Decimal(0)) + Decimal(line["qty"])
    for line in lines:
        have = stock.get(line["item_id"], Decimal(0))
        if wanted[line["item_id"]] > have:
            return t("stock_short", language, name=line["name"], qty=fmt_qty(have), unit=line["item_unit"])
    return None


def _supplier_step(ctx: Context, draft: dict) -> Outcome | None:
    """Find the supplier (asking which one / whether to add a new one). None = found."""
    language, name = ctx.language, draft["supplier_name"]
    if not name:
        return ask_draft(ctx, "stock_supplier", "choice_or_name", draft, t("ask_stock_supplier", language))
    with transaction() as conn:
        matches = party_tools.find_parties(conn, ctx.business["id"], name)
    suppliers = [m for m in matches if m["type"] == "supplier"] or matches
    if len(suppliers) == 1:
        draft["account_id"], draft["supplier_name"] = str(suppliers[0]["id"]), suppliers[0]["name"]
        return None
    if suppliers:
        options = [{"id": str(p["id"]), "name": p["name"]} for p in suppliers]
        labels = [p["name"] for p in options] + [t("new_party_option", language)]
        question = t("choose_party", language, name=name, options=numbered(labels))
        return ask_draft(ctx, "stock_choose_supplier", "choice", draft, question, options=options)
    return ask_draft(ctx, "stock_new_supplier", "yes_no", draft, t("confirm_new_supplier", language, name=_title(name)))


def _save(ctx: Context, draft: dict) -> Outcome:
    language, mode = ctx.language, draft["mode"]
    business_id, user_id = ctx.business["id"], ctx.user["id"]

    def commit(conn: Connection) -> str:
        entry_date = date.fromisoformat(draft["date"])
        lines = [dict(line) for line in draft["lines"]]
        for line in lines:
            if line["new"]:
                created = tools.create_item(conn, business_id, name=line["name"], unit=line["unit"], user_id=user_id,
                                            purchase_price=_dec(line["rate"]))
                line["item_id"], line["item_unit"] = str(created["id"]), created["unit"]
        ids = [line["item_id"] for line in lines]
        tools.lock_items(conn, business_id, ids)
        before = tools.stock_of(conn, business_id, ids)
        if mode == "stock_out":
            short = _short_text(language, lines, before)
            if short:  # another message took the stock meanwhile
                return short

        out = mode == "stock_out"
        moves, total = [], Decimal(0)
        for line in lines:
            qty = Decimal(line["qty"])
            rate = _dec(line["rate"]) if line["rate"] is not None else _dec(line["purchase_price"])
            moves.append((line["item_id"], -qty if out else qty, rate))
            if not out and draft["pay"] != "none":
                total += qty * rate

        legs, money, supplier_id = [], None, None
        if not out and draft["pay"] != "none" and total > 0:
            paid = min(Decimal(draft["paid_amount"]), total) if draft["paid_amount"] else Decimal(0)
            if draft["pay"] in ("cash", "bank"):
                paid = total
            if paid:
                money = money_account(conn, ctx, draft, entry_date)
                legs.append((money[0], -paid))
            if draft["pay"] == "udhaar" and total > paid:
                supplier_id = draft["account_id"]
                if supplier_id is None:
                    supplier_id = party_tools.create_party(conn, business_id, "supplier",
                                                           _title(draft["supplier_name"]), None, user_id)["id"]
                legs.append((supplier_id, -(total - paid)))  # the shop owes the supplier

        kind = "stock_out" if out else ("purchase" if legs else "stock_in")
        note = draft["note"]
        if not out and draft["supplier_name"] and supplier_id is None:
            note = note or _title(draft["supplier_name"])
        tools.record_stock(
            conn, business_id=business_id, type=kind, entry_date=entry_date, moves=moves, legs=legs, note=note,
            message_id=draft["source_message_id"] or ctx.message_id, user_id=user_id,
            source_line=draft["source_line"],
        )

        after = tools.stock_of(conn, business_id, ids)
        reply = [t("stock_out_saved" if out else "stock_in_saved", language, date=short_date(entry_date))]
        items = {str(i["id"]): i for i in tools.list_items(conn, business_id) if str(i["id"]) in ids}
        for item_id, qty, _ in moves:
            item = items[item_id]
            reply.append(f"📦 {item['name']}: {_signed_qty(qty)} → {fmt_qty(after[item_id])} {item['unit']}")
        if legs:
            reply.append(t("stock_total", language, amount=format_rs(total)))
        if supplier_id is not None:
            name = party_tools.get_party(conn, business_id, supplier_id)["name"]
            reply.append(balance_line(language, name, party_tools.get_balance(conn, business_id, supplier_id)))
        if money:
            reply.append(money_line(language, money[1], money[2], money_tools.get_balance(conn, business_id, money[0])))
        reply += low_warnings(conn, ctx, items, before, after)
        return "\n".join(reply)

    return Outcome(_DRAFT_INTENT[mode], commit=commit)


def low_warnings(conn: Connection, ctx: Context, items: dict[str, dict], before: dict[str, Decimal],
                 after: dict[str, Decimal]) -> list[str]:
    """Inside the commit: a warning for every item at or below its level. When staff took an item
    across its level, the owner is told too."""
    out = [i for i in items if after[i] <= 0]  # always warned, with or without a level
    low = [i for i, item in items.items()
           if i not in out and item["low_stock_level"] is not None and after[i] <= item["low_stock_level"]]
    level = {i: items[i]["low_stock_level"] if items[i]["low_stock_level"] is not None else Decimal(0) for i in items}
    crossed = [i for i in out + low if before.get(i, Decimal(0)) > level[i]]
    if crossed and not _is_owner(ctx):
        _tell_owner(conn, ctx, [items[i] for i in crossed], after)
    return ([t("out_of_stock_warning", ctx.language, name=items[i]["name"]) for i in out]
            + [t("low_stock_warning", ctx.language, name=items[i]["name"], qty=fmt_qty(after[i]),
                 unit=items[i]["unit"]) for i in low])


def _tell_owner(conn: Connection, ctx: Context, items: list[dict], after: dict[str, Decimal]) -> None:
    """Staff took an item below its level: the owner gets a message now (through the reminder sender)."""
    owner_id = ctx.business["owner_id"]
    language = crud.get_language_preference(conn, owner_id) or ctx.language
    conversation = crud.get_or_create_conversation(conn, owner_id, ctx.conversation["channel"])
    text = t("low_stock_owner", language, business=ctx.business["name"], by=ctx.user.get("name") or "",
             items=", ".join(f"{i['name']} {fmt_qty(after[str(i['id'])])} {i['unit']}" for i in items))
    crud.insert_bot_reply(conn, conversation["id"], None, text, ctx.business["id"], "notice")


def _pay_from(text: str, fields: StockInFields) -> tuple[str | None, str | None]:
    """(pay, paid_amount): udhaar | cash | bank | none | None (ask). Words in the message decide; the AI's
    paid_via is only trusted for cash / bank, so "50 socks aae" (nothing said) is always asked."""
    words = set(re.findall(r"\w+", text.lower()))
    paid = confirmed_amount(text, fields.paid_amount)
    if words & UDHAAR_WORDS or (paid and fields.supplier_name):
        return "udhaar", _str(paid)
    if fields.bank_name or words & ONLINE_WORDS:
        return "bank", None
    if words & CASH_WORDS:
        return "cash", None
    if {"sirf", "stock"} <= words or {"only", "stock"} <= words:
        return "none", None
    if fields.paid_via in ("cash", "bank"):
        return fields.paid_via, None
    if fields.supplier_name:  # "Bilal se 50 socks liye": goods from a supplier, like a khata entry
        return "udhaar", None
    return None, None


@intent(
    "stock_in",
    "ITEMS with quantities came into stock (bought, a delivery): \"50 socks aae\", \"Bilal se 20 bori cheeni "
    "li\". items: each with qty, unit and rate (price per unit, \"20 wale\"). paid_via: \"udhaar\" | \"cash\" | "
    "\"bank\" | \"none\" (only add stock) | null. paid_amount: paid now when the rest is udhaar. Money with no "
    "item counts (\"Bilal se 5000 ka maal liya\") is party_entry; a thing for own use with a price (\"chai 200\")"
    " is cash_entry.",
    fields=StockInFields,
    fields_hint=(
        '{"items": [{"name": string, "qty": number | null, "unit": string | null, "rate": number | null}], '
        '"supplier_name": string | null, "paid_via": "udhaar" | "cash" | "bank" | "none" | null, '
        '"paid_amount": number | null, "bank_name": string | null, "date": "YYYY-MM-DD" | null}'
    ),
    examples=["50 socks aae", "Bilal se 50 socks 20 wale udhaar liye", "10 kg cheeni 150 ke cash mein li",
              "Bilal se 100 pcs liye 500 cash diye baqi udhaar", "stock in 20 packet surf"],
    needs_business=True,
)
def stock_in(ctx: Context, fields: StockInFields) -> Outcome:
    entry_date = fields.date or _today(ctx)
    if entry_date > _today(ctx):
        return Outcome("stock_in", t("future_date", ctx.language))
    if _sold_to(ctx, fields):  # "Naveed ne 1 cooler udhaar li": Naveed is a customer, this is a sale
        from app.handlers import bills  # bills imports this module

        words = set(re.findall(r"\w+", ctx.text.lower()))
        bill = CreateBillFields(customer_name=fields.supplier_name, items=fields.items, date=fields.date,
                                paid_via="udhaar" if words & UDHAAR_WORDS else None)
        return bills.create_bill(ctx, bill)
    if _adds_new_item(ctx, fields):  # "fridge add krdo stocks mein 3": a NEW item, not goods from a supplier
        line = fields.items[0]
        return add_item(ctx, AddItemFields(name=line.name, unit=line.unit, qty=line.qty))
    pay, paid = _pay_from(ctx.text, fields)
    draft = new_stock_draft(
        "stock_in", fields.items, ctx.text, supplier_name=fields.supplier_name, pay=pay, paid_amount=paid,
        date=entry_date.isoformat(), bank_name=fields.bank_name,
    )
    return next_step(ctx, draft)


def _sold_to(ctx: Context, fields: StockInFields) -> bool:
    """'<name> ne ... udhaar ki / li / khareedi' about the shop's own items: <name> bought them (a sale),
    unlike '<name> ne 50 socks diye / bheje' or '<name> se aaye' (goods from a supplier)."""
    if ctx.business["role"] != "owner" or not bought_by(ctx.text, fields.supplier_name):
        return False
    with transaction() as conn:
        return all(line.name and tools.find_item(conn, ctx.business["id"], line.name, partial=False)
                   for line in fields.items)


def _adds_new_item(ctx: Context, fields: StockInFields) -> bool:
    """One item the shop doesn't have yet, with "add" written and no supplier or payment: add the item."""
    if ctx.business["role"] != "owner" or len(fields.items) != 1 or not fields.items[0].name:
        return False
    if fields.supplier_name or fields.paid_via:
        return False
    if not re.search(r"\badd\b|ایڈ", ctx.text, re.IGNORECASE):
        return False
    with transaction() as conn:
        return not tools.find_item(conn, ctx.business["id"], fields.items[0].name, partial=False)


@intent(
    "stock_out",
    "ITEMS out of stock WITHOUT a sale: kharab, muft, used, lost, returned to the supplier, \"5 socks nikale\"."
    " items: each with qty and unit. reason: as written.",
    fields=StockOutFields,
    fields_hint=(
        '{"items": [{"name": string, "qty": number | null, "unit": string | null, "rate": null}], '
        '"reason": string | null, "date": "YYYY-MM-DD" | null}'
    ),
    examples=["5 socks kharab ho gae", "2 packet surf muft diye", "stock out 3 kg cheeni", "5 socks nikale"],
    needs_business=True,
)
def stock_out(ctx: Context, fields: StockOutFields) -> Outcome:
    entry_date = fields.date or _today(ctx)
    if entry_date > _today(ctx):
        return Outcome("stock_out", t("future_date", ctx.language))
    draft = new_stock_draft("stock_out", fields.items, ctx.text, date=entry_date.isoformat(), note=fields.reason)
    return next_step(ctx, draft)


def _line_item(ctx: Context, item_id: str | None, data: dict) -> Outcome:
    """The item of one draft line is known (or it is a new item): go on with the draft."""
    draft = dict(data["draft"])
    draft["lines"] = [dict(line) for line in draft["lines"]]
    line = draft["lines"][data["line"]]
    if item_id is None:
        line["new"], line["name"] = True, _title(line["word"])
    else:
        with transaction() as conn:
            item = tools.get_item(conn, ctx.business["id"], item_id)
        line["item_id"], line["name"], line["item_unit"] = item_id, item["name"], item["unit"]
        line["purchase_price"] = _str(item["purchase_price"])
        line["sale_price"] = _str(item["sale_price"])
    return continue_draft(ctx, draft)


# ---------------------------------------------------------------------------
# Answers to the draft's questions
# ---------------------------------------------------------------------------


def _draft(pending: PendingAction) -> dict:
    draft = dict(pending.data["draft"])
    draft["lines"] = [dict(line) for line in draft.get("lines", [])]
    return draft


def _retry(ctx: Context, pending: PendingAction, question: str) -> Outcome:
    return Outcome(DRAFT_STEPS[pending.data["draft"]["mode"]][0], question, pending=pending)


@pending_resolver("stock_unit")
def resolve_stock_unit(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    number = parse_number(answer)
    if number is not None:
        unit = UNIT_OPTIONS[number - 1] if 1 <= number <= len(UNIT_OPTIONS) else None
    else:
        unit = normal_unit(answer)
    if not unit:
        return _retry(ctx, pending, t("invalid_choice", ctx.language, n=len(UNIT_OPTIONS),
                                      options=numbered(UNIT_OPTIONS)))
    draft, line = _draft(pending), pending.data["line"]
    if line == -1:
        draft["item"] = {**draft["item"], "unit": unit}
    else:
        draft["lines"][line]["unit"] = unit
    return next_step(ctx, draft)


def _number_answer(answer: str) -> Decimal | None:
    value = parse_amount_answer(answer)
    if value is None:
        values = parse_amounts(answer)
        value = values[0] if len(values) == 1 else None
    return value


@pending_resolver("stock_qty")
def resolve_stock_qty(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft, line = _draft(pending), pending.data["line"]
    qty = _number_answer(answer)
    if qty is not None:
        draft["lines"][line]["qty"] = str(qty)
    return continue_draft(ctx, draft)  # asks again if still missing


@pending_resolver("stock_rate")
def resolve_stock_rate(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft, line = _draft(pending), pending.data["line"]
    rate = _number_answer(answer)
    if rate is not None:
        draft["lines"][line]["rate"] = str(rate)
    return continue_draft(ctx, draft)


_PAY_CHOICES = {1: "udhaar", 2: "cash", 3: "bank", 4: "none"}


@pending_resolver("stock_pay")
def resolve_stock_pay(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    words = set(re.findall(r"\w+", answer.lower()))
    pay = _PAY_CHOICES.get(parse_number(answer) or 0)
    if pay is None:
        if words & UDHAAR_WORDS:
            pay = "udhaar"
        elif words & CASH_WORDS:
            pay = "cash"
        elif words & (ONLINE_WORDS | {"bank"}):
            pay = "bank"
        elif words & {"sirf", "stock", "none"}:
            pay = "none"
    draft["pay"] = pay
    return next_step(ctx, draft)  # asks again if still unknown


@pending_resolver("stock_supplier")
def resolve_stock_supplier(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    draft["supplier_name"] = answer.strip()
    return next_step(ctx, draft)


@pending_resolver("stock_choose_supplier")
def resolve_stock_choose_supplier(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft, options = _draft(pending), pending.data["options"]
    if parse_number(answer) == len(options) + 1:  # a new supplier with the same name
        draft["new_supplier"] = True
        return next_step(ctx, draft)
    chosen = pick(answer, options, lambda p: p["name"])
    if chosen is None:
        labels = [p["name"] for p in options] + [t("new_party_option", ctx.language)]
        return _retry(ctx, pending, t("invalid_choice", ctx.language, n=len(labels), options=numbered(labels)))
    draft["account_id"], draft["supplier_name"] = chosen["id"], chosen["name"]
    return next_step(ctx, draft)


@pending_resolver("stock_new_supplier")
def resolve_stock_new_supplier(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return _retry(ctx, pending, t("answer_yes_no", ctx.language))
    if not yes:
        return Outcome("stock_in", t("image_cancelled", ctx.language))
    draft = _draft(pending)
    draft["new_supplier"] = True
    return next_step(ctx, draft)


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _period(start: date, end: date) -> str:
    return short_date(start) if start == end else f"{short_date(start)} – {short_date(end)}"


@intent(
    "stock_report",
    "STOCK: the list (\"stock dikhao\"), rates, low stock, value, the stock in / out report for a period, or "
    "ONE item (\"socks kitne hain\"). kind: list | rates | low | value | in | out | item. item: the item word.",
    fields=StockReportFields,
    fields_hint=(
        '{"kind": "list" | "rates" | "low" | "value" | "in" | "out" | "item", "item": string | null, '
        '"start_date": "YYYY-MM-DD" | null, "end_date": "YYYY-MM-DD" | null, "pdf": true | false}'
    ),
    examples=["stock dikhao", "rate list", "kaunsa maal kam hai", "stock ki value", "September ka stock in report",
              "socks kitne hain", "stock PDF bhejo"],
    needs_business=True,
)
def stock_report(ctx: Context, fields: StockReportFields) -> Outcome:
    data = {"kind": fields.kind, "start": _iso(fields.start_date), "end": _iso(fields.end_date),
            "pdf": bool(fields.pdf)}
    if fields.kind == "item" and not fields.item:
        data["kind"] = "list"
    if fields.item and data["kind"] in ("item", "in", "out"):
        return with_item(ctx, fields.item, "report", data)
    return _report(ctx, None, data)


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _report(ctx: Context, item_id: str | None, data: dict) -> Outcome:
    language, business_id, kind = ctx.language, ctx.business["id"], data["kind"]
    with transaction() as conn:
        if kind == "item":
            item = tools.get_item(conn, business_id, item_id)
            moves = tools.item_moves(conn, business_id, item_id)
            return Outcome("stock_report", _item_detail(language, item, moves))
        if kind in ("in", "out"):
            day = _today(ctx)
            end = min(date.fromisoformat(data["end"]) if data["end"] else day, day)
            start = date.fromisoformat(data["start"]) if data["start"] else end.replace(day=1)
            rows = tools.moves_report(conn, business_id, kind, start, end, item_id)
            item = tools.get_item(conn, business_id, item_id) if item_id else None
            return _moves_reply(ctx, kind, rows, start, end, item, data["pdf"])
        items = tools.low_items(conn, business_id) if kind == "low" else tools.list_items(conn, business_id)
        has_items = bool(items) or bool(tools.list_items(conn, business_id))

    if not has_items:
        return Outcome("stock_report", t("no_items", language))
    if kind == "low" and not items:
        return Outcome("stock_report", t("no_low_stock", language))
    lines = [_report_line(language, kind, i) for i in items]
    title = t(f"stock_report_{kind}", language, n=len(items))
    body = numbered(lines[:_TEXT_LIMIT])
    if len(lines) > _TEXT_LIMIT:
        body += "\n" + t("report_more", language, n=len(lines) - _TEXT_LIMIT)
    reply = f"{title}\n{body}"
    if kind == "value":
        total = sum((i["qty"] * i["purchase_price"] for i in items if i["purchase_price"] and i["qty"] > 0),
                    Decimal(0))
        reply += "\n" + t("stock_value_total", language, amount=format_rs(total))
    attachment = pdf.stock_pdf(ctx.business, kind, items) if data["pdf"] else None
    return Outcome("stock_report", reply, attachment=attachment)


def _report_line(language: str, kind: str, item: dict) -> str:
    qty = f"{fmt_qty(item['qty'])} {item['unit']}"
    if kind == "rates":
        sale = format_rs(item["sale_price"]) if item["sale_price"] is not None else "-"
        purchase = format_rs(item["purchase_price"]) if item["purchase_price"] is not None else "-"
        return t("rate_line", language, name=item["name"], sale=sale, purchase=purchase)
    if kind == "value":
        if item["purchase_price"] is None:
            return t("value_line_no_price", language, name=item["name"], qty=qty)
        value = item["qty"] * item["purchase_price"] if item["qty"] > 0 else Decimal(0)
        return f"{item['name']} — {qty} × {format_rs(item['purchase_price'])} = {format_rs(value)}"
    if kind == "low":
        return t("low_line", language, name=item["name"], qty=qty, level=fmt_qty(item["low_stock_level"]))
    return f"{item['name']} — {qty}"


def _item_detail(language: str, item: dict, moves: list[dict]) -> str:
    lines = [f"*{item['name']}*" + (f" · {item['category']}" if item["category"] else ""), _item_line(language, item, item["qty"])]
    if item["purchase_price"] is not None and item["qty"] > 0:
        lines.append(t("stock_value_total", language, amount=format_rs(item["qty"] * item["purchase_price"])))
    if item["low_stock_level"] is not None:
        lines.append(t("low_level_line", language, level=fmt_qty(item["low_stock_level"]), unit=item["unit"]))
    if moves:
        lines.append("")
        for m in moves:
            lines.append(f"{short_date(m['transaction_date'])} · {t('move_' + m['transaction_type'], language)} "
                         f"{_signed_qty(m['qty'])}")
    return "\n".join(lines)


def _moves_reply(ctx: Context, kind: str, rows: list[dict], start: date, end: date, item: dict | None,
                 as_pdf: bool) -> Outcome:
    language = ctx.language
    name = f" · {item['name']}" if item else ""
    if not rows:
        return Outcome("stock_report", t("no_stock_moves", language, period=_period(start, end)))
    total_qty = sum((abs(r["qty"]) for r in rows), Decimal(0))
    amount = sum((abs(r["qty"]) * r["rate"] for r in rows if r["rate"] is not None), Decimal(0))
    lines = [
        f"{short_date(r['transaction_date'])} · {r['name']} {fmt_qty(abs(r['qty']))} {r['unit']}"
        + (f" × {format_rs(r['rate'])}" if r["rate"] is not None else "")
        + (f" · {r['party']}" if r["party"] else "")
        + (f" · Bill #{r['bill_no']}" if r.get("bill_no") else "")
        for r in rows
    ]
    body = "\n".join(lines[-_TEXT_LIMIT:])
    reply = t(f"stock_{kind}_report", language, period=_period(start, end), name=name, n=len(rows),
              amount=format_rs(amount)) + "\n" + body
    if item and total_qty:
        reply += "\n" + t("report_total_qty", language, qty=fmt_qty(total_qty), unit=item["unit"])
    attachment = pdf.stock_moves_pdf(ctx.business, kind, rows, start, end) if as_pdf else None
    return Outcome("stock_report", reply, attachment=attachment)


# ---------------------------------------------------------------------------
# Edit / delete an item (owner), and its photo
# ---------------------------------------------------------------------------


@intent(
    "edit_item",
    "CHANGE an existing item: sale price / rate, purchase price, name, unit, category or low-stock alert.",
    fields=EditItemFields,
    fields_hint=(
        '{"item": string, "new_name": string | null, "unit": string | null, "category": string | null, '
        '"sale_price": number | null, "purchase_price": number | null, "low_stock_level": number | null}'
    ),
    examples=["socks ka rate 35 karo", "cheeni ki khareed 140 ho gayi", "socks ka alert 10 pe lagao",
              "socks ki category Kapre karo"],
    needs_business=True,
    owner_only=True,
)
def edit_item(ctx: Context, fields: EditItemFields) -> Outcome:
    text = ctx.text
    changes = {
        "name": _title(fields.new_name) if fields.new_name else None,
        "unit": normal_unit(fields.unit),
        "category": _title(fields.category) if fields.category else None,
        "sale_price": _str(confirmed_amount(text, fields.sale_price)),
        "purchase_price": _str(confirmed_amount(text, fields.purchase_price)),
        "low_stock_level": _str(_qty_of(text, fields.low_stock_level)),
    }
    changes = {k: v for k, v in changes.items() if v is not None}
    if not changes:
        return Outcome("edit_item", t("edit_item_nothing", ctx.language))
    return with_item(ctx, fields.item, "edit", {"changes": changes})


_CHANGE_LABELS = {"name": "field_name", "unit": "field_unit", "category": "field_category",
                  "sale_price": "field_sale", "purchase_price": "field_purchase", "low_stock_level": "field_alert"}


def _ask_edit_item(ctx: Context, item_id: str, data: dict) -> Outcome:
    language = ctx.language
    with transaction() as conn:
        item = tools.get_item(conn, ctx.business["id"], item_id)
    changes = []
    for key, new in data["changes"].items():
        old = item[key]
        if key in ("sale_price", "purchase_price"):
            old, new = (format_rs(old) if old is not None else "-"), format_rs(Decimal(new))
        elif key == "low_stock_level":
            old, new = (fmt_qty(old) if old is not None else "-"), fmt_qty(Decimal(new))
        changes.append(f"{t(_CHANGE_LABELS[key], language)}: {old or '-'} → {new}")
    pending = PendingAction(kind="confirm_edit_item", language=language, expects="yes_no",
                            data={"item_id": item_id, "changes": data["changes"]})
    return Outcome("edit_item", t("confirm_edit_item", language, name=item["name"], changes="\n".join(changes)),
                   pending=pending)


@pending_resolver("confirm_edit_item")
def resolve_confirm_edit_item(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("edit_item", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("edit_item", t("edit_kept", ctx.language))
    data, business_id = pending.data, ctx.business["id"]

    def commit(conn: Connection) -> str:
        changes = {k: (Decimal(v) if k in ("sale_price", "purchase_price", "low_stock_level") else v)
                   for k, v in data["changes"].items()}
        if "name" in changes:
            same = [i for i in tools.find_item(conn, business_id, changes["name"])
                    if i["name"].lower() == changes["name"].lower() and str(i["id"]) != data["item_id"]]
            if same:
                return t("item_exists_short", ctx.language, name=same[0]["name"])
        if not tools.update_item(conn, business_id, data["item_id"], **changes):
            return t("item_gone", ctx.language)
        item = tools.get_item(conn, business_id, data["item_id"])
        return t("item_updated", ctx.language, name=item["name"]) + "\n" + _item_line(ctx.language, item, item["qty"])

    return Outcome("edit_item", commit=commit)


@intent(
    "delete_item",
    "User removes an ITEM from the stock list (\"socks delete karo\", \"cheeni ka item hatao\"). Deleting one "
    "stock ENTRY is delete_entry.",
    fields=ItemFields,
    fields_hint='{"item": string}',
    examples=["socks delete karo", "cheeni ka item hata do"],
    needs_business=True,
    owner_only=True,
)
def delete_item(ctx: Context, fields: ItemFields) -> Outcome:
    return with_item(ctx, fields.item, "delete", {})


def _ask_delete_item(ctx: Context, item_id: str, data: dict) -> Outcome:
    with transaction() as conn:
        item = tools.get_item(conn, ctx.business["id"], item_id)
    pending = PendingAction(kind="confirm_delete_item", language=ctx.language, expects="yes_no",
                            data={"item_id": item_id})
    question = t("confirm_delete_item", ctx.language, name=item["name"], qty=fmt_qty(item["qty"]), unit=item["unit"])
    return Outcome("delete_item", question, pending=pending)


@pending_resolver("confirm_delete_item")
def resolve_confirm_delete_item(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("delete_item", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("delete_item", t("delete_kept", ctx.language))
    business_id, item_id = ctx.business["id"], pending.data["item_id"]

    def commit(conn: Connection) -> str:
        item = tools.get_item(conn, business_id, item_id)
        if item is None or not tools.delete_item(conn, business_id, item_id):
            return t("item_gone", ctx.language)
        return t("item_deleted", ctx.language, name=item["name"])

    return Outcome("delete_item", commit=commit)


@intent(
    "item_photo",
    "SEE a stock item's photo. A saved entry's / bill's photo is entry_photo.",
    fields=ItemFields,
    fields_hint='{"item": string}',
    examples=["socks ki photo bhejo", "surf ki tasveer dikhao"],
    needs_business=True,
)
def item_photo(ctx: Context, fields: ItemFields) -> Outcome:
    return with_item(ctx, fields.item, "photo", {})


def _send_item_photo(ctx: Context, item_id: str, data: dict) -> Outcome:
    with transaction() as conn:
        item = tools.get_item(conn, ctx.business["id"], item_id)
        path = tools.item_photo(conn, ctx.business["id"], item_id)
    if not path:
        return Outcome("item_photo", t("no_item_photo", ctx.language, name=item["name"]))
    caption = f"📷 {item['name']}\n" + _item_line(ctx.language, item, item["qty"])
    return Outcome("item_photo", caption, attachment=path)


ITEM_HANDLERS.update({
    "line": ("stock_in", _line_item),
    "report": ("stock_report", _report),
    "edit": ("edit_item", _ask_edit_item),
    "delete": ("delete_item", _ask_delete_item),
    "photo": ("item_photo", _send_item_photo),
})

for _mode, _intent in _DRAFT_INTENT.items():
    DRAFT_STEPS[_mode] = (_intent, next_step)


# ---------------------------------------------------------------------------
# Photos: an item's barcode or picture (called by the agent before bill reading)
# ---------------------------------------------------------------------------

_BARCODE_WORDS = {"barcode", "barcod", "bar", "code", "بارکوڈ"}
_PHOTO_WORDS = {"photo", "foto", "tasveer", "tasvir", "pic", "picture", "image", "تصویر", "فوٹو"}
_CAPTION_FILLER = {"ka", "ki", "ke", "hai", "he", "yeh", "ye", "is", "iska", "iski", "save", "karo", "kro", "lagao",
                   "add", "rakho", "of", "the", "this", "کا", "کی", "کے", "ہے", "یہ"}


def stock_photo(ctx: Context) -> Outcome | None:
    """A photo that is about a stock item, else None (then it is read as a bill / register page).
      "socks ka barcode" + barcode photo -> save the barcode on Socks (owner)
      "socks ki photo" + photo           -> save it as Socks' picture (owner)
      a known barcode, no caption        -> that item's stock and price (staff too)"""
    caption = "" if ctx.text.strip() == "[image]" else ctx.text.strip()
    words = re.findall(r"\w+", caption.lower())
    item_word = " ".join(w for w in words if w not in _BARCODE_WORDS | _PHOTO_WORDS | _CAPTION_FILLER)
    language = ctx.language

    if words and set(words) & _BARCODE_WORDS:
        if not _is_owner(ctx):
            return Outcome("item_barcode", t("owner_only", language))
        code = _read_barcode(ctx.image_path)
        if code is None:
            return Outcome("item_barcode", t("barcode_unreadable", language))
        if not item_word:
            return _barcode_lookup(ctx, code, ask=True)
        return with_item(ctx, item_word, "barcode", {"code": code})

    if words and set(words) & _PHOTO_WORDS and item_word:
        with transaction() as conn:
            known = tools.find_item(conn, ctx.business["id"], item_word)
        if known:  # else "yeh bill ki photo hai" etc.: a normal photo
            if not _is_owner(ctx):
                return Outcome("item_photo", t("owner_only", language))
            return with_item(ctx, item_word, "photo_set", {})
        return None

    if not caption:
        code = barcode.read(ctx.image_path)
        if code:
            with transaction() as conn:
                known = tools.find_by_barcode(conn, ctx.business["id"], code)
            if known:
                return _barcode_lookup(ctx, code, ask=False)
    return None


def _read_barcode(path: str) -> str | None:
    """The bars first (free, instant); if they can't be read, the digits printed under them (OCR),
    accepted only with a correct check digit."""
    code = barcode.read(path)
    if code:
        return code
    try:
        return barcode.from_text(read_text(path).text)
    except OCRError:
        return None


def _barcode_lookup(ctx: Context, code: str, ask: bool) -> Outcome:
    with transaction() as conn:
        item = tools.find_by_barcode(conn, ctx.business["id"], code)
    if item:
        return Outcome("item_barcode", f"🔖 {code}\n*{item['name']}*\n" + _item_line(ctx.language, item, item["qty"]))
    pending = PendingAction(kind="barcode_item", language=ctx.language, expects="choice_or_name", data={"code": code})
    return Outcome("item_barcode", t("ask_barcode_item", ctx.language, code=code), pending=pending)


@pending_resolver("barcode_item")
def resolve_barcode_item(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    return with_item(ctx, answer.strip(), "barcode", {"code": pending.data["code"]})


def _save_barcode(ctx: Context, item_id: str, data: dict) -> Outcome:
    business_id, code = ctx.business["id"], data["code"]

    def commit(conn: Connection) -> str:
        other = tools.find_by_barcode(conn, business_id, code)
        if other and str(other["id"]) != item_id:
            return t("barcode_taken", ctx.language, code=code, name=other["name"])
        if not tools.update_item(conn, business_id, item_id, barcode=code):
            return t("item_gone", ctx.language)
        item = tools.get_item(conn, business_id, item_id)
        return t("barcode_saved", ctx.language, name=item["name"], code=code)

    return Outcome("item_barcode", commit=commit)


def _save_item_photo(ctx: Context, item_id: str, data: dict) -> Outcome:
    business_id, message_id = ctx.business["id"], ctx.message_id

    def commit(conn: Connection) -> str:
        if not tools.update_item(conn, business_id, item_id, photo_message_id=message_id):
            return t("item_gone", ctx.language)
        item = tools.get_item(conn, business_id, item_id)
        return t("item_photo_saved", ctx.language, name=item["name"])

    return Outcome("item_photo", commit=commit)


ITEM_HANDLERS.update({
    "barcode": ("item_barcode", _save_barcode),
    "photo_set": ("item_photo", _save_item_photo),
})
