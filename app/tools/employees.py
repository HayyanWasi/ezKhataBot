"""Shop employees: add, list, remove. Every query is scoped to one business.

An employee is a user (their own WhatsApp number) with an active row in business_employees.
Removing sets the row to 'removed', so their past entries keep their name."""

from uuid import UUID

from psycopg import Connection

from app.db import crud
from app.tools.party import nice_name

Id = UUID | str


def list_employees(conn: Connection, business_id: Id) -> list[dict]:
    return conn.execute(
        """
        select u.id, u.name, u.phone, e.created_at
        from business_employees e join users u on u.id = e.user_id
        where e.business_id = %s and e.status = 'active'
        order by u.name
        """,
        (business_id,),
    ).fetchall()


def find_employee(conn: Connection, business_id: Id, word: str) -> list[dict]:
    """Active employees whose name contains the word, or whose number ends with it."""
    word = word.strip().lower()
    digits = "".join(c for c in word if c.isdigit())
    return [
        e for e in list_employees(conn, business_id)
        if (word and word in e["name"].lower()) or (len(digits) >= 7 and e["phone"].endswith(digits[-9:]))
    ]


def add_employee(conn: Connection, business_id: Id, phone: str, name: str, added_by: Id) -> dict:
    """The user with this number (created if new) becomes an active employee of the shop."""
    user = crud.get_user_by_phone(conn, phone) or crud.create_user(conn, phone, nice_name(name))
    conn.execute(
        """
        insert into business_employees (business_id, user_id, added_by)
        values (%s, %s, %s)
        on conflict (business_id, user_id) do update set status = 'active'
        """,
        (business_id, user["id"], added_by),
    )
    return user


def remove_employee(conn: Connection, business_id: Id, user_id: Id) -> None:
    conn.execute(
        "update business_employees set status = 'removed' where business_id = %s and user_id = %s",
        (business_id, user_id),
    )


def is_employee(conn: Connection, business_id: Id, user_id: Id) -> bool:
    return conn.execute(
        "select 1 from business_employees where business_id = %s and user_id = %s and status = 'active'",
        (business_id, user_id),
    ).fetchone() is not None
