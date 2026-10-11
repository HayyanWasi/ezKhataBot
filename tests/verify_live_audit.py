"""Read back isolated live audit effects; no writes."""

from live_roman_urdu_bot import PHONE, SHOP
from app.core.database import transaction
from app.db import crud

with transaction() as conn:
    user = crud.get_user_by_phone(conn, PHONE)
    shop = next(b for b in crud.list_user_businesses(conn, user["id"]) if b["name"] == SHOP)
    employee_count = conn.execute(
        "select count(*) from public.business_employees where business_id = %s and status = 'active'",
        (shop["id"],),
    ).fetchone()["count"]
    message_count = conn.execute(
        """select count(*) from public.messages m
           join public.conversations c on c.id = m.conversation_id
           where c.user_id = %s and c.channel = 'cli'""",
        (user["id"],),
    ).fetchone()["count"]
    print(f"shop={shop['name']!r} active_employees={employee_count} cli_messages={message_count}")
