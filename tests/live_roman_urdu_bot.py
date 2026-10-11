"""Live CLI-channel bot audit on a synthetic shop. Uses configured Supabase and Groq."""

import json
import argparse
import os
import sys
import time
import uuid
from pathlib import Path

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LLM_PROVIDERS"] = "groq"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import transaction
from app.db import crud
from app.services.handler import handle_message


PHONE = "999000000000001"  # synthetic, CLI only; no WhatsApp sends
SHOP = "EzKhata Roman Urdu Audit Shop"
OUT = Path(__file__).with_name("live_roman_urdu_results.json")

CASES = [
    ("social", "kiya kar rha hai tou?", ["greeting", "help"]),
    ("social", "kya krrhe ho aap?", ["greeting", "help"]),
    ("social", "kya krrhe ho tum?", ["greeting", "help"]),
    ("social", "mere bhai tum kiya kaarhe ho?", ["greeting", "help"]),
    ("social", "mere bhi tum kiya karrhe ho?", ["greeting", "help"]),
    ("social", "oye tou kya karha hai?", ["greeting", "help"]),
    ("social", "abe tu kya kr raha hai?", ["greeting", "help"]),
    ("social", "assalam o alaikum bhai", ["greeting"]),
    ("employee", "employee add karo Ali and number", ["add_employee"]),
    ("employee", "add employee ali 0333", ["add_employee"]),
    ("employee", "add ali number", ["add_employee", "add_party"]),
    ("employee", "ali ko add kardo 03323", ["add_employee"]),
    ("employee", "ali ko add kr oska number ye hai", ["add_employee"]),
    ("employee", "oye ali ko employee add kr 999000000000002", ["add_employee"]),
    ("employee", "employees dikhao", ["list_employees"]),
    ("accounting", "aaj ka hisaab dikhao", ["money_report", "recent_entries"]),
    ("accounting", "Ali ka udhaar kitna hai?", ["party_balance"]),
    ("accounting", "yaar kal ka munafa batao", ["profit_report"]),
]


class CaptureChannel:
    name = "cli"

    def __init__(self):
        self.sent = []

    def send(self, phone, text):
        self.sent.append(text)
        return "audit-" + uuid.uuid4().hex[:12]

    def send_document(self, phone, path, caption):
        self.sent.append(caption + " [document]")
        return "audit-" + uuid.uuid4().hex[:12]


def setup():
    with transaction() as conn:
        user = crud.get_user_by_phone(conn, PHONE)
        if user is None:
            user = crud.create_user(conn, PHONE, "Roman Urdu Audit")
            crud.create_business(conn, user["id"], SHOP)
        shops = crud.list_user_businesses(conn, user["id"])
        if len(shops) != 1 or shops[0]["name"] != SHOP:
            raise RuntimeError("Synthetic audit number does not own exactly the expected test shop")
        return str(user["id"]), str(shops[0]["id"])


def send(channel, text):
    external_id = "roman-audit-" + uuid.uuid4().hex
    before = len(channel.sent)
    result = str(handle_message(channel, external_id, PHONE, text))
    with transaction() as conn:
        row = conn.execute(
            """select u.intent, u.processing_status, u.error, b.text as reply,
                      c.pending_action, b.delivery_status
               from public.messages u
               join public.conversations c on c.id = u.conversation_id
               left join public.messages b on b.reply_to_id = u.id
               where u.external_id = %s and c.user_id =
                   (select id from public.users where phone = %s)""",
            (external_id, PHONE),
        ).fetchone()
    return {
        "input": text, "result": result, "intent": row["intent"],
        "processing_status": row["processing_status"], "error": row["error"],
        "reply": row["reply"], "delivery_status": row["delivery_status"],
        "pending_kind": (row["pending_action"] or {}).get("kind"),
        "delivered_replies": channel.sent[before:],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--pause", type=int, default=22)
    args = parser.parse_args()
    user_id, shop_id = setup()
    channel = CaptureChannel()
    results = json.loads(OUT.read_text(encoding="utf-8"))["results"][:args.start - 1] if args.start > 1 and OUT.exists() else []
    try:
        for index, (group, text, expected_intents) in enumerate(CASES[args.start - 1:], args.start):
            item = send(channel, text)
            item.update(index=index, group=group, expected_intents=expected_intents)
            item["status"] = "PASS" if (item["intent"] in expected_intents
                                          and item["processing_status"] == "processed"
                                          and item["reply"] and item["delivery_status"] == "sent") else "FAIL"
            results.append(item)
            OUT.write_text(json.dumps({"user_id": user_id, "shop_id": shop_id, "results": results},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{index}/{len(CASES)} {item['status']} {item['intent']} {text!r}", flush=True)
            if item["pending_kind"]:
                send(channel, "/cancel")
            time.sleep(args.pause)
    finally:
        OUT.write_text(json.dumps({"user_id": user_id, "shop_id": shop_id, "results": results},
                                  ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
