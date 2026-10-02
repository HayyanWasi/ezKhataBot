"""Bill tools: the ONLY code that reads or writes bills and the shop's bill details.

The AI never calls these and never sees SQL. Every tool is scoped to one
business_id. Write tools run only inside the pipeline's commit transaction.

A bill is one business_transactions row (type 'bill') with:
  - stock_moves: one per item (qty < 0, rate = the sale rate), so stock goes down
  - khata_entries: cash / bank +paid, and the customer +balance (they owe the shop)
  - a bills row: bill number, customer, totals
Cancelling = soft-deleting the transaction (money.delete_transaction): stock,
cash and khata come back, and the bill shows as cancelled.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from psycopg import Connection

from app.tools import money, stock

Id = UUID | str


def next_bill_no(conn: Connection, business_id: Id) -> int:
    """Inside the commit: the shop row is locked, so two bills never get the same number."""
    conn.execute("select id from businesses where id = %s for update", (business_id,))
    row = conn.execute(
        "select coalesce(max(bill_no), 0) + 1 as n from bills where business_id = %s", (business_id,)
    ).fetchone()
    return row["n"]


def record_bill(
    conn: Connection,
    *,
    business_id: Id,
    entry_date: date,
    moves: list[tuple[Id, Decimal, Decimal]],  # (item id, qty (> 0), sale rate)
    legs: list[tuple[Id, Decimal]],  # cash / bank +paid, customer +balance
    bill: dict,  # customer_id, customer_name, subtotal, discount_*, tax_*, total, paid_amount, pay_via
    message_id: Id | None,
    user_id: Id,
) -> dict:
    """One bill. Returns the bills row (with its bill_no)."""
    transaction_id = stock.record_stock(
        conn, business_id=business_id, type="bill", entry_date=entry_date,
        moves=[(item_id, -qty, rate) for item_id, qty, rate in moves], legs=legs,
        note=None, message_id=message_id, user_id=user_id,
    )
    return conn.execute(
        """
        insert into bills (business_id, bill_no, transaction_id, customer_id, customer_name, subtotal,
                           discount_amount, discount_percent, tax_amount, tax_percent, total, paid_amount,
                           pay_via, created_by)
        values (%(business_id)s, %(bill_no)s, %(transaction_id)s, %(customer_id)s, %(customer_name)s,
                %(subtotal)s, %(discount_amount)s, %(discount_percent)s, %(tax_amount)s, %(tax_percent)s,
                %(total)s, %(paid_amount)s, %(pay_via)s, %(user_id)s)
        returning *
        """,
        {**bill, "business_id": business_id, "bill_no": next_bill_no(conn, business_id),
         "transaction_id": transaction_id, "user_id": user_id},
    ).fetchone()


_BILL = """b.*, t.transaction_date as bill_date, (t.deleted_at is not null) as cancelled"""


def get_bill(conn: Connection, business_id: Id, bill_no: int) -> dict | None:
    """A bill with its lines (name, unit, qty, rate, amount)."""
    bill = conn.execute(
        f"""
        select {_BILL} from bills b join business_transactions t on t.id = b.transaction_id
        where b.business_id = %s and b.bill_no = %s
        """,
        (business_id, bill_no),
    ).fetchone()
    if bill is None:
        return None
    lines = conn.execute(
        """
        select i.name, i.unit, -s.qty as qty, s.rate, -s.qty * s.rate as amount
        from stock_moves s join items i on i.id = s.item_id
        where s.transaction_id = %s order by s.line
        """,
        (bill["transaction_id"],),
    ).fetchall()
    return {**bill, "lines": lines}


def bill_for_transaction(conn: Connection, business_id: Id, transaction_id: Id) -> dict | None:
    return conn.execute(
        "select bill_no, customer_name, total from bills where business_id = %s and transaction_id = %s",
        (business_id, transaction_id),
    ).fetchone()


def list_bills(
    conn: Connection, business_id: Id, start: date, end: date, customer_id: Id | None = None
) -> list[dict]:
    """Bills in a period (cancelled ones too, marked), oldest first."""
    return conn.execute(
        f"""
        select {_BILL} from bills b join business_transactions t on t.id = b.transaction_id
        where b.business_id = %(business_id)s and t.transaction_date between %(start)s and %(end)s
          and (%(customer_id)s::uuid is null or b.customer_id = %(customer_id)s)
        order by b.bill_no
        """,
        {"business_id": business_id, "start": start, "end": end, "customer_id": customer_id},
    ).fetchall()


def cash_sales_total(conn: Connection, business_id: Id, start: date, end: date) -> Decimal:
    """Amount-only sales ("aaj 20000 ki sale hui") in a period."""
    row = conn.execute(
        """
        select coalesce(sum(k.amount), 0) as total
        from business_transactions t join khata_entries k on k.transaction_id = t.id
        where t.business_id = %s and t.transaction_type = 'sale' and t.deleted_at is null
          and t.transaction_date between %s and %s
        """,
        (business_id, start, end),
    ).fetchone()
    return row["total"]


def profit_items(conn: Connection, business_id: Id, start: date, end: date) -> list[dict]:
    """Items sold on live bills in a period: qty, sales (qty x sale rate) and cost (qty x purchase price
    at the time of the sale: the rate of the item's latest stock in before the bill, else today's
    purchase price). cost is None when the purchase price is not known."""
    return conn.execute(
        """
        select l.item_id, l.name, l.unit, sum(l.qty) as qty, sum(l.qty * l.rate) as sales,
               case when bool_and(l.cost is not null) then sum(l.qty * l.cost) end as cost
        from (
            select m.item_id, i.name, i.unit, -m.qty as qty, m.rate,
                   coalesce((
                       select pm.rate from stock_moves pm
                       join business_transactions pt on pt.id = pm.transaction_id
                       where pm.item_id = m.item_id and pm.qty > 0 and pm.rate is not null
                         and pt.deleted_at is null and pt.created_at <= t.created_at
                       order by pt.created_at desc limit 1
                   ), i.purchase_price) as cost
            from stock_moves m
            join business_transactions t on t.id = m.transaction_id
            join items i on i.id = m.item_id
            where t.business_id = %s and t.deleted_at is null and t.transaction_type = 'bill' and m.qty < 0
              and t.transaction_date between %s and %s
        ) l
        group by l.item_id, l.name, l.unit
        order by sales desc
        """,
        (business_id, start, end),
    ).fetchall()


def bill_discounts(conn: Connection, business_id: Id, start: date, end: date) -> Decimal:
    row = conn.execute(
        """
        select coalesce(sum(b.discount_amount), 0) as total
        from bills b join business_transactions t on t.id = b.transaction_id
        where b.business_id = %s and t.deleted_at is null and t.transaction_date between %s and %s
        """,
        (business_id, start, end),
    ).fetchone()
    return row["total"]


def expenses_total(conn: Connection, business_id: Id, start: date, end: date) -> Decimal:
    """Shop costs (bijli, kiraya, chai ...) paid from cash or a bank in a period."""
    row = conn.execute(
        """
        select coalesce(-sum(k.amount), 0) as total
        from khata_entries k
        join business_transactions t on t.id = k.transaction_id
        join accounts a on a.id = k.account_id
        where t.business_id = %s and t.deleted_at is null and t.category_id is not null
          and a.type in ('cash', 'bank') and k.amount < 0 and t.transaction_date between %s and %s
        """,
        (business_id, start, end),
    ).fetchone()
    return row["total"]


def set_shop_details(conn: Connection, business_id: Id, address: str | None, phone: str | None) -> None:
    conn.execute("update businesses set address = %s, phone = %s where id = %s", (address, phone, business_id))


def shop_details(conn: Connection, business_id: Id) -> dict:
    return conn.execute("select name, address, phone from businesses where id = %s", (business_id,)).fetchone()


delete_bill = money.delete_transaction  # cancel: stock, cash and khata come back
