"""Cash book tools: the ONLY code that reads or writes cash, banks, expense
categories, and the shared transaction/leg rows.

The AI never calls these and never sees SQL. Every tool is scoped to one
business_id. Write tools run only inside the pipeline's commit transaction.

One money event = one business_transactions row + one khata_entries row per
account it touches (a "leg"). Sign of a leg's amount:
    party (customer/supplier):  > 0 party owes the shop,  < 0 the shop owes the party
    cash / bank:                > 0 money came in,        < 0 money went out
"Ali ne 1000 wapas diye" = one transaction, two legs: Ali -1000, Cash +1000.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from psycopg import Connection

Id = UUID | str
CASH_NAME = "Cash"


# ---------------------------------------------------------------------------
# Transactions (write)
# ---------------------------------------------------------------------------


def record_transaction(
    conn: Connection,
    *,
    business_id: Id,
    type: str,  # gave | got | opening_balance | cash_in | cash_out | sale | transfer | adjustment
    entry_date: date,
    legs: list[tuple[Id, Decimal]],  # (account id, signed amount)
    note: str | None,
    message_id: Id | None,
    user_id: Id,
    category_id: Id | None = None,
    source_line: int = 0,  # position of the row when one message saves several (a photo)
    edited_from: Id | None = None,
    allow_no_legs: bool = False,  # a stock-only event (app/tools/stock.py) moves no money
) -> UUID:
    """One transaction with its legs. Returns the transaction id."""
    if (not legs and not allow_no_legs) or any(amount == 0 for _, amount in legs):
        raise ValueError("every leg needs a non-zero amount")

    transaction_id = conn.execute(
        """
        insert into business_transactions
            (business_id, transaction_date, transaction_type, source_message_id, source_line,
             category_id, edited_from, created_by)
        values (%s, %s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (business_id, entry_date, type, message_id, source_line, category_id, edited_from, user_id),
    ).fetchone()["id"]

    for account_id, amount in legs:
        # The select makes sure the account belongs to this business
        entry = conn.execute(
            """
            insert into khata_entries (transaction_id, account_id, amount, notes)
            select %s, a.id, %s, %s from accounts a
            where a.id = %s and a.business_id = %s and a.deleted_at is null
            returning id
            """,
            (transaction_id, amount, note, account_id, business_id),
        ).fetchone()
        if entry is None:
            raise ValueError("account not found in this business")
    return transaction_id


def delete_transaction(conn: Connection, business_id: Id, transaction_id: Id, user_id: Id) -> bool:
    """Soft delete. False if it was already deleted."""
    row = conn.execute(
        """
        update business_transactions set deleted_at = now(), deleted_by = %s
        where id = %s and business_id = %s and deleted_at is null
        returning id
        """,
        (user_id, transaction_id, business_id),
    ).fetchone()
    return row is not None


def edit_transaction(
    conn: Connection,
    business_id: Id,
    entry: dict,  # from find_entry()
    *,
    amount: Decimal | None,
    entry_date: date | None,
    note: str | None,
    message_id: Id,
    user_id: Id,
    qty: Decimal | None = None,  # a stock entry with one item: its new quantity
) -> UUID | None:
    """Soft-delete the old transaction and save a corrected copy that points to it (with its stock
    moves, if any). None if the old one was already deleted."""
    if not delete_transaction(conn, business_id, entry["transaction_id"], user_id):
        return None
    legs = [
        (leg["account_id"], (amount if leg["amount"] > 0 else -amount) if amount is not None else leg["amount"])
        for leg in entry["legs"]
    ]
    moves = [dict(m) for m in entry.get("moves", [])]
    if qty is not None and len(moves) == 1:
        move = moves[0]
        old_qty = abs(move["qty"])
        move["qty"] = qty if move["qty"] > 0 else -qty
        if amount is None and legs and move["rate"]:
            # A purchase: the money follows the quantity. The udhaar (party) leg takes the difference;
            # with no udhaar, the one money leg is the new total.
            difference = (qty - old_qty) * move["rate"]
            party = next((i for i, leg in enumerate(entry["legs"]) if leg["type"] in ("customer", "supplier")), None)
            index = party if party is not None else 0
            account_id, signed = legs[index]
            signed = signed - difference if signed < 0 else signed + difference
            legs = [leg for i, leg in enumerate(legs) if i != index] + ([(account_id, signed)] if signed else [])

    transaction_id = record_transaction(
        conn,
        business_id=business_id,
        type=entry["transaction_type"],
        entry_date=entry_date or entry["transaction_date"],
        legs=legs,
        note=note if note is not None else entry["notes"],
        message_id=message_id,
        user_id=user_id,
        category_id=entry["category_id"],
        edited_from=entry["transaction_id"],
        allow_no_legs=bool(moves),
    )
    for move in moves:
        conn.execute(
            "insert into stock_moves (transaction_id, item_id, qty, rate, line) values (%s, %s, %s, %s, %s)",
            (transaction_id, move["item_id"], move["qty"], move["rate"], move["line"]),
        )
    return transaction_id


# ---------------------------------------------------------------------------
# Cash and banks
# ---------------------------------------------------------------------------


def get_cash_account(conn: Connection, business_id: Id) -> dict | None:
    return conn.execute(
        "select id, type, name from accounts where business_id = %s and type = 'cash' and deleted_at is null",
        (business_id,),
    ).fetchone()


def ensure_cash_account(
    conn: Connection, business_id: Id, user_id: Id, opening: Decimal | None, entry_date: date
) -> UUID:
    """The shop's cash account; created on first use, with the opening cash (if any) as its first entry."""
    cash = get_cash_account(conn, business_id)
    if cash:
        return cash["id"]
    cash_id = conn.execute(
        "insert into accounts (business_id, type, name, created_by) values (%s, 'cash', %s, %s) returning id",
        (business_id, CASH_NAME, user_id),
    ).fetchone()["id"]
    if opening:
        record_transaction(
            conn, business_id=business_id, type="opening_balance", entry_date=entry_date,
            legs=[(cash_id, opening)], note=None, message_id=None, user_id=user_id,
        )
    return cash_id


def find_banks(conn: Connection, business_id: Id, name: str | None = None) -> list[dict]:
    """The shop's banks/wallets; with a name: exact matches if any, else partial."""
    rows = conn.execute(
        """
        select id, type, name, account_number from accounts
        where business_id = %s and type = 'bank' and deleted_at is null
        order by name
        """,
        (business_id,),
    ).fetchall()
    if not name:
        return rows
    needle = name.strip().lower().replace(" ", "")
    exact = [r for r in rows if r["name"].lower().replace(" ", "") == needle]
    return exact or [r for r in rows if needle in r["name"].lower().replace(" ", "")]


def create_bank(
    conn: Connection, business_id: Id, name: str, account_number: str | None, user_id: Id
) -> dict:
    return conn.execute(
        """
        insert into accounts (business_id, type, name, account_number, created_by)
        values (%s, 'bank', %s, %s, %s)
        returning id, type, name, account_number
        """,
        (business_id, name.strip(), account_number, user_id),
    ).fetchone()


def get_account(conn: Connection, business_id: Id, account_id: Id) -> dict | None:
    return conn.execute(
        "select id, type, name from accounts where id = %s and business_id = %s and deleted_at is null",
        (account_id, business_id),
    ).fetchone()


def get_balance(conn: Connection, business_id: Id, account_id: Id) -> Decimal:
    row = conn.execute(
        """
        select coalesce(sum(k.amount), 0) as balance
        from khata_entries k join business_transactions t on t.id = k.transaction_id
        where k.account_id = %s and t.business_id = %s and t.deleted_at is null
        """,
        (account_id, business_id),
    ).fetchone()
    return row["balance"]


# ---------------------------------------------------------------------------
# Expense categories (each shop makes its own)
# ---------------------------------------------------------------------------


def list_categories(conn: Connection, business_id: Id) -> list[dict]:
    return conn.execute(
        "select id, name from expense_categories where business_id = %s and deleted_at is null order by name",
        (business_id,),
    ).fetchall()


def category_for_word(conn: Connection, business_id: Id, word: str) -> dict | None:
    """The category this word was put in before, or a category with that name. For a phrase
    ("bijli bill") each of its words is tried too, so a remembered "bijli" still matches."""
    phrase = word.strip().lower()
    for candidate in dict.fromkeys([phrase, *phrase.split()]):
        found = _category_for(conn, business_id, candidate)
        if found:
            return found
    return None


def _category_for(conn: Connection, business_id: Id, word: str) -> dict | None:
    return conn.execute(
        """
        select c.id, c.name from expense_categories c
        left join category_words w on w.category_id = c.id and w.business_id = c.business_id and w.word = %s
        where c.business_id = %s and c.deleted_at is null and (w.word is not null or lower(c.name) = %s)
        order by (w.word is not null) desc
        limit 1
        """,
        (word, business_id, word),
    ).fetchone()


def create_category(conn: Connection, business_id: Id, name: str, user_id: Id) -> dict:
    """A new category, or the existing one with the same name."""
    existing = conn.execute(
        """
        select id, name from expense_categories
        where business_id = %s and lower(name) = lower(%s) and deleted_at is null
        """,
        (business_id, name.strip()),
    ).fetchone()
    if existing:
        return existing
    return conn.execute(
        "insert into expense_categories (business_id, name, created_by) values (%s, %s, %s) returning id, name",
        (business_id, name.strip(), user_id),
    ).fetchone()


def remember_word(conn: Connection, business_id: Id, word: str, category_id: Id) -> None:
    conn.execute(
        """
        insert into category_words (business_id, word, category_id) values (%s, %s, %s)
        on conflict (business_id, word) do update set category_id = excluded.category_id
        """,
        (business_id, word.strip().lower(), category_id),
    )


# ---------------------------------------------------------------------------
# Finding an entry (undo / delete / edit / photo proof)
# ---------------------------------------------------------------------------


def find_entry(
    conn: Connection,
    business_id: Id,
    user_id: Id,
    *,
    account_id: Id | None = None,
    amount: Decimal | None = None,
    item: str | None = None,  # a word in the entry's category or note ("bijli")
    only_own: bool = False,
    with_photo: bool = False,
) -> dict | None:
    """The latest live transaction: the user's own last one, or the one touching
    account_id and/or with that amount / item word. Returns it with all its legs."""
    item = item.strip().lower() if item else None
    described = account_id is not None or amount is not None or item is not None
    row = conn.execute(
        """
        select t.id as transaction_id, t.transaction_date, t.transaction_type, t.created_by,
               t.category_id, c.name as category, m.attachment_path as photo
        from business_transactions t
        left join expense_categories c on c.id = t.category_id
        left join messages m on m.id = t.source_message_id
        where t.business_id = %(business_id)s and t.deleted_at is null
          and ((%(described)s and not %(only_own)s) or t.created_by = %(user_id)s)
          and (%(account_id)s::uuid is null or exists (
                select 1 from khata_entries k where k.transaction_id = t.id and k.account_id = %(account_id)s))
          and (%(amount)s::numeric is null
               or exists (select 1 from khata_entries k where k.transaction_id = t.id and abs(k.amount) = %(amount)s)
               or exists (select 1 from stock_moves s where s.transaction_id = t.id and abs(s.qty) = %(amount)s))
          and (%(item)s::text is null or position(%(item)s in lower(coalesce(c.name, ''))) > 0
               or exists (select 1 from khata_entries k where k.transaction_id = t.id
                          and position(%(item)s in lower(coalesce(k.notes, ''))) > 0)
               or exists (select 1 from stock_moves s join items i on i.id = s.item_id
                          where s.transaction_id = t.id and position(%(item)s in lower(i.name)) > 0))
          and (not %(with_photo)s or m.attachment_path is not null)
        order by t.created_at desc
        limit 1
        """,
        {"business_id": business_id, "described": described, "only_own": only_own, "user_id": user_id,
         "account_id": account_id, "amount": amount, "item": item, "with_photo": with_photo},
    ).fetchone()
    if row is None:
        return None
    legs = conn.execute(
        """
        select k.account_id, k.amount, k.notes, a.name, a.type
        from khata_entries k join accounts a on a.id = k.account_id
        where k.transaction_id = %s
        order by a.type in ('cash', 'bank')  -- the party leg first
        """,
        (row["transaction_id"],),
    ).fetchall()
    return {**row, "legs": legs, "moves": entry_moves(conn, row["transaction_id"]),
            "notes": legs[0]["notes"] if legs else None}


def entry_moves(conn: Connection, transaction_id: Id) -> list[dict]:
    """The stock lines of a transaction (none for money-only entries)."""
    return conn.execute(
        """
        select s.item_id, s.qty, s.rate, s.line, i.name, i.unit
        from stock_moves s join items i on i.id = s.item_id
        where s.transaction_id = %s
        order by s.line
        """,
        (transaction_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Reports (read-only)
# ---------------------------------------------------------------------------


def money_summary(conn: Connection, business_id: Id, account_id: Id, start: date, end: date) -> dict:
    """Opening (before start), money in / out in the period, closing (at end), expense totals."""
    totals = conn.execute(
        """
        select
            coalesce(sum(k.amount) filter (where t.transaction_date < %s), 0) as opening,
            coalesce(sum(k.amount) filter (where t.transaction_date between %s and %s and k.amount > 0
                and t.transaction_type <> 'opening_balance'), 0) as money_in,
            coalesce(-sum(k.amount) filter (where t.transaction_date between %s and %s and k.amount < 0), 0)
                as money_out,
            coalesce(sum(k.amount) filter (where t.transaction_date <= %s), 0) as closing
        from khata_entries k join business_transactions t on t.id = k.transaction_id
        where k.account_id = %s and t.business_id = %s and t.deleted_at is null
        """,
        (start, start, end, start, end, end, account_id, business_id),
    ).fetchone()
    categories = conn.execute(
        """
        select c.name, -sum(k.amount) as total
        from khata_entries k
        join business_transactions t on t.id = k.transaction_id
        join expense_categories c on c.id = t.category_id
        where k.account_id = %s and t.business_id = %s and t.deleted_at is null
          and t.transaction_date between %s and %s and k.amount < 0
        group by c.name
        order by total desc
        """,
        (account_id, business_id, start, end),
    ).fetchall()
    # An opening balance entered inside the period counts as opening, not as money in
    opening_in_period = conn.execute(
        """
        select coalesce(sum(k.amount), 0) as total
        from khata_entries k join business_transactions t on t.id = k.transaction_id
        where k.account_id = %s and t.business_id = %s and t.deleted_at is null
          and t.transaction_type = 'opening_balance' and t.transaction_date between %s and %s
        """,
        (account_id, business_id, start, end),
    ).fetchone()["total"]
    return {**totals, "opening": totals["opening"] + opening_in_period, "categories": categories}


def money_rows(conn: Connection, business_id: Id, account_id: Id, start: date, end: date) -> list[dict]:
    """Every entry in the period with its details and the running balance after it."""
    return conn.execute(
        """
        select * from (
            select t.transaction_date, t.transaction_type, t.created_at, k.amount, k.notes,
                   c.name as category,
                   (select a2.name from khata_entries k2 join accounts a2 on a2.id = k2.account_id
                    where k2.transaction_id = t.id and k2.account_id <> k.account_id limit 1) as other,
                   sum(k.amount) over (order by t.transaction_date, t.created_at) as balance
            from khata_entries k
            join business_transactions t on t.id = k.transaction_id
            left join expense_categories c on c.id = t.category_id
            where k.account_id = %s and t.business_id = %s and t.deleted_at is null
              and t.transaction_date <= %s
        ) e
        where transaction_date >= %s
        order by transaction_date, created_at
        """,
        (account_id, business_id, end, start),
    ).fetchall()
