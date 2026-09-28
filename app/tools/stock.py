"""Stock book tools: the ONLY code that reads or writes items and stock moves.

The AI never calls these and never sees SQL. Every tool is scoped to one
business_id. Write tools run only inside the pipeline's commit transaction.

A stock event (opening stock, stock in, purchase, stock out) is one
business_transactions row with one stock_moves row per item (qty > 0 came in,
< 0 went out). A purchase also has money legs (supplier / cash / bank), saved
through money.record_transaction like any other transaction. A move counts only
while its transaction is live, so undo / delete / edit need no stock code.
"""

import difflib
from datetime import date
from decimal import Decimal
from uuid import UUID

from psycopg import Connection

from app.tools import money

Id = UUID | str

# Current stock of an item (i = items row); used in several queries below
_QTY = """coalesce((select sum(s.qty) from stock_moves s join business_transactions t on t.id = s.transaction_id
                    where s.item_id = i.id and t.deleted_at is null), 0)"""

_ITEM = f"""i.id, i.name, i.category, i.unit, i.sale_price, i.purchase_price, i.barcode, i.low_stock_level,
            i.photo_message_id, {_QTY} as qty"""


def _normal(word: str) -> str:
    return " ".join(word.lower().split())


def _singular(word: str) -> str:
    """socks -> sock, boxes -> box, glasses -> glass (good enough for matching, never shown)."""
    if word.endswith("es") and len(word) > 4 and word[-3] in "sxzh":
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


# ---------------------------------------------------------------------------
# Items (read)
# ---------------------------------------------------------------------------


def list_items(conn: Connection, business_id: Id) -> list[dict]:
    return conn.execute(
        f"select {_ITEM} from items i where i.business_id = %s and i.deleted_at is null order by lower(i.name)",
        (business_id,),
    ).fetchall()


def get_item(conn: Connection, business_id: Id, item_id: Id) -> dict | None:
    return conn.execute(
        f"select {_ITEM} from items i where i.id = %s and i.business_id = %s and i.deleted_at is null",
        (item_id, business_id),
    ).fetchone()


def find_item(conn: Connection, business_id: Id, word: str) -> list[dict]:
    """Items the user may mean by `word`: a remembered word, the exact name, singular/plural,
    a near spelling, or a name containing the word. [] = no match; one = sure; several = ask."""
    word = _normal(word)
    if not word:
        return []
    remembered = conn.execute(
        f"""
        select {_ITEM} from item_words w join items i on i.id = w.item_id
        where w.business_id = %s and w.word = %s and i.deleted_at is null
        """,
        (business_id, word),
    ).fetchone()
    if remembered:
        return [remembered]

    items = list_items(conn, business_id)
    names = {item["id"]: _normal(item["name"]) for item in items}
    for same in (
        lambda name: name == word,
        lambda name: _singular(name) == _singular(word),
        lambda name: name.replace(" ", "") == word.replace(" ", ""),
    ):
        found = [item for item in items if same(names[item["id"]])]
        if found:
            return found

    close = set(difflib.get_close_matches(word, names.values(), n=5, cutoff=0.85))
    found = [item for item in items if names[item["id"]] in close]
    if found:
        return found
    if len(word) >= 3:  # "cheeni" -> "Cheeni 1kg"
        return [item for item in items if word in names[item["id"]] or _singular(word) in names[item["id"]]]
    return []


def find_by_barcode(conn: Connection, business_id: Id, barcode: str) -> dict | None:
    return conn.execute(
        f"select {_ITEM} from items i where i.business_id = %s and i.barcode = %s and i.deleted_at is null",
        (business_id, barcode),
    ).fetchone()


def item_photo(conn: Connection, business_id: Id, item_id: Id) -> str | None:
    row = conn.execute(
        """
        select m.attachment_path from items i join messages m on m.id = i.photo_message_id
        where i.id = %s and i.business_id = %s and i.deleted_at is null
        """,
        (item_id, business_id),
    ).fetchone()
    return row["attachment_path"] if row else None


# ---------------------------------------------------------------------------
# Items (write)
# ---------------------------------------------------------------------------


def create_item(
    conn: Connection,
    business_id: Id,
    *,
    name: str,
    unit: str,
    user_id: Id,
    category: str | None = None,
    sale_price: Decimal | None = None,
    purchase_price: Decimal | None = None,
    low_stock_level: Decimal | None = None,
    barcode: str | None = None,
) -> dict:
    return conn.execute(
        """
        insert into items (business_id, name, unit, category, sale_price, purchase_price, low_stock_level,
                           barcode, created_by)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning id, name, unit, category, sale_price, purchase_price, low_stock_level, barcode
        """,
        (business_id, name.strip(), unit.strip(), category, sale_price, purchase_price, low_stock_level,
         barcode, user_id),
    ).fetchone()


_EDITABLE = {"name", "unit", "category", "sale_price", "purchase_price", "low_stock_level", "barcode",
             "photo_message_id"}


def update_item(conn: Connection, business_id: Id, item_id: Id, **changes) -> bool:
    """Change some fields of an item (only the ones in _EDITABLE). False if the item is gone."""
    changes = {k: v for k, v in changes.items() if k in _EDITABLE}
    if not changes:
        return False
    columns = ", ".join(f"{column} = %s" for column in changes)
    row = conn.execute(
        f"""
        update items set {columns}, updated_at = now()
        where id = %s and business_id = %s and deleted_at is null
        returning id
        """,
        (*changes.values(), item_id, business_id),
    ).fetchone()
    return row is not None


def delete_item(conn: Connection, business_id: Id, item_id: Id) -> bool:
    """Soft delete; its barcode and remembered words are freed for other items."""
    row = conn.execute(
        """
        update items set deleted_at = now(), barcode = null, updated_at = now()
        where id = %s and business_id = %s and deleted_at is null
        returning id
        """,
        (item_id, business_id),
    ).fetchone()
    if row:
        conn.execute("delete from item_words where business_id = %s and item_id = %s", (business_id, item_id))
    return row is not None


def remember_word(conn: Connection, business_id: Id, word: str, item_id: Id) -> None:
    """Next time `word` means this item without asking ("jurab" -> Socks)."""
    word = _normal(word)
    if not word:
        return
    conn.execute(
        """
        insert into item_words (business_id, word, item_id)
        select %s, %s, i.id from items i where i.id = %s and i.business_id = %s and i.deleted_at is null
        on conflict (business_id, word) do update set item_id = excluded.item_id
        """,
        (business_id, word, item_id, business_id),
    )


# ---------------------------------------------------------------------------
# Stock (read)
# ---------------------------------------------------------------------------


def stock_of(conn: Connection, business_id: Id, item_ids: list[Id]) -> dict[str, Decimal]:
    rows = conn.execute(
        f"select i.id, {_QTY} as qty from items i where i.business_id = %s and i.id = any(%s::uuid[])",
        (business_id, [str(i) for i in item_ids]),
    ).fetchall()
    return {str(r["id"]): r["qty"] for r in rows}


def lock_items(conn: Connection, business_id: Id, item_ids: list[Id]) -> None:
    """Inside the commit: hold these items until it ends, so two messages can't both take the last stock."""
    conn.execute(
        "select id from items where business_id = %s and id = any(%s::uuid[]) order by id for update",
        (business_id, [str(i) for i in item_ids]),
    )


def low_items(conn: Connection, business_id: Id) -> list[dict]:
    """Items at or below their low-stock level."""
    return [
        item for item in list_items(conn, business_id)
        if item["low_stock_level"] is not None and item["qty"] <= item["low_stock_level"]
    ]


def item_moves(conn: Connection, business_id: Id, item_id: Id, limit: int = 5) -> list[dict]:
    """The item's latest live stock moves, newest first."""
    return conn.execute(
        """
        select t.transaction_date, t.transaction_type, s.qty, s.rate
        from stock_moves s join business_transactions t on t.id = s.transaction_id
        where s.item_id = %s and t.business_id = %s and t.deleted_at is null
        order by t.transaction_date desc, t.created_at desc
        limit %s
        """,
        (item_id, business_id, limit),
    ).fetchall()


def moves_report(
    conn: Connection, business_id: Id, direction: str, start: date, end: date, item_id: Id | None = None
) -> list[dict]:
    """Stock IN (direction 'in') or OUT ('out') lines in a period, oldest first, with the supplier if any."""
    return conn.execute(
        """
        select t.transaction_date, t.transaction_type, i.name, i.unit, s.qty, s.rate,
               (select a.name from khata_entries k join accounts a on a.id = k.account_id
                where k.transaction_id = t.id and a.type in ('customer', 'supplier') limit 1) as party,
               (select k.notes from khata_entries k where k.transaction_id = t.id limit 1) as notes,
               (select b.bill_no from bills b where b.transaction_id = t.id) as bill_no
        from stock_moves s
        join business_transactions t on t.id = s.transaction_id
        join items i on i.id = s.item_id
        where t.business_id = %(business_id)s and t.deleted_at is null
          and t.transaction_date between %(start)s and %(end)s
          and ((%(direction)s = 'in' and s.qty > 0) or (%(direction)s = 'out' and s.qty < 0))
          and (%(item_id)s::uuid is null or s.item_id = %(item_id)s)
        order by t.transaction_date, t.created_at, s.line
        """,
        {"business_id": business_id, "direction": direction, "start": start, "end": end, "item_id": item_id},
    ).fetchall()


# ---------------------------------------------------------------------------
# Stock (write)
# ---------------------------------------------------------------------------


def record_stock(
    conn: Connection,
    *,
    business_id: Id,
    type: str,  # stock_opening | stock_in | purchase | stock_out | bill
    entry_date: date,
    moves: list[tuple[Id, Decimal, Decimal | None]],  # (item id, signed qty, rate per unit)
    legs: list[tuple[Id, Decimal]],  # money legs of a purchase (supplier / cash / bank), else []
    note: str | None,
    message_id: Id | None,
    user_id: Id,
    source_line: int = 0,
) -> UUID:
    """One stock event. The latest purchase rate becomes the item's purchase price. Returns the transaction id."""
    if not moves or any(qty == 0 for _, qty, _ in moves):
        raise ValueError("every move needs a non-zero quantity")
    transaction_id = money.record_transaction(
        conn, business_id=business_id, type=type, entry_date=entry_date, legs=legs, note=note,
        message_id=message_id, user_id=user_id, source_line=source_line, allow_no_legs=True,
    )
    for line, (item_id, qty, rate) in enumerate(moves):
        # The select makes sure the item belongs to this business
        row = conn.execute(
            """
            insert into stock_moves (transaction_id, item_id, qty, rate, line)
            select %s, i.id, %s, %s, %s from items i
            where i.id = %s and i.business_id = %s and i.deleted_at is null
            returning id
            """,
            (transaction_id, qty, rate, line, item_id, business_id),
        ).fetchone()
        if row is None:
            raise ValueError("item not found in this business")
        if qty > 0 and rate is not None and type in ("stock_in", "purchase"):
            update_item(conn, business_id, item_id, purchase_price=rate)
    return transaction_id
