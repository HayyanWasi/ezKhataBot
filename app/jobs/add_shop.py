"""Register a number for the bot: creates the owner and their first shop.

    uv run python -m app.jobs.add_shop 03001234567 "Ali" "Ali General Store"

Only registered numbers get replies on WhatsApp. The signup website will call add_shop() later."""

import sys

from app.core.database import transaction
from app.core.phone import normalize_phone
from app.db import crud


def add_shop(phone: str, owner_name: str, shop_name: str) -> str:
    phone = normalize_phone(phone)
    with transaction() as conn:
        user = crud.get_user_by_phone(conn, phone)
        if user:
            return f"{phone} is already registered ({user['name']})"
        user = crud.create_user(conn, phone, owner_name.strip())
        crud.create_business(conn, user["id"], shop_name.strip())
    return f"Registered {phone}: owner {owner_name}, shop {shop_name}"


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    print(add_shop(*sys.argv[1:]))
