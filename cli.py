"""EzKhata dev chat: talk to the bot as a shopkeeper, without WhatsApp.

    uv run cli.py [--phone 03001234567] [--verbose] [--lease 5]
"""

import argparse
import logging
import uuid

from app.channels.cli import CLIChannel
from app.core.config import get_settings
from app.core.database import transaction
from app.core.phone import normalize_phone
from app.db import crud
from app.services import handler

DEV_HELP = """dev commands:
  /as <phone>            chat as another number (unknown numbers are not onboarded)
  /add-business <name>   create another shop owned by you
  /repeat                resend the last message with the SAME id (duplicate test)
  /fail-next-send        next reply fails to send
  /crash-before-commit   next message stops after thinking, before saving
  /dev                   show this list
  /exit                  quit
bot commands: /help, /cancel"""


def ask_phone() -> str:
    while True:
        try:
            return normalize_phone(input("Your WhatsApp number: "))
        except ValueError as e:
            print(e)


def onboard(phone: str) -> dict:
    """Temporary until the admin dashboard exists: a new number creates its owner + first shop."""
    with transaction() as conn:
        user = crud.get_user_by_phone(conn, phone)
    if user:
        return user
    print("New number - let's set up your shop.")
    name = input("Your name: ").strip()
    shop = input("Shop name: ").strip()
    with transaction() as conn:
        user = crud.create_user(conn, phone, name)
        crud.create_business(conn, user["id"], shop)
    print(f"Created owner {name} with shop {shop}.")
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description="EzKhata dev chat")
    parser.add_argument("--phone", help="your WhatsApp number, e.g. 03001234567")
    parser.add_argument("-v", "--verbose", action="store_true", help="show AI calls and pipeline logs")
    parser.add_argument("--lease", type=int, default=5, help="seconds before a crashed message is retried (dev)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="  · %(name)s: %(message)s")
    if args.verbose:
        logging.getLogger("ezkhata").setLevel(logging.INFO)
    get_settings().processing_lease_seconds = args.lease

    phone = normalize_phone(args.phone) if args.phone else ask_phone()
    onboard(phone)
    channel = CLIChannel()
    last: tuple[str, str, str] | None = None  # (external_id, phone, text)

    print(f"\nChatting as {phone}. Type /dev for dev commands.\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue

        command, _, arg = text.partition(" ")
        if command == "/exit":
            break
        if command == "/dev":
            print(DEV_HELP)
            continue
        if command == "/as":
            try:
                phone = normalize_phone(arg)
                print(f"(now chatting as {phone})")
            except ValueError as e:
                print(e)
            continue
        if command == "/add-business":
            with transaction() as conn:
                user = crud.get_user_by_phone(conn, phone)
                if user and arg.strip():
                    crud.create_business(conn, user["id"], arg.strip())
                    print(f"(created shop {arg.strip()})")
                else:
                    print("(usage: /add-business <name>, as a registered number)")
            continue
        if command == "/fail-next-send":
            channel.fail_next_send = True
            print("(next reply will fail to send)")
            continue
        if command == "/crash-before-commit":
            handler.DEV["crash_before_commit"] = True
            print("(next message will crash before commit)")
            continue
        if command == "/repeat":
            if last is None:
                print("(nothing to repeat)")
                continue
            external_id, phone_used, text = last
        else:
            external_id, phone_used = uuid.uuid4().hex, phone
            last = (external_id, phone_used, text)

        try:
            result = handler.handle_message(channel, external_id, phone_used, text)
        except handler.SimulatedCrash as e:
            print(f"({e}: message left as 'received', nothing saved)")
            continue
        if result not in (handler.Result.PROCESSED, handler.Result.NOT_REGISTERED):
            print(f"({result})")


if __name__ == "__main__":
    main()
