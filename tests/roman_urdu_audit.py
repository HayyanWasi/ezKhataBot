"""Offline, read-only Roman Urdu audit. Run: .venv/Scripts/python tests/roman_urdu_audit.py"""

import json
import sys
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.agent import run_intent
from app.core.phone import normalize_phone
from app.handlers.employees import add_employee, resolve_add_employee
from app.schemas.khata import ClassifierOutput, EmployeeFields
from app.services.answers import is_trivial_answer, parse_yes_no
from app.services.registry import Context
from app.services.replies import detect_language


RESULTS = []


def record(group, text, expected, actual, note=""):
    RESULTS.append(dict(group=group, text=text, expected=expected, actual=actual,
                        status="PASS" if expected == actual else "FAIL", note=note))


roman = [
    "kiya kar rha hai tou?", "kya krrhe ho aap?", "kya krrhe ho tum?",
    "mere bhai tum kiya kaarhe ho?", "mere bhi tum kiya karrhe ho?",
    "oye tou kya karha hai?", "kya kr rhy ho?", "kia kar rahay ho?",
    "kya kar rahe ho?", "ap kia kr rahe hain", "tm kya krre ho",
    "tum kia krrhy ho", "oy kya scene hai", "abe kya kr rha",
    "assalam o alaikum", "salam bhai", "yaar tu kya karta hai",
    "employee add karo Ali 03001234567", "add employee ali 03331234567",
    "ali ko add kardo 03331234567", "ali ko add kr oska number ye hai 03331234567",
    "ali ko staff mein rakh lo 03331234567", "mre mulazim ali ko add krdo 03331234567",
    "oye ali ko employee add kr 03331234567", "bhai ali ka number 03331234567 add krdo",
    "Ali ko add karo 03323", "add ali number", "employee add krna hai",
    "Ali ko 500 diye", "ali sy 300 ly liye", "ali se paisay milay 500",
    "kal ki sale 5000 thi", "aaj ka cash dikhao", "udhar walon ka hisab btao",
    "rohaan ki baki rakam kitni", "kya tum mera hisaab bata skte ho",
    "oye 2 socks bech diye", "bhai 3 hazar jama krdo",
    "meray staff ko dikhao", "mujhse roman urdu me baat kro",
]
english = ["add employee Ali 03331234567", "show today's cash", "how are you doing?",
           "what can you do?", "remove employee Ali"]
for text in roman:
    record("language", text, "roman_ur", detect_language(text, default="en"))
for text in english:
    record("language", text, "en", detect_language(text, default="en"))

for raw, expected in [
    ("03001234567", "923001234567"), ("+92 300 1234567", "923001234567"),
    ("00923001234567", "923001234567"), ("0333-1234567", "923331234567"),
    ("03323", "INVALID"), ("0333", "INVALID"), ("abc", "INVALID"),
    ("1234567890", "INVALID"), ("999999999999999", "INVALID"),
]:
    try:
        actual = normalize_phone(raw)
    except ValueError:
        actual = "INVALID"
    record("phone", raw, expected, actual)

for answer, expected in [
    ("haan", True), ("han", True), ("haa", True), ("ji", True),
    ("jee", True), ("theek", True), ("hanji", True), ("haan ji", True),
    ("han g", True), ("kr do", True), ("kar do", True),
    ("nahi", False), ("nhi", False), ("nai", False),
    ("na ji", False), ("mat karo", False), ("rehne do", False),
    ("nahin", False), ("yes", True), ("no", False),
]:
    actual = parse_yes_no(answer)
    record("confirmation", answer, expected, actual,
           "None means the bot asks again" if actual is None else "")

owner_id = uuid4()
business_id = uuid4()
business = {"id": business_id, "name": "Test Shop", "owner_id": owner_id, "role": "owner"}


def context(text, role="owner"):
    shop = dict(business, role=role)
    return Context(user={"id": owner_id, "name": "Owner"},
                   conversation={"id": uuid4(), "channel": "whatsapp"},
                   business=shop, businesses=[shop], language="roman_ur", text=text)


with patch("app.handlers.employees.transaction", lambda: nullcontext(object())), \
     patch("app.handlers.employees.crud.get_user_by_phone", return_value=None), \
     patch("app.handlers.employees.tools.is_employee", return_value=False):
    for text, name, phone, expected in [
        ("employee add karo Ali and number", "Ali", None, "ASK_DETAILS"),
        ("add employee ali 0333", "ali", "0333", "INVALID_PHONE"),
        ("add ali number", "Ali", None, "ASK_DETAILS"),
        ("ali ko add kardo 03323", "ali", "03323", "INVALID_PHONE"),
        ("ali ko add kr oska number ye hai", "ali", None, "ASK_DETAILS"),
        ("ali ko add kardo 03331234567", "ali", "03331234567", "CONFIRM"),
        ("Ali ko add karo 1234567890", "Ali", "1234567890", "INVALID_PHONE"),
    ]:
        outcome = add_employee(context(text), EmployeeFields(name=name, phone=phone))
        actual = ("CONFIRM" if outcome.pending and outcome.pending.kind == "confirm_add_employee"
                  else "ASK_DETAILS" if "naam aur WhatsApp number" in outcome.reply
                  else "INVALID_PHONE" if "number" in outcome.reply.lower() else "OTHER")
        record("employee_flow", text, expected, actual,
               "Handler given expected extracted fields; classifier was not run")
        if actual == "CONFIRM":
            record("employee_flow", text + " [no immediate write]", True, outcome.commit is None)
            for answer, want in [("nahi", "CANCEL"), ("haan", "COMMIT_READY"),
                                 ("hanji", "ASK_AGAIN")]:
                resolved = resolve_add_employee(context(answer), outcome.pending, answer)
                got = "CANCEL" if resolved.pending is None and resolved.commit is None else \
                      "ASK_AGAIN" if resolved.pending else "COMMIT_READY"
                record("employee_flow", text + " -> " + answer, want, got)

staff = run_intent({"ctx": context("ali ko employee add karo 03331234567", role="employee"),
                    "classification": ClassifierOutput(intent="add_employee", language="roman_ur",
                                                       fields={"name": "Ali", "phone": "03331234567"})})["outcome"]
record("authorization", "employee tries to add Ali", "OWNER_ONLY",
       "OWNER_ONLY" if "maalik" in staff.reply.lower() else "OTHER")
record("pending_routing", "haan ji after confirmation", True, is_trivial_answer("haan ji", "yes_no"))

counts = {s: sum(r["status"] == s for r in RESULTS) for s in ("PASS", "FAIL")}
print(json.dumps({"summary": counts, "results": RESULTS}, ensure_ascii=False, indent=2))
