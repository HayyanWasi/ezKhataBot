"""Shop employees, managed by the owner on WhatsApp.

    "Bilal ko employee add karo 03001234567"  -> haan/nahi -> Bilal can use the bot for this shop
    "employees dikhao"                         -> the list
    "Bilal ko employee se hatao"               -> haan/nahi -> removed

A new employee gets a welcome message from the bot. What staff may do is decided by each
intent (owner_only); employees can be in several shops ("dukaan badlo").
"""

import re

from psycopg import Connection

from app.core.database import transaction
from app.core.phone import typed_phone
from app.db import crud
from app.schemas.khata import EmployeeFields, PendingAction
from app.services.answers import parse_yes_no
from app.services.registry import Context, Outcome, intent, pending_resolver
from app.services.replies import numbered, t
from app.tools import employees as tools
from app.tools.party import nice_name


def _number(phone: str) -> str:
    """923001234567 -> 0300-1234567 (how Pakistani numbers are written)."""
    return f"0{phone[2:5]}-{phone[5:]}" if phone.startswith("92") and len(phone) == 12 else phone


@intent(
    "add_employee",
    "The OWNER adds a shop employee / worker / staff (salesman, munshi) who will use the bot from their own "
    "WhatsApp number. name and phone as written.",
    fields=EmployeeFields,
    fields_hint='{"name": string | null, "phone": string | null}',
    examples=["Bilal ko employee add karo 03001234567", "employee add karna hai", "usman ko staff me dal"],
    needs_business=True,
    owner_only=True,
)
def add_employee(ctx: Context, fields: EmployeeFields) -> Outcome:
    return _add(ctx, fields.name, fields.phone)


def _add(ctx: Context, name: str | None, typed: str | None, invalid: bool = False) -> Outcome:
    """Ask for what is missing (name, then number), keeping what was already said; then confirm."""
    language = ctx.language
    phone = None
    if typed and any(c.isdigit() for c in typed):  # "number" / "baad mein" is no number yet
        try:
            phone = typed_phone(typed)
        except ValueError:
            invalid = True
    if not name or not phone:
        question = t("employee_ask_name", language) if not name else t("employee_ask_phone", language, name=name)
        if invalid:
            question = t("invalid_phone", language) + "\n" + question
        pending = PendingAction(kind="employee_details", language=language,
                                expects="text" if not name else "phone",
                                data={"name": name, "phone": phone})
        return Outcome("add_employee", question, pending=pending)
    business = ctx.business
    with transaction() as conn:
        user = crud.get_user_by_phone(conn, phone)
        if user and str(user["id"]) == str(business["owner_id"]):
            return Outcome("add_employee", t("employee_is_owner", language))
        if user and tools.is_employee(conn, business["id"], user["id"]):
            return Outcome("add_employee", t("employee_exists", language, name=user["name"]))
    name = user["name"] if user else nice_name(name)
    question = t("employee_confirm_add", language, name=name, number=_number(phone), shop=business["name"])
    pending = PendingAction(kind="confirm_add_employee", language=language, expects="yes_no",
                            data={"phone": phone, "name": name})
    return Outcome("add_employee", question, pending=pending)


_PHONE_IN_TEXT = re.compile(r"\+?\d[\d\s-]{3,18}\d")


@pending_resolver("employee_details")
def resolve_employee_details(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    """The answer to "naam kya hai?" / "number kya hai?": a name, a number, or both ("Rizwan 0333...")."""
    name, phone = pending.data.get("name"), pending.data.get("phone")
    found = _PHONE_IN_TEXT.search(answer)
    typed = found.group() if found else None
    rest = (answer[:found.start()] + answer[found.end():]) if found else answer
    rest = re.sub(r"\b(ka|ki|ke|number|no|naam|name|hai|he|whatsapp)\b", " ", rest, flags=re.IGNORECASE)
    rest = re.sub(r"[^\w\s]", " ", rest).strip()
    if not name and rest and not re.search(r"\d", rest):
        name = rest
    if typed is None:
        return _add(ctx, name, phone, invalid=bool(name and pending.data.get("name")))
    return _add(ctx, name, typed)


@pending_resolver("confirm_add_employee")
def resolve_add_employee(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("add_employee", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("add_employee", t("cancelled", ctx.language))
    business, phone, name = ctx.business, pending.data["phone"], pending.data["name"]

    def commit(conn: Connection) -> str:
        user = tools.add_employee(conn, business["id"], phone, name, ctx.user["id"])
        language = crud.get_language_preference(conn, user["id"]) or ctx.language
        welcome = t("employee_welcome", language, name=user["name"], shop=business["name"],
                    owner=ctx.user.get("name") or "")
        crud.queue_notice(conn, user["id"], ctx.conversation["channel"], welcome, business["id"])
        return t("employee_added", ctx.language, name=user["name"], number=_number(phone))

    return Outcome("add_employee", commit=commit)


@intent(
    "list_employees",
    "The OWNER asks which employees / staff the shop has.",
    examples=["employees dikhao", "mere staff mein kaun kaun hai", "employee list"],
    needs_business=True,
    owner_only=True,
)
def list_employees(ctx: Context, fields) -> Outcome:
    with transaction() as conn:
        rows = tools.list_employees(conn, ctx.business["id"])
    if not rows:
        return Outcome("list_employees", t("employees_none", ctx.language))
    items = [f"{r['name']} · {_number(r['phone'])}" for r in rows]
    return Outcome("list_employees", t("employees_list", ctx.language, n=len(rows), items=numbered(items)))


@intent(
    "remove_employee",
    "The OWNER removes an employee / staff member from the shop (they can no longer use the bot for it).",
    fields=EmployeeFields,
    fields_hint='{"name": string | null, "phone": string | null}',
    examples=["Bilal ko employee se hatao", "Ahmed ko staff se nikal do", "remove employee 03001234567"],
    needs_business=True,
    owner_only=True,
)
def remove_employee(ctx: Context, fields: EmployeeFields) -> Outcome:
    word = fields.phone or fields.name
    if not word:
        return list_employees(ctx, None)
    with transaction() as conn:
        matches = tools.find_employee(conn, ctx.business["id"], word)
    if not matches:
        return Outcome("remove_employee", t("employee_not_found", ctx.language, name=word))
    if len(matches) > 1:
        items = [f"{m['name']} · {_number(m['phone'])}" for m in matches]
        return Outcome("remove_employee", t("employee_which", ctx.language, items=numbered(items)))
    who = matches[0]
    question = t("employee_confirm_remove", ctx.language, name=who["name"], shop=ctx.business["name"])
    pending = PendingAction(kind="confirm_remove_employee", language=ctx.language, expects="yes_no",
                            data={"user_id": str(who["id"]), "name": who["name"]})
    return Outcome("remove_employee", question, pending=pending)


@pending_resolver("confirm_remove_employee")
def resolve_remove_employee(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    yes = parse_yes_no(answer)
    if yes is None:
        return Outcome("remove_employee", t("answer_yes_no", ctx.language), pending=pending)
    if not yes:
        return Outcome("remove_employee", t("cancelled", ctx.language))
    business_id = ctx.business["id"]

    def commit(conn: Connection) -> str:
        tools.remove_employee(conn, business_id, pending.data["user_id"])
        return t("employee_removed", ctx.language, name=pending.data["name"])

    return Outcome("remove_employee", commit=commit)
