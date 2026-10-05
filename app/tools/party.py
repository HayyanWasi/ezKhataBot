"""Party khata tools: the ONLY code that reads or writes party data.

The AI never calls these and never sees SQL. Handlers call them with values the
code has already checked. Every tool is scoped to one business_id, so one shop
can never see or change another shop's parties.

Read tools can run in any short transaction. Write tools run only inside the
pipeline's commit transaction (Outcome.commit(conn)) and never commit themselves.

Sign rule for khata_entries.amount:
    > 0  you will get   (maine diye: gave goods/money to the party)
    < 0  you will give  (maine liye: got goods/money from the party)
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from psycopg import Connection

from app.tools import money

Id = UUID | str


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------


def find_parties(conn: Connection, business_id: Id, name: str, type: str | None = None) -> list[dict]:
    """Parties matching a name: exact matches if any, else partial matches."""
    rows = conn.execute(
        """
        select id, type, name, phone from accounts
        where business_id = %s and deleted_at is null
          and type in ('customer', 'supplier')
          and (%s::text is null or type = %s)
          and position(lower(%s) in lower(name)) > 0
        order by name
        """,
        (business_id, type, type, name.strip()),
    ).fetchall()
    exact = [r for r in rows if r["name"].lower() == name.strip().lower()]
    return exact or rows


def get_party(conn: Connection, business_id: Id, account_id: Id) -> dict | None:
    return conn.execute(
        """
        select id, type, name, phone from accounts
        where id = %s and business_id = %s and deleted_at is null
        """,
        (account_id, business_id),
    ).fetchone()


def get_balance(conn: Connection, business_id: Id, account_id: Id) -> Decimal:
    row = conn.execute(
        """
        select coalesce(sum(k.amount), 0) as balance
        from khata_entries k
        join business_transactions t on t.id = k.transaction_id
        where k.account_id = %s and t.business_id = %s and t.deleted_at is null
        """,
        (account_id, business_id),
    ).fetchone()
    return row["balance"]


def recent_entries(conn: Connection, business_id: Id, account_id: Id, limit: int = 5) -> list[dict]:
    """Newest entries first, each with the running balance after it."""
    return conn.execute(
        """
        select * from (
            select t.transaction_date, t.transaction_type, t.created_at, k.amount, k.notes,
                   sum(k.amount) over (order by t.transaction_date, t.created_at) as running_balance
            from khata_entries k
            join business_transactions t on t.id = k.transaction_id
            where k.account_id = %s and t.business_id = %s and t.deleted_at is null
        ) e
        order by transaction_date desc, created_at desc
        limit %s
        """,
        (account_id, business_id, limit),
    ).fetchall()


def list_balances(conn: Connection, business_id: Id, type: str | None = None) -> list[dict]:
    """Every live party with its balance, biggest balance first."""
    return conn.execute(
        """
        select a.id, a.type, a.name,
               coalesce(sum(k.amount) filter (where t.id is not null), 0) as balance
        from accounts a
        left join khata_entries k on k.account_id = a.id
        left join business_transactions t on t.id = k.transaction_id and t.deleted_at is null
        where a.business_id = %s and a.deleted_at is null
          and a.type in ('customer', 'supplier')
          and (%s::text is null or a.type = %s)
        group by a.id
        order by abs(coalesce(sum(k.amount) filter (where t.id is not null), 0)) desc, a.name
        """,
        (business_id, type, type),
    ).fetchall()


# ---------------------------------------------------------------------------
# Write tools (only inside the commit transaction)
# ---------------------------------------------------------------------------


def nice_name(name: str) -> str:
    """ "ali bhai" -> "Ali Bhai"; a name the user wrote with capitals ("ABC Traders", "McDonald") stays as written."""
    name = " ".join(name.split())
    return name.title() if name == name.lower() else name


def create_party(
    conn: Connection, business_id: Id, type: str, name: str, phone: str | None, created_by: Id
) -> dict:
    return conn.execute(
        """
        insert into accounts (business_id, type, name, phone, created_by)
        values (%s, %s, %s, %s, %s)
        returning id, type, name, phone
        """,
        (business_id, type, nice_name(name), phone, created_by),
    ).fetchone()


def rename_party(conn: Connection, business_id: Id, account_id: Id, name: str) -> str:
    """A party's name is changed; its entries stay with it. Returns the saved name."""
    return conn.execute(
        "update accounts set name = %s where id = %s and business_id = %s and deleted_at is null returning name",
        (nice_name(name), account_id, business_id),
    ).fetchone()["name"]


def set_party_phone(conn: Connection, business_id: Id, account_id: Id, phone: str) -> None:
    conn.execute(
        "update accounts set phone = %s where id = %s and business_id = %s and deleted_at is null",
        (phone, account_id, business_id),
    )


def record_entry(
    conn: Connection,
    *,
    business_id: Id,
    account_id: Id,
    direction: str,  # "gave" (you will get) | "got" (you will give)
    amount: Decimal,  # always positive; the sign comes from direction
    entry_date: date,
    note: str | None,
    message_id: Id,
    user_id: Id,
    opening: bool = False,
    source_line: int = 0,  # position of the row when one message saves several (a photo)
    money_account_id: Id | None = None,  # paid in cash / a bank: the money leg (Ali -1000, Cash +1000)
) -> UUID:
    """One transaction with the party leg (and the cash/bank leg, if paid). Returns the transaction id."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    if direction not in ("gave", "got"):
        raise ValueError(f"bad direction {direction!r}")
    signed = amount if direction == "gave" else -amount
    legs = [(account_id, signed)]
    if money_account_id is not None:
        legs.append((money_account_id, -signed))  # the shop gave money -> money went out
    return money.record_transaction(
        conn,
        business_id=business_id,
        type="opening_balance" if opening else direction,
        entry_date=entry_date,
        legs=legs,
        note=note,
        message_id=message_id,
        user_id=user_id,
        source_line=source_line,
    )


delete_entry = money.delete_transaction
