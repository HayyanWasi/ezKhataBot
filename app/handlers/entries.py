"""Undo / delete / edit any entry (party khata, cash book or stock), and send an entry's photo.

Every change is asked first (haan/nahi). A delete is a soft delete; an edit
soft-deletes the old entry and saves a corrected copy that points to it
(edited_from), so the history stays. A stock entry's items go with it; a change
that would take an item's stock below 0 is refused.

The owner can change any entry. Staff can only change their own cash and stock entries.
"""

from datetime import date, timedelta
from decimal import Decimal

from psycopg import Connection

from app.core.database import transaction
from app.core.dates import short_date, today
from app.handlers import bills
from app.handlers.money_steps import money_line
from app.handlers.party import PARTY_CHOICE_HANDLERS, ask_choose_party, balance_line
from app.schemas.khata import DeleteEntryFields, EditEntryFields, EntryPhotoFields, PendingAction
from app.services.amounts import confirmed_amount, format_rs
from app.services.answers import parse_yes_no
from app.services.registry import Context, Outcome, intent, pending_resolver
from app.services.replies import t
from app.tools import money as tools
from app.tools import party as party_tools
from app.tools import bills as bill_tools
from app.tools import stock as stock_tools

_PARTY_TYPES = ("customer", "supplier")


def _is_owner(ctx: Context) -> bool:
    return ctx.business["role"] == "owner"


def _label(language: str, entry: dict) -> str:
    """What the entry is about: the party's name, else the expense category, else its kind.
    A stock entry also names its items: "Stock in (Socks)", "Bilal (Socks)"."""
    party = next((leg for leg in entry["legs"] if leg["type"] in _PARTY_TYPES), None)
    moves = entry.get("moves") or []
    if party:
        label = party["name"]
    elif moves:
        label = t(f"entry_{entry['transaction_type']}", language)
    else:
        return entry["category"] or entry["notes"] or t(f"entry_{entry['transaction_type']}", language)
    if moves:
        label += " (" + ", ".join(m["name"] for m in moves) + ")"
    return label


def _amount(entry: dict) -> Decimal:
    return abs(entry["legs"][0]["amount"])


def _amount_text(entry: dict) -> str:
    """Rs 500, or for a stock-only entry its quantity: 50 pcs."""
    if entry["legs"]:
        return format_rs(_amount(entry))
    move = entry["moves"][0]
    return f"{_qty(abs(move['qty']))} {move['unit']}" + (" …" if len(entry["moves"]) > 1 else "")


def _qty(value: Decimal) -> str:
    return f"{value:,.0f}" if value == value.to_integral() else f"{value.normalize():f}"


def _bill_no(ctx: Context, entry: dict) -> int:
    with transaction() as conn:
        return bill_tools.bill_for_transaction(conn, ctx.business["id"], entry["transaction_id"])["bill_no"]


def _moves_data(entry: dict) -> list[dict]:
    return [{"item_id": str(m["item_id"]), "qty": str(m["qty"])} for m in entry.get("moves") or []]


def _stock_problem(conn: Connection, ctx: Context, moves: list[dict], new_qty: Decimal | None = None) -> str | None:
    """Removing (or, with new_qty, changing) these moves would take an item below 0: the refusal, else None."""
    if not moves:
        return None
    change: dict[str, Decimal] = {}
    for move in moves:
        old = Decimal(move["qty"])
        new = (new_qty if old > 0 else -new_qty) if new_qty is not None else Decimal(0)
        change[move["item_id"]] = change.get(move["item_id"], Decimal(0)) + new - old
    stock_tools.lock_items(conn, ctx.business["id"], list(change))
    stock = stock_tools.stock_of(conn, ctx.business["id"], list(change))
    for item_id, delta in change.items():
        if stock.get(item_id, Decimal(0)) + delta < 0:
            item = stock_tools.get_item(conn, ctx.business["id"], item_id)
            return t("stock_change_below_zero", ctx.language, name=item["name"], qty=_qty(stock[item_id]),
                     unit=item["unit"])
    return None


def _stock_lines(conn: Connection, ctx: Context, moves: list[dict]) -> list[str]:
    """📦 Socks: 150 pcs, for every item the entry moved."""
    ids = list(dict.fromkeys(m["item_id"] for m in moves))
    stock = stock_tools.stock_of(conn, ctx.business["id"], ids)
    lines = []
    for item_id in ids:
        item = stock_tools.get_item(conn, ctx.business["id"], item_id)
        if item:
            lines.append(f"📦 {item['name']}: {_qty(stock[item_id])} {item['unit']}")
    return lines


def _find(ctx: Context, party: dict | None, data: dict, amount_key: str = "amount") -> dict | None:
    """The entry the user means: by party, amount (data[amount_key]) and item word; staff only their own."""
    with transaction() as conn:
        return tools.find_entry(
            conn, ctx.business["id"], ctx.user["id"], account_id=party["id"] if party else None,
            amount=Decimal(data[amount_key]) if data.get(amount_key) else None, item=data.get("item"),
            only_own=not _is_owner(ctx),
        )


def _staff_blocked(ctx: Context, entry: dict) -> bool:
    """Staff may only change their own cash entries (no party leg)."""
    if _is_owner(ctx):
        return False
    own = str(entry["created_by"]) == str(ctx.user["id"])
    return not own or any(leg["type"] in _PARTY_TYPES for leg in entry["legs"])


def _with_party(ctx: Context, intent_name: str, purpose: str, fields, data: dict, then) -> Outcome:
    """Find the party named in the message (asking which one if several), then call `then`.
    A name that is no party ("bijli wali entry") is used as the item word instead."""
    data = {**data, "item": fields.item}
    if not fields.party_name:
        return then(ctx, None, data)
    with transaction() as conn:
        matches = party_tools.find_parties(conn, ctx.business["id"], fields.party_name)
    if not matches:
        return then(ctx, None, {**data, "item": data["item"] or fields.party_name})
    if len(matches) > 1:
        return ask_choose_party(ctx, fields.party_name, matches, purpose, data)
    return then(ctx, matches[0], data)


def _balances(conn: Connection, ctx: Context, legs: list[dict]) -> list[str]:
    """A balance line for every account the entry touched."""
    lines = []
    for leg in legs:
        balance = tools.get_balance(conn, ctx.business["id"], leg["account_id"])
        if leg["type"] in _PARTY_TYPES:
            lines.append(balance_line(ctx.language, leg["name"], balance))
        else:
            lines.append(money_line(ctx.language, leg["name"], leg["type"], balance))
    return lines


def _legs_data(entry: dict) -> list[dict]:
    return [{"account_id": str(leg["account_id"]), "name": leg["name"], "type": leg["type"]} for leg in entry["legs"]]


# ---------------------------------------------------------------------------
# Delete / undo
# ---------------------------------------------------------------------------


@intent(
    "delete_entry",
    "User wants to undo or delete an entry (khata, cash or stock): the last one, or one described by party name, "
    "item and/or amount (a stock entry's quantity counts as its amount: \"cheeni ki 10 kg wali entry\" -> "
    "item cheeni, amount 10).",
    fields=DeleteEntryFields,
    fields_hint='{"party_name": string | null, "item": string | null, "amount": number | null}',
    examples=["undo", "bijli wali entry delete karo", "galti ho gayi, entry hatao", "Ali ki 500 wali entry delete karo", "آخری انٹری ڈیلیٹ کرو"],
    needs_business=True,
)
def delete_entry(ctx: Context, fields: DeleteEntryFields) -> Outcome:
    amount = confirmed_amount(ctx.text, fields.amount)
    data = {"amount": str(amount) if amount else None}
    return _with_party(ctx, "delete_entry", "delete", fields, data, _ask_delete)


def _ask_delete(ctx: Context, party: dict | None, data: dict) -> Outcome:
    entry = _find(ctx, party, data)
    if entry is None:
        return Outcome("delete_entry", t("no_entry_to_delete", ctx.language))
    if _staff_blocked(ctx, entry):
        return Outcome("delete_entry", t("staff_own_cash_only", ctx.language))
    if entry["transaction_type"] == "bill":  # undo / delete of a bill = cancel the bill
        return bills.ask_cancel(ctx, _bill_no(ctx, entry))
    pending = PendingAction(
        kind="confirm_delete",
        language=ctx.language,
        expects="yes_no",
        data={"transaction_id": str(entry["transaction_id"]), "legs": _legs_data(entry), "moves": _moves_data(entry)},
    )
    question = t(
        "confirm_delete", ctx.language, name=_label(ctx.language, entry), amount=_amount_text(entry),
        date=short_date(entry["transaction_date"]),
    )
    return Outcome("delete_entry", question, pending=pending)


@pending_resolver("confirm_delete")
def resolve_confirm_delete(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("delete_entry", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("delete_entry", t("delete_kept", ctx.language))
    data = pending.data
    if "legs" not in data:  # a question asked before the cash book existed
        data = {**data, "legs": [{"account_id": data["account_id"], "name": data["name"], "type": "customer"}]}

    def commit(conn: Connection) -> str:
        moves = data.get("moves", [])
        problem = _stock_problem(conn, ctx, moves)
        if problem:
            return problem
        if not tools.delete_transaction(conn, ctx.business["id"], data["transaction_id"], ctx.user["id"]):
            return t("no_entry_to_delete", ctx.language)
        lines = [t("entry_deleted", ctx.language)] + _balances(conn, ctx, data["legs"])
        return "\n".join(lines + _stock_lines(conn, ctx, moves))

    return Outcome("delete_entry", commit=commit)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


@intent(
    "edit_entry",
    "User CORRECTS an entry already saved (khata, cash or stock): a different amount, quantity, date or note. "
    "Signs: \"entry\", "
    "\"wali\", \"thi/tha\", \"nahi ... thi\", \"galat\", \"theek karo\", \"change karo\". "
    "\"Ali wali entry 500 nahi 600 thi\" -> party_name Ali, amount 500, new_amount 600. "
    "\"chai wali 150 entry 180 thi\" -> amount 150, new_amount 180 (chai is not a party: party_name null). "
    "\"last entry ki date kal karo\" -> new_date. amount = the entry's current amount (or quantity) if said. "
    "\"socks wali entry 50 nahi 40 thi\" -> item socks, amount 50, new_qty 40.",
    fields=EditEntryFields,
    fields_hint=(
        '{"party_name": string | null, "item": string | null, "amount": number | null, "new_amount": number | null, '
        '"new_date": "YYYY-MM-DD" | null, "new_note": string | null, "new_qty": number | null}'
    ),
    examples=[
        "Ali wali entry 500 nahi 600 thi", "chai wali 150 entry 180 thi", "last entry 700 karo",
        "chai wali entry ki date kal karo",
    ],
    needs_business=True,
)
def edit_entry(ctx: Context, fields: EditEntryFields) -> Outcome:
    new_amount = confirmed_amount(ctx.text, fields.new_amount)
    new_qty = confirmed_amount(ctx.text, fields.new_qty)
    old_amount = confirmed_amount(ctx.text, fields.amount)
    if old_amount is not None and old_amount == new_amount:
        old_amount = None
    now = today(ctx.business["timezone"])
    new_date = fields.new_date
    if new_date == now + timedelta(days=1):  # "date kal karo": for an entry, kal can only be yesterday
        new_date = now - timedelta(days=1)
    if new_date and new_date > now:
        return Outcome("edit_entry", t("future_date", ctx.language))
    if new_amount is None and new_qty is None and new_date is None and fields.new_note is None:
        return Outcome("edit_entry", t("edit_nothing", ctx.language))
    data = {
        "amount": str(old_amount) if old_amount else None,
        "new_amount": str(new_amount) if new_amount else None,
        "new_date": new_date.isoformat() if new_date else None,
        "new_note": fields.new_note,
        "new_qty": str(new_qty) if new_qty else None,
    }
    return _with_party(ctx, "edit_entry", "edit", fields, data, _ask_edit)


def _ask_edit(ctx: Context, party: dict | None, data: dict) -> Outcome:
    language = ctx.language
    entry = _find(ctx, party, data)
    if entry is None and data.get("amount") and data["new_amount"]:
        # "350 thi 300 nahi" can come back with old and new swapped: try the other way round
        entry = _find(ctx, party, data, amount_key="new_amount")
        if entry is not None:
            data = {**data, "amount": data["new_amount"], "new_amount": data["amount"]}
    if entry is None:
        return Outcome("edit_entry", t("no_entry_found", language))
    if _staff_blocked(ctx, entry):
        return Outcome("edit_entry", t("staff_own_cash_only", language))
    if entry["transaction_type"] == "bill":
        return Outcome("edit_entry", t("bill_edit_cancel", language, no=_bill_no(ctx, entry)))

    data = _qty_or_amount(entry, data)
    if (data.get("new_qty") and len(entry["moves"]) != 1) or (data["new_amount"] and not entry["legs"]):
        return Outcome("edit_entry", t("edit_qty_one_item", language))
    changes = []
    if data.get("new_qty"):
        move = entry["moves"][0]
        changes.append(f"{move['name']} {_qty(abs(move['qty']))} → {_qty(Decimal(data['new_qty']))} {move['unit']}")
    if data["new_amount"]:
        changes.append(f"{format_rs(_amount(entry))} → {format_rs(Decimal(data['new_amount']))}")
    if data["new_date"]:
        changes.append(f"{short_date(entry['transaction_date'])} → {short_date(date.fromisoformat(data['new_date']))}")
    if data["new_note"]:
        changes.append(f"\"{entry['notes'] or '-'}\" → \"{data['new_note']}\"")

    pending = PendingAction(
        kind="confirm_edit",
        language=language,
        expects="yes_no",
        data={**data, "transaction_id": str(entry["transaction_id"])},
    )
    question = t(
        "confirm_edit", language, name=_label(language, entry), date=short_date(entry["transaction_date"]),
        changes=", ".join(changes),
    )
    return Outcome("edit_entry", question, pending=pending)


@pending_resolver("confirm_edit")
def resolve_confirm_edit(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("edit_entry", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("edit_entry", t("edit_kept", ctx.language))
    data, business_id = pending.data, ctx.business["id"]

    def commit(conn: Connection) -> str:
        # Read the entry again inside the commit, so the legs are exactly what gets replaced
        entry = _live_entry(conn, ctx, data["transaction_id"])
        if entry is None:
            return t("no_entry_found", ctx.language)
        new_qty = Decimal(data["new_qty"]) if data.get("new_qty") else None
        moves = [{"item_id": str(m["item_id"]), "qty": str(m["qty"])} for m in entry["moves"]]
        problem = _stock_problem(conn, ctx, moves, new_qty) if new_qty is not None else None
        if problem:
            return problem
        tools.edit_transaction(
            conn, business_id, entry,
            amount=Decimal(data["new_amount"]) if data["new_amount"] else None,
            entry_date=date.fromisoformat(data["new_date"]) if data["new_date"] else None,
            note=data["new_note"],
            message_id=ctx.message_id,
            user_id=ctx.user["id"],
            qty=new_qty,
        )
        lines = [t("entry_edited", ctx.language)] + _balances(conn, ctx, entry["legs"])
        return "\n".join(lines + _stock_lines(conn, ctx, moves))

    return Outcome("edit_entry", commit=commit)


def _live_entry(conn: Connection, ctx: Context, transaction_id: str) -> dict | None:
    row = conn.execute(
        """
        select t.id as transaction_id, t.transaction_date, t.transaction_type, t.created_by, t.category_id
        from business_transactions t where t.id = %s and t.business_id = %s and t.deleted_at is null
        """,
        (transaction_id, ctx.business["id"]),
    ).fetchone()
    if row is None:
        return None
    legs = conn.execute(
        """
        select k.account_id, k.amount, k.notes, a.name, a.type
        from khata_entries k join accounts a on a.id = k.account_id
        where k.transaction_id = %s
        """,
        (transaction_id,),
    ).fetchall()
    return {**row, "legs": legs, "moves": tools.entry_moves(conn, transaction_id),
            "notes": legs[0]["notes"] if legs else None}


def _qty_or_amount(entry: dict, data: dict) -> dict:
    """A stock entry's "50 nahi 40": the numbers are a quantity when the entry moves no money,
    or when the old number is the item's quantity (not its money)."""
    moves = entry.get("moves") or []
    if len(moves) != 1 or data.get("new_qty") or not data["new_amount"]:
        return data
    old_qty = abs(moves[0]["qty"])
    if not entry["legs"] or (data.get("amount") and Decimal(data["amount"]) == old_qty):
        return {**data, "new_qty": data["new_amount"], "new_amount": None}
    return data


# ---------------------------------------------------------------------------
# Photo proof
# ---------------------------------------------------------------------------


@intent(
    "entry_photo",
    "User asks for the photo / proof / bill picture of an entry that was saved from a photo.",
    fields=EntryPhotoFields,
    fields_hint='{"party_name": string | null, "item": string | null, "amount": number | null}',
    examples=["Ali wali entry ki photo bhejo", "bijli bill ki photo dikhao", "last entry ka proof"],
    needs_business=True,
)
def entry_photo(ctx: Context, fields: EntryPhotoFields) -> Outcome:
    amount = confirmed_amount(ctx.text, fields.amount)
    data = {"amount": str(amount) if amount else None}
    return _with_party(ctx, "entry_photo", "photo", fields, data, _send_photo)


def _send_photo(ctx: Context, party: dict | None, data: dict) -> Outcome:
    amount = Decimal(data["amount"]) if data.get("amount") else None
    with transaction() as conn:  # anyone in the shop may see a proof photo
        entry = tools.find_entry(
            conn, ctx.business["id"], ctx.user["id"], account_id=party["id"] if party else None,
            amount=amount, item=data.get("item"), with_photo=True,
        )
    if entry is None:
        return Outcome("entry_photo", t("no_entry_photo", ctx.language))
    caption = t(
        "entry_photo", ctx.language, name=_label(ctx.language, entry), amount=format_rs(_amount(entry)),
        date=short_date(entry["transaction_date"]),
    )
    return Outcome("entry_photo", caption, attachment=entry["photo"])


PARTY_CHOICE_HANDLERS.update({
    "delete": ("delete_entry", _ask_delete),
    "edit": ("edit_entry", _ask_edit),
    "photo": ("entry_photo", _send_photo),
})
