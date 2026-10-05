"""Bills (sale invoices) and counter sales, with a PDF bill like DigiKhata's.

The AI only picks one of these intents and fills its fields (customer, items with
quantities and rates, discount, tax, payment as written). Everything else is code:
  - every number must be written in the message (app/services/amounts.py)
  - items are the shop's stock items (the same matching as stock, app/handlers/stock.py)
  - totals, discount and tax are worked out here, in Decimal
  - stock never goes below 0: re-checked in the commit with the items locked

A bill is a draft like a stock entry: next_step() asks the ONE missing thing
(which item -> quantity -> rate -> payment -> customer -> bank -> shop details) or saves it.
No customer name = a walk-in (counter) sale, paid in cash unless online is said.

Bills are owner only (staff can view them). Cancelling a bill soft-deletes its
transaction, so stock, cash and khata come back.
"""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

from psycopg import Connection

from app.core.config import get_settings
from app.core.dates import short_date, today
from app.core.database import transaction
from app.handlers.money_steps import money_account, money_line, money_step
from app.handlers.party import balance_line, shop_goods
from app.handlers.stock import _short_text, fmt_qty, low_warnings, new_stock_draft, with_item
from app.schemas.khata import (
    BillReportFields, CancelBillFields, CreateBillFields, PendingAction, ProfitFields, StockLine,
)
from app.services import pdf
from app.services.amounts import confirmed_amount, format_rs
from app.services.answers import CASH_WORDS, ONLINE_WORDS, UDHAAR_WORDS, is_skip, parse_number, parse_yes_no, pick
from app.services.registry import DRAFT_STEPS, Context, Outcome, ask_draft, intent, pending_resolver
from app.services.replies import numbered, t
from app.tools import bills as tools
from app.tools import money as money_tools
from app.tools import party as party_tools
from app.tools import stock as stock_tools

WALK_IN = "Walk-in"
_CENT = Decimal("0.01")


def _is_owner(ctx: Context) -> bool:
    return ctx.business["role"] == "owner"


def _today(ctx: Context) -> date:
    return today(ctx.business["timezone"])


def _str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _dec(value) -> Decimal | None:
    return Decimal(value) if value not in (None, "") else None


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _pct(value: Decimal) -> str:
    return fmt_qty(value)


# ---------------------------------------------------------------------------
# Totals (code, never the AI)
# ---------------------------------------------------------------------------


def totals(draft: dict) -> dict:
    """subtotal, discount (Rs and %), tax (Rs and %), total, paid, balance, for a draft whose lines are known."""
    subtotal = sum((Decimal(line["qty"]) * Decimal(line["rate"]) for line in draft["lines"]), Decimal(0))
    subtotal = _money(subtotal)

    discount_amount, discount_percent = _dec(draft["discount_amount"]), _dec(draft["discount_percent"])
    if discount_amount is None and discount_percent is not None:
        discount_amount = _money(subtotal * discount_percent / 100)
    if discount_amount is not None and discount_percent is None and subtotal:
        discount_percent = _money(discount_amount / subtotal * 100)
    discount_amount = discount_amount or Decimal(0)

    taxable = subtotal - discount_amount
    tax_amount, tax_percent = _dec(draft["tax_amount"]), _dec(draft["tax_percent"])
    if tax_amount is None and tax_percent is not None:
        tax_amount = _money(taxable * tax_percent / 100)
    if tax_amount is not None and tax_percent is None and taxable > 0:
        tax_percent = _money(tax_amount / taxable * 100)
    tax_amount = tax_amount or Decimal(0)

    total = taxable + tax_amount
    if draft["pay"] in ("cash", "bank"):
        paid = total
    else:
        paid = min(_dec(draft["paid_amount"]) or Decimal(0), total)
    return {
        "subtotal": subtotal, "discount_amount": discount_amount,
        "discount_percent": discount_percent if discount_amount else None,
        "tax_amount": tax_amount, "tax_percent": tax_percent if tax_amount else None,
        "total": total, "paid_amount": paid, "balance": total - paid,
    }


# ---------------------------------------------------------------------------
# Bill draft: ask what's missing, then save
# ---------------------------------------------------------------------------


def _pay_from(text: str, fields: CreateBillFields) -> tuple[str | None, str | None]:
    """(pay, paid_amount): cash | bank | udhaar | None (ask). Words decide; the AI's paid_via is a fallback."""
    words = set(re.findall(r"\w+", text.lower()))
    paid = confirmed_amount(text, fields.paid_amount)
    if words & UDHAAR_WORDS or paid:
        return "udhaar", _str(paid)
    if fields.bank_name or words & ONLINE_WORDS:
        return "bank", None
    if words & CASH_WORDS:
        return "cash", None
    if fields.paid_via:
        return fields.paid_via, None
    if not fields.customer_name:  # a counter sale: cash
        return "cash", None
    return None, None


def next_step(ctx: Context, draft: dict) -> Outcome:
    language = ctx.language
    if not draft["lines"]:
        return Outcome("create_bill", t("bill_which_items", language))

    for n, line in enumerate(draft["lines"]):
        if line["item_id"] is None:
            return with_item(ctx, line["word"], "line", {"draft": draft, "line": n})
        if line["qty"] is None:
            question = t("ask_stock_qty", language, name=line["name"], unit=line["item_unit"])
            return ask_draft(ctx, "stock_qty", "amount", draft, question, line=n)
        if line["rate"] is None:
            if line["sale_price"] is not None:
                line["rate"] = line["sale_price"]
            else:
                question = t("ask_bill_rate", language, name=line["name"], unit=line["item_unit"])
                return ask_draft(ctx, "stock_rate", "amount", draft, question, line=n)

    with transaction() as conn:
        stock = stock_tools.stock_of(conn, ctx.business["id"], [line["item_id"] for line in draft["lines"]])
        shop = tools.shop_details(conn, ctx.business["id"])
    short = _short_text(language, draft["lines"], stock)
    if short:
        return Outcome("create_bill", short)

    if draft["pay"] is None:
        question = t("ask_bill_pay", language, total=format_rs(totals({**draft, "pay": "cash"})["total"]))
        return ask_draft(ctx, "bill_pay", "choice", draft, question)
    sums = totals(draft)
    if sums["discount_amount"] > sums["subtotal"]:
        return Outcome("create_bill", t("bill_discount_too_big", language))

    if sums["balance"] > 0 and draft["account_id"] is None and not draft["new_customer"]:
        if not draft["customer_name"]:
            return ask_draft(ctx, "bill_customer", "choice_or_name", draft, t("ask_bill_customer", language))
        question = _customer_step(ctx, draft)
        if question:
            return question
    elif draft["customer_name"] and draft["account_id"] is None:
        with transaction() as conn:  # a cash bill for a known customer is kept on their record
            same = [p for p in party_tools.find_parties(conn, ctx.business["id"], draft["customer_name"], "customer")
                    if p["name"].lower() == draft["customer_name"].lower()]
        if len(same) == 1:
            draft["account_id"], draft["customer_name"] = str(same[0]["id"]), same[0]["name"]

    draft["via"] = draft["pay"] if draft["pay"] in ("cash", "bank") else None
    if draft["pay"] == "udhaar" and sums["paid_amount"] > 0:
        draft["via"] = "bank" if draft["bank_name"] else "cash"
    question = money_step(ctx, draft)  # which bank? opening cash?
    if question:
        return question

    # Asked once per shop: a skip is saved as an empty address, so it isn't asked on every bill
    if shop["address"] is None and shop["phone"] is None and not draft["shop_asked"]:
        return ask_draft(ctx, "shop_details", "free_text", draft, t("ask_shop_details", language))
    return _save(ctx, draft)


def _customer_step(ctx: Context, draft: dict) -> Outcome | None:
    """Find the customer for a bill with a balance. None = found. The same name exactly = that customer;
    names that only contain it ("Ahmed" -> "Bilal Ahmed") are offered with "new customer"; none = add new."""
    language, name = ctx.language, draft["customer_name"]
    with transaction() as conn:
        customers = party_tools.find_parties(conn, ctx.business["id"], name, "customer")
    exact = [c for c in customers if c["name"].lower() == name.strip().lower()]
    if len(exact) == 1:
        draft["account_id"], draft["customer_name"] = str(exact[0]["id"]), exact[0]["name"]
        return None
    if customers:
        options = [{"id": str(p["id"]), "name": p["name"]} for p in customers[:8]]
        labels = [p["name"] for p in options] + [t("new_party_option", language)]
        question = t("choose_party", language, name=name, options=numbered(labels))
        return ask_draft(ctx, "bill_choose_customer", "choice", draft, question, options=options)
    return ask_draft(ctx, "bill_new_customer", "yes_no", draft, t("confirm_new_customer", language,
                                                                  name=_title(name)))


def _title(word: str) -> str:
    word = " ".join(word.split())
    return word[:1].upper() + word[1:]


def _bill_pdf_path(business_id) -> str:
    folder = get_settings().storage_dir / "bills" / str(business_id)
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / f"bill_{uuid4().hex[:10]}.pdf")


def _save(ctx: Context, draft: dict) -> Outcome:
    language = ctx.language
    business_id, user_id = ctx.business["id"], ctx.user["id"]
    path = _bill_pdf_path(business_id)  # the PDF is written inside the commit, once the bill has its number

    def commit(conn: Connection) -> str:
        entry_date = date.fromisoformat(draft["date"])
        lines = draft["lines"]
        ids = [line["item_id"] for line in lines]
        stock_tools.lock_items(conn, business_id, ids)
        before = stock_tools.stock_of(conn, business_id, ids)
        short = _short_text(language, lines, before)
        if short:  # another message took the stock meanwhile
            return short
        if draft["shop_address"] is not None or draft["shop_phone"] is not None:
            tools.set_shop_details(conn, business_id, draft["shop_address"], draft["shop_phone"])

        sums = totals(draft)
        customer_id = draft["account_id"]
        if sums["balance"] > 0 and customer_id is None:
            customer_id = party_tools.create_party(conn, business_id, "customer", _title(draft["customer_name"]),
                                                   None, user_id)["id"]
        legs, money = [], None
        if sums["paid_amount"] > 0:
            money = money_account(conn, ctx, draft, entry_date)
            legs.append((money[0], sums["paid_amount"]))
        if sums["balance"] > 0:
            legs.append((customer_id, sums["balance"]))  # the customer owes the shop

        name = draft["customer_name"] and _title(draft["customer_name"])
        if customer_id is not None:
            name = party_tools.get_party(conn, business_id, customer_id)["name"]
        pay_via = "unpaid" if sums["paid_amount"] == 0 else (money[2] if money else "cash")
        bill = tools.record_bill(
            conn, business_id=business_id, entry_date=entry_date,
            moves=[(line["item_id"], Decimal(line["qty"]), Decimal(line["rate"])) for line in lines], legs=legs,
            bill={"customer_id": customer_id, "customer_name": name or WALK_IN, "pay_via": pay_via,
                  **{k: v for k, v in sums.items() if k != "balance"}},
            message_id=draft["source_message_id"] or ctx.message_id, user_id=user_id,
        )
        full = tools.get_bill(conn, business_id, bill["bill_no"])
        pdf.bill_pdf(tools.shop_details(conn, business_id), full, path)

        reply = [bill_summary(language, full)]
        after = stock_tools.stock_of(conn, business_id, ids)
        items = {str(i["id"]): i for i in stock_tools.list_items(conn, business_id) if str(i["id"]) in ids}
        reply += [f"📦 {items[i]['name']}: {fmt_qty(after[i])} {items[i]['unit']}" for i in dict.fromkeys(ids)]
        reply += low_warnings(conn, ctx, items, before, after)
        if sums["balance"] > 0:
            reply.append(balance_line(language, name, party_tools.get_balance(conn, business_id, customer_id)))
        if money:
            reply.append(money_line(language, money[1], money[2], money_tools.get_balance(conn, business_id, money[0])))
        return "\n".join(reply)

    return Outcome("create_bill", commit=commit, attachment=path)


def bill_summary(language: str, bill: dict) -> str:
    """🧾 Bill #3 · Rohaan · 28 Sep, the lines and the totals."""
    head = t("bill_head", language, no=bill["bill_no"], name=bill["customer_name"], date=short_date(bill["bill_date"]))
    if bill.get("cancelled"):
        head += " " + t("bill_cancelled_tag", language)
    lines = [head]
    for n, line in enumerate(bill["lines"], 1):
        lines.append(f"{n}) {line['name']} {fmt_qty(line['qty'])} × {format_rs(line['rate'])} = {format_rs(line['amount'])}")
    if bill["discount_amount"] or bill["tax_amount"]:
        lines.append(t("bill_subtotal", language, amount=format_rs(bill["subtotal"])))
    if bill["discount_amount"]:
        pct = f" {_pct(bill['discount_percent'])}%" if bill["discount_percent"] is not None else ""
        lines.append(t("bill_discount", language, pct=pct, amount=format_rs(bill["discount_amount"])))
    if bill["tax_amount"]:
        pct = f" {_pct(bill['tax_percent'])}%" if bill["tax_percent"] is not None else ""
        lines.append(t("bill_tax", language, pct=pct, amount=format_rs(bill["tax_amount"])))
    lines.append(t("bill_total", language, amount=format_rs(bill["total"])))
    balance = bill["total"] - bill["paid_amount"]
    if balance > 0:
        lines.append(t("bill_paid_part", language, paid=format_rs(bill["paid_amount"]), balance=format_rs(balance)))
    else:
        how = t("cash_name", language) if bill["pay_via"] == "cash" else t("bill_online", language)
        lines.append(t("bill_paid_full", language, how=how))
    return "\n".join(lines)


@intent(
    "create_bill",
    "SELLING items, to a customer or walk-in: \"Rohaan ka bill: 50 socks, 2 belt 250 wale\", \"2 socks bech "
    "diye\", \"Ali ko 2 packet surf udhaar diye 500 ke\". items: each with qty, unit and rate. customer_name: "
    "null for a walk-in. discount / tax: percent or amount. paid_via: \"cash\" | \"bank\" | \"udhaar\" | null; "
    "paid_amount: paid now when the rest is udhaar. A sale amount with no items (\"aaj 20000 ki sale\") is "
    "cash_entry.",
    fields=CreateBillFields,
    fields_hint=(
        '{"customer_name": string | null, "items": [{"name": string, "qty": number | null, "unit": string | null, '
        '"rate": number | null}], "discount_percent": number | null, "discount_amount": number | null, '
        '"tax_percent": number | null, "tax_amount": number | null, "paid_via": "cash" | "bank" | "udhaar" | null, '
        '"paid_amount": number | null, "bank_name": string | null, "date": "YYYY-MM-DD" | null}'
    ),
    examples=["Rohaan ka bill 50 socks 10% discount 1000 cash baqi udhaar", "2 socks aur 1 belt bech diye",
              "counter sale 3 packet surf", "Ali ko 5 kg cheeni ka bill banao udhaar"],
    needs_business=True,
    owner_only=True,
)
def create_bill(ctx: Context, fields: CreateBillFields) -> Outcome:
    text = ctx.text
    entry_date = fields.date or _today(ctx)
    if entry_date > _today(ctx):
        return Outcome("create_bill", t("future_date", ctx.language))
    pay, paid = _pay_from(text, fields)
    lines = fields.items
    if not any(line.name for line in lines):  # the AI left the items out: the shop's items written with a count
        goods = shop_goods(ctx, text)
        lines = [StockLine(name=item["name"], qty=str(count)) for item, count in goods]
        text += "".join(f" {count} {item['name']}" for item, count in goods)  # "aik sock": the count in digits
    draft = new_stock_draft("bill", lines, text, date=entry_date.isoformat(), bank_name=fields.bank_name)
    draft.update({
        "customer_name": fields.customer_name, "account_id": None, "new_customer": False, "pay": pay,
        "paid_amount": paid,
        "discount_percent": _str(confirmed_amount(text, fields.discount_percent)),
        "discount_amount": _str(confirmed_amount(text, fields.discount_amount)),
        "tax_percent": _str(confirmed_amount(text, fields.tax_percent)),
        "tax_amount": _str(confirmed_amount(text, fields.tax_amount)),
        "shop_asked": False, "shop_address": None, "shop_phone": None,
    })
    return next_step(ctx, draft)


# ---------------------------------------------------------------------------
# Answers to the draft's questions
# ---------------------------------------------------------------------------


def _draft(pending: PendingAction) -> dict:
    draft = dict(pending.data["draft"])
    draft["lines"] = [dict(line) for line in draft["lines"]]
    return draft


_BILL_PAY = {1: "cash", 2: "bank", 3: "udhaar"}


@pending_resolver("bill_pay")
def resolve_bill_pay(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    words = set(re.findall(r"\w+", answer.lower()))
    pay = _BILL_PAY.get(parse_number(answer) or 0)
    if pay is None:
        if words & UDHAAR_WORDS:
            pay = "udhaar"
        elif words & CASH_WORDS:
            pay = "cash"
        elif words & (ONLINE_WORDS | {"bank"}):
            pay = "bank"
    draft["pay"] = pay
    return next_step(ctx, draft)  # asks again if still unknown


@pending_resolver("bill_customer")
def resolve_bill_customer(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = _draft(pending)
    draft["customer_name"] = answer.strip()
    return next_step(ctx, draft)


@pending_resolver("bill_choose_customer")
def resolve_bill_choose_customer(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft, options = _draft(pending), pending.data["options"]
    if parse_number(answer) == len(options) + 1:
        draft["new_customer"] = True
        return next_step(ctx, draft)
    chosen = pick(answer, options, lambda p: p["name"])
    if chosen is None:
        labels = [p["name"] for p in options] + [t("new_party_option", ctx.language)]
        question = t("invalid_choice", ctx.language, n=len(labels), options=numbered(labels))
        return Outcome("create_bill", question, pending=pending)
    draft["account_id"], draft["customer_name"] = chosen["id"], chosen["name"]
    return next_step(ctx, draft)


@pending_resolver("bill_new_customer")
def resolve_bill_new_customer(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("create_bill", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("create_bill", t("image_cancelled", ctx.language))
    draft = _draft(pending)
    draft["new_customer"] = True
    return next_step(ctx, draft)


_PHONE = re.compile(r"(?:\+?92|0)\s*3\d{2}[\s-]*\d{7}|\b\d{3,4}[\s-]?\d{7}\b")


@pending_resolver("shop_details")
def resolve_shop_details(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    """The shop's address and phone in one message ("skip" = none). Code picks out the phone number."""
    draft = _draft(pending)
    draft["shop_asked"] = True
    draft["shop_address"] = ""  # skipped: remembered, not asked again
    if not is_skip(answer):
        match = _PHONE.search(answer)
        phone = re.sub(r"[\s-]", "", match.group()) if match else None
        address = (answer[:match.start()] + answer[match.end():]) if match else answer
        address = re.sub(r"\s+", " ", address).strip(" ,.-") or None
        draft["shop_address"], draft["shop_phone"] = address, phone
    return next_step(ctx, draft)


# ---------------------------------------------------------------------------
# Bills: list, one bill (PDF again), total sale
# ---------------------------------------------------------------------------


def _period(start: date, end: date) -> str:
    return short_date(start) if start == end else f"{short_date(start)} – {short_date(end)}"


@intent(
    "profit_report",
    "PROFIT / munafa / faida / kamai (or loss) for a day or a period. start_date / end_date: one day = both "
    "the same; null = today.",
    fields=ProfitFields,
    fields_hint='{"start_date": "YYYY-MM-DD" | null, "end_date": "YYYY-MM-DD" | null}',
    examples=["aaj hmein kitne ka faida howa?", "kal ka munafa batao", "is mahine ka profit", "5 tareekh ka faida"],
    needs_business=True,
    owner_only=True,
)
def profit_report(ctx: Context, fields: ProfitFields) -> Outcome:
    """Profit = item sales - discounts - their purchase cost; net = that - expenses. All in code."""
    language, business_id, day = ctx.language, ctx.business["id"], _today(ctx)
    end = min(fields.end_date or fields.start_date or day, day)
    start = min(fields.start_date or end, end)
    with transaction() as conn:
        items = tools.profit_items(conn, business_id, start, end)
        discounts = tools.bill_discounts(conn, business_id, start, end)
        expenses = tools.expenses_total(conn, business_id, start, end)
        cash_sales = tools.cash_sales_total(conn, business_id, start, end)

    period = _period(start, end)
    if not items and not cash_sales:
        reply = [t("profit_none", language, period=period)]
        if expenses:
            reply.append(t("profit_expenses_only", language, amount=format_rs(expenses)))
        return Outcome("profit_report", "\n".join(reply))

    known = [i for i in items if i["cost"] is not None]
    missing = [i for i in items if i["cost"] is None]
    sales = sum((i["sales"] for i in known), Decimal(0))
    cost = sum((i["cost"] for i in known), Decimal(0))
    gross = sales - discounts - cost
    net = gross - expenses
    reply = [t("profit_head", language, period=period)]
    if known:
        reply.append(t("profit_sales", language, amount=format_rs(sales)))
        if discounts:
            reply.append(t("profit_discount", language, amount=format_rs(discounts)))
        reply.append(t("profit_cost", language, amount=format_rs(cost)))
        reply.append(t("profit_gross" if gross >= 0 else "loss_gross", language, amount=format_rs(gross)))
        if expenses:
            reply.append(t("profit_expenses", language, amount=format_rs(expenses)))
            reply.append(t("profit_net" if net >= 0 else "loss_net", language, amount=format_rs(net)))
    if missing:
        reply.append(t("profit_missing", language, names=", ".join(i["name"] for i in missing),
                       amount=format_rs(sum((i["sales"] for i in missing), Decimal(0))), first=missing[0]["name"]))
    if cash_sales:
        reply.append(t("profit_cash_sales", language, amount=format_rs(cash_sales)))
    return Outcome("profit_report", "\n".join(reply))


@intent(
    "bill_report",
    "BILLS or SALES: one bill (\"Bill 3 bhejo\"), the bill list, a customer's bills, or the total sale for a "
    "period. Sale / bikri is always this, never profit_report. kind: \"one\" (a bill number is given) or "
    "\"list\".",
    fields=BillReportFields,
    fields_hint=(
        '{"kind": "one" | "list", "bill_no": number | null, "customer_name": string | null, '
        '"start_date": "YYYY-MM-DD" | null, "end_date": "YYYY-MM-DD" | null, "pdf": true | false}'
    ),
    examples=["Bill 3 bhejo", "bills dikhao", "kl ki sale", "Rohaan ke bills", "September ke bills PDF"],
    needs_business=True,
)
def bill_report(ctx: Context, fields: BillReportFields) -> Outcome:
    language, business_id = ctx.language, ctx.business["id"]
    if confirmed_amount(ctx.text, fields.bill_no) is not None:  # a bill number the user wrote, never a guess
        return send_bill(ctx, fields.bill_no)
    day = _today(ctx)
    end = min(fields.end_date or day, day)
    start = fields.start_date or end.replace(day=1)
    with transaction() as conn:
        customer = None
        if fields.customer_name:
            matches = party_tools.find_parties(conn, business_id, fields.customer_name)
            if not matches:
                return Outcome("bill_report", t("party_not_found", language, name=fields.customer_name))
            customer = matches[0]
        bills = tools.list_bills(conn, business_id, start, end, customer["id"] if customer else None)
        cash_sales = Decimal(0) if customer else tools.cash_sales_total(conn, business_id, start, end)

    live = [b for b in bills if not b["cancelled"]]
    bill_total = sum((b["total"] for b in live), Decimal(0))
    name = f" · {customer['name']}" if customer else ""
    reply = [t("bills_head", language, name=name, period=_period(start, end))]
    reply.append(t("bills_total", language, total=format_rs(bill_total + cash_sales), n=len(live),
                   bills=format_rs(bill_total)))
    if cash_sales:
        reply.append(t("bills_cash_sales", language, amount=format_rs(cash_sales)))
    for b in bills[-30:]:
        tag = f" {t('bill_cancelled_tag', language)}" if b["cancelled"] else ""
        due = b["total"] - b["paid_amount"]
        rest = f" · {t('bill_due', language, amount=format_rs(due))}" if due > 0 and not b["cancelled"] else ""
        reply.append(f"#{b['bill_no']} · {short_date(b['bill_date'])} · {b['customer_name']} · "
                     f"{format_rs(b['total'])}{rest}{tag}")
    if not bills:
        reply.append(t("no_bills", language))
    attachment = None
    if fields.pdf and bills:
        with transaction() as conn:
            shop = tools.shop_details(conn, business_id)
        attachment = pdf.bills_list_pdf(shop, ctx.business["id"], bills, cash_sales, start, end)
    return Outcome("bill_report", "\n".join(reply), attachment=attachment)


def send_bill(ctx: Context, bill_no: int) -> Outcome:
    with transaction() as conn:
        bill = tools.get_bill(conn, ctx.business["id"], bill_no)
        shop = tools.shop_details(conn, ctx.business["id"])
    if bill is None:
        return Outcome("bill_report", t("bill_not_found", ctx.language, no=bill_no))
    path = _bill_pdf_path(ctx.business["id"])
    pdf.bill_pdf(shop, bill, path)
    return Outcome("bill_report", bill_summary(ctx.language, bill), attachment=path)


# ---------------------------------------------------------------------------
# Cancel a bill (owner): stock, cash and khata come back
# ---------------------------------------------------------------------------


@intent(
    "cancel_bill",
    "CANCEL / delete a bill by number. Changing a bill is also this (cancelled and made again).",
    fields=CancelBillFields,
    fields_hint='{"bill_no": number | null}',
    examples=["Bill 3 cancel karo", "bill number 5 delete kar do", "Bill 3 mein socks 40 karo"],
    needs_business=True,
    owner_only=True,
)
def cancel_bill(ctx: Context, fields: CancelBillFields) -> Outcome:
    if confirmed_amount(ctx.text, fields.bill_no) is None:  # not written: ask which bill, never guess one
        return Outcome("cancel_bill", t("ask_bill_no", ctx.language))
    if re.search(r"\bkaro\b|\bkar\b", ctx.text.lower()) and not re.search(r"cancel|delete|hatao|khatam|radd",
                                                                        ctx.text.lower()):
        return Outcome("cancel_bill", t("bill_edit_cancel", ctx.language, no=fields.bill_no))
    return ask_cancel(ctx, fields.bill_no)


def ask_cancel(ctx: Context, bill_no: int) -> Outcome:
    with transaction() as conn:
        bill = tools.get_bill(conn, ctx.business["id"], bill_no)
    if bill is None:
        return Outcome("cancel_bill", t("bill_not_found", ctx.language, no=bill_no))
    if bill["cancelled"]:
        return Outcome("cancel_bill", t("bill_already_cancelled", ctx.language, no=bill_no))
    pending = PendingAction(kind="confirm_cancel_bill", language=ctx.language, expects="yes_no",
                            data={"bill_no": bill_no, "transaction_id": str(bill["transaction_id"])})
    question = t("confirm_cancel_bill", ctx.language, no=bill_no, name=bill["customer_name"],
                 amount=format_rs(bill["total"]))
    return Outcome("cancel_bill", question, pending=pending)


@pending_resolver("confirm_cancel_bill")
def resolve_confirm_cancel_bill(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("cancel_bill", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("cancel_bill", t("delete_kept", ctx.language))
    language, business_id, data = ctx.language, ctx.business["id"], pending.data

    def commit(conn: Connection) -> str:
        legs = conn.execute(
            """
            select k.account_id, a.name, a.type from khata_entries k join accounts a on a.id = k.account_id
            where k.transaction_id = %s
            """,
            (data["transaction_id"],),
        ).fetchall()
        moves = money_tools.entry_moves(conn, data["transaction_id"])
        if not tools.delete_bill(conn, business_id, data["transaction_id"], ctx.user["id"]):
            return t("bill_already_cancelled", language, no=data["bill_no"])
        reply = [t("bill_cancelled", language, no=data["bill_no"])]
        ids = list(dict.fromkeys(str(m["item_id"]) for m in moves))
        stock = stock_tools.stock_of(conn, business_id, ids)
        reply += [f"📦 {m['name']}: {fmt_qty(stock[str(m['item_id'])])} {m['unit']}" for m in moves]
        for leg in legs:
            balance = money_tools.get_balance(conn, business_id, leg["account_id"])
            if leg["type"] in ("customer", "supplier"):
                reply.append(balance_line(language, leg["name"], balance))
            else:
                reply.append(money_line(language, leg["name"], leg["type"], balance))
        return "\n".join(reply)

    return Outcome("cancel_bill", commit=commit)


DRAFT_STEPS["bill"] = ("create_bill", next_step)
