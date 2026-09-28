"""Statement tools (read-only): the numbers behind the PDF statements.

Every number comes from SQL + Decimal, never from the AI. Scoped to one business.
Sign rule (same as app/tools/party.py): amount > 0 = you will get, < 0 = you will give.
"""

from datetime import date
from decimal import Decimal

from psycopg import Connection

from app.tools.party import Id


def party_statement(conn: Connection, business_id: Id, account_id: Id, start: date | None, end: date) -> dict:
    """Opening balance, rows with running balance, totals and closing balance.

    start=None means the full khata (opening balance 0).
    """
    opening = Decimal(0)
    if start is not None:
        opening = conn.execute(
            """
            select coalesce(sum(k.amount), 0) as total
            from khata_entries k join business_transactions t on t.id = k.transaction_id
            where k.account_id = %s and t.business_id = %s and t.deleted_at is null
              and t.transaction_date < %s
            """,
            (account_id, business_id, start),
        ).fetchone()["total"]

    entries = conn.execute(
        """
        select t.transaction_date, t.transaction_type, k.amount, k.notes
        from khata_entries k join business_transactions t on t.id = k.transaction_id
        where k.account_id = %s and t.business_id = %s and t.deleted_at is null
          and (%s::date is null or t.transaction_date >= %s) and t.transaction_date <= %s
        order by t.transaction_date, t.created_at
        """,
        (account_id, business_id, start, start, end),
    ).fetchall()

    rows, balance = [], opening
    total_gave = total_got = Decimal(0)
    for e in entries:
        balance += e["amount"]
        if e["amount"] > 0:
            total_gave += e["amount"]
        else:
            total_got += -e["amount"]
        rows.append({**e, "balance": balance})

    return {
        "opening": opening,
        "rows": rows,
        "total_gave": total_gave,
        "total_got": total_got,
        "closing": opening + total_gave - total_got,
    }


def all_parties_summary(conn: Connection, business_id: Id, start: date | None, end: date) -> list[dict]:
    """Every live party: opening (before start), gave/got in the period, closing (at end)."""
    return conn.execute(
        """
        select a.id, a.name, a.type, a.phone,
            coalesce(sum(k.amount) filter (where %s::date is not null and t.transaction_date < %s), 0) as opening,
            coalesce(sum(k.amount) filter (where k.amount > 0
                and (%s::date is null or t.transaction_date >= %s) and t.transaction_date <= %s), 0) as gave,
            coalesce(-sum(k.amount) filter (where k.amount < 0
                and (%s::date is null or t.transaction_date >= %s) and t.transaction_date <= %s), 0) as got,
            coalesce(sum(k.amount) filter (where t.transaction_date <= %s), 0) as closing
        from accounts a
        left join khata_entries k on k.account_id = a.id
        left join business_transactions t on t.id = k.transaction_id and t.deleted_at is null
        where a.business_id = %s and a.deleted_at is null and a.type in ('customer', 'supplier')
        -- deleted transactions join as null, so every date filter above skips them
        group by a.id
        order by a.type, a.name
        """,
        (start, start, start, start, end, start, start, end, end, business_id),
    ).fetchall()
