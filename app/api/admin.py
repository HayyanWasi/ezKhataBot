"""Super admin APIs for the dashboard (frontend on Vercel). Every route except login needs
`Authorization: Bearer <token>` from POST /api/admin/login.

No shop money is shown here: only shops, people, requests and how the bot is doing."""

import logging
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import transaction
from app.core.phone import normalize_phone
from app.core.security import check_password, make_token, token_ok
from app.api.signup import client_ip, too_many

log = logging.getLogger("ezkhata.admin")
PK = ZoneInfo("Asia/Karachi")


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def require_admin(authorization: str = Header(default="")) -> None:
    secret = get_settings().admin_secret
    token = authorization.removeprefix("Bearer ").strip()
    if not secret or not token or not token_ok(secret, token):
        raise _fail(401, "login_needed", "Dobara login karein.")


public = APIRouter(prefix="/api/admin")
router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class LoginIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


@public.post("/login")
def login(body: LoginIn, request: Request) -> dict:
    s = get_settings()
    if not (s.admin_username and s.admin_password_hash and s.admin_secret):
        raise _fail(503, "admin_off", "Admin login set nahi hai.")
    ip = client_ip(request)
    if too_many(f"login:{ip}", 5, 15 * 60):  # 5 tries per 15 minutes
        raise _fail(429, "too_many", "Bohot zyada ghalat koshishen. 15 minute baad try karein.")
    if body.username.strip().lower() != s.admin_username.lower() or not check_password(body.password, s.admin_password_hash):
        log.warning("admin login failed from %s", ip)
        raise _fail(401, "wrong_login", "Username ya password ghalat hai.")
    log.info("admin login from %s", ip)
    return {"token": make_token(s.admin_secret), "hours": 12}


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------


def _today_start() -> datetime:
    return datetime.combine(datetime.now(PK).date(), dtime.min, tzinfo=PK)


def _whatsapp_state() -> str:
    s = get_settings()
    try:
        res = requests.get(f"{s.evolution_api_url.rstrip('/')}/instance/connectionState/{s.evolution_instance}",
                           headers={"apikey": s.evolution_api_key}, timeout=8)
        return res.json().get("instance", {}).get("state", "unknown")
    except Exception:
        return "unreachable"


@router.get("/overview")
def overview() -> dict:
    with transaction() as conn:
        row = conn.execute(
            """
            select
              (select count(*) from businesses) as shops,
              (select count(*) from businesses where disabled_at is null) as shops_on,
              (select count(*) from users) as users,
              (select count(*) from business_employees where status = 'active') as employees,
              (select count(*) from signup_requests where status = 'pending') as pending_requests,
              (select count(*) from messages where role = 'user' and created_at >= %(today)s) as messages_today,
              (select count(*) from messages where role = 'user' and intent = 'unknown' and created_at >= %(today)s)
                as not_understood_today,
              (select count(*) from messages where role = 'user' and processing_status = 'failed'
                 and created_at >= %(today)s) as errors_today,
              (select count(*) from messages where role = 'bot' and delivery_status = 'failed'
                 and created_at >= %(today)s) as undelivered_today,
              (select count(distinct business_id) from messages where role = 'user' and created_at >= %(today)s)
                as active_shops_today
            """,
            {"today": _today_start()},
        ).fetchone()
    data = dict(row)
    total = data["messages_today"]
    data["not_understood_pct"] = round(100 * data["not_understood_today"] / total, 1) if total else 0
    data["whatsapp"] = _whatsapp_state()
    return data


# ---------------------------------------------------------------------------
# Signup requests
# ---------------------------------------------------------------------------


@router.get("/requests")
def list_requests(status: str = "pending") -> list[dict]:
    with transaction() as conn:
        return conn.execute(
            """select id, name, phone, shop_name, username, status, note, created_at, decided_at
               from signup_requests where %(status)s = 'all' or status = %(status)s
               order by created_at desc limit 200""",
            {"status": status},
        ).fetchall()


class DecideIn(BaseModel):
    note: str | None = Field(default=None, max_length=300)


@router.post("/requests/{request_id}/approve")
def approve(request_id: str, body: DecideIn | None = None) -> dict:
    with transaction() as conn:
        req = conn.execute("select * from signup_requests where id = %s for update", (request_id,)).fetchone()
        if not req or req["status"] != "pending":
            raise _fail(404, "not_pending", "Yeh request pending nahi hai.")
        if conn.execute("select 1 from users where phone = %s", (req["phone"],)).fetchone():
            raise _fail(409, "phone_registered", "Yeh number pehle se registered hai.")
        user = conn.execute(
            "insert into users (phone, name, username, password_hash) values (%s, %s, %s, %s) returning id",
            (req["phone"], req["name"], req["username"], req["password_hash"]),
        ).fetchone()
        conn.execute("insert into businesses (owner_id, name) values (%s, %s)", (user["id"], req["shop_name"]))
        conn.execute(
            """update signup_requests set status = 'approved', decided_at = now(), user_id = %s, note = %s
               where id = %s""",
            (user["id"], body.note if body else None, request_id),
        )
    log.info("signup %s approved", request_id)
    return {"ok": True, "user_id": user["id"]}


@router.post("/requests/{request_id}/reject")
def reject(request_id: str, body: DecideIn | None = None) -> dict:
    with transaction() as conn:
        done = conn.execute(
            """update signup_requests set status = 'rejected', decided_at = now(), note = %s
               where id = %s and status = 'pending'""",
            (body.note if body else None, request_id),
        ).rowcount
    if not done:
        raise _fail(404, "not_pending", "Yeh request pending nahi hai.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Shops and people
# ---------------------------------------------------------------------------


@router.get("/shops")
def list_shops() -> list[dict]:
    with transaction() as conn:
        return conn.execute(
            """
            select b.id, b.name, b.created_at, b.disabled_at,
                   u.id as owner_id, u.name as owner_name, u.phone as owner_phone, u.disabled_at as owner_disabled_at,
                   (select count(*) from business_employees e where e.business_id = b.id and e.status = 'active')
                     as employees,
                   (select count(*) from messages m where m.business_id = b.id and m.role = 'user') as messages,
                   (select max(m.created_at) from messages m where m.business_id = b.id and m.role = 'user')
                     as last_active
            from businesses b join users u on u.id = b.owner_id
            order by last_active desc nulls last, b.created_at desc
            """
        ).fetchall()


@router.get("/shops/{shop_id}")
def shop_detail(shop_id: str) -> dict:
    with transaction() as conn:
        shop = conn.execute(
            """select b.id, b.name, b.created_at, b.disabled_at, b.address, b.phone as shop_phone,
                      u.id as owner_id, u.name as owner_name, u.phone as owner_phone, u.username as owner_username,
                      u.disabled_at as owner_disabled_at
               from businesses b join users u on u.id = b.owner_id where b.id = %s""",
            (shop_id,),
        ).fetchone()
        if not shop:
            raise _fail(404, "no_shop", "Dukaan nahi mili.")
        employees = conn.execute(
            """select u.id, u.name, u.phone, u.disabled_at, e.status, e.created_at
               from business_employees e join users u on u.id = e.user_id
               where e.business_id = %s order by e.status, e.created_at""",
            (shop_id,),
        ).fetchall()
    return {**shop, "employees": employees}


def _set_disabled(table: str, row_id: str, off: bool) -> dict:
    with transaction() as conn:
        done = conn.execute(
            f"update {table} set disabled_at = {'now()' if off else 'null'} where id = %s", (row_id,)
        ).rowcount
    if not done:
        raise _fail(404, "not_found", "Nahi mila.")
    log.info("%s %s turned %s", table, row_id, "off" if off else "on")
    return {"ok": True}


@router.post("/shops/{shop_id}/disable")
def disable_shop(shop_id: str) -> dict:
    return _set_disabled("businesses", shop_id, True)


@router.post("/shops/{shop_id}/enable")
def enable_shop(shop_id: str) -> dict:
    return _set_disabled("businesses", shop_id, False)


@router.post("/users/{user_id}/disable")
def disable_user(user_id: str) -> dict:
    return _set_disabled("users", user_id, True)


@router.post("/users/{user_id}/enable")
def enable_user(user_id: str) -> dict:
    return _set_disabled("users", user_id, False)


class PersonIn(BaseModel):
    phone: str = Field(min_length=10, max_length=20)
    name: str = Field(min_length=1, max_length=80)


class ShopIn(PersonIn):
    shop_name: str = Field(min_length=1, max_length=80)


def _phone(raw: str) -> str:
    try:
        return normalize_phone(raw)
    except ValueError:
        raise _fail(400, "bad_phone", "Number theek nahi. Jaise: 03001234567")


@router.post("/shops")
def add_shop(body: ShopIn) -> dict:
    """The admin turns the bot on for any number directly (no signup, no payment)."""
    phone = _phone(body.phone)
    with transaction() as conn:
        user = conn.execute("select id from users where phone = %s", (phone,)).fetchone()
        if not user:
            user = conn.execute(
                "insert into users (phone, name) values (%s, %s) returning id", (phone, body.name.strip())
            ).fetchone()
        shop = conn.execute(
            "insert into businesses (owner_id, name) values (%s, %s) returning id", (user["id"], body.shop_name.strip())
        ).fetchone()
        conn.execute("update users set disabled_at = null where id = %s", (user["id"],))
    return {"ok": True, "shop_id": shop["id"]}


@router.post("/shops/{shop_id}/employees")
def add_employee(shop_id: str, body: PersonIn) -> dict:
    phone = _phone(body.phone)
    with transaction() as conn:
        shop = conn.execute("select owner_id from businesses where id = %s", (shop_id,)).fetchone()
        if not shop:
            raise _fail(404, "no_shop", "Dukaan nahi mili.")
        user = conn.execute("select id from users where phone = %s", (phone,)).fetchone()
        if not user:
            user = conn.execute(
                "insert into users (phone, name) values (%s, %s) returning id", (phone, body.name.strip())
            ).fetchone()
        if user["id"] == shop["owner_id"]:
            raise _fail(409, "is_owner", "Yeh number is dukaan ka malik hai.")
        conn.execute(
            """insert into business_employees (business_id, user_id, added_by) values (%s, %s, %s)
               on conflict (business_id, user_id) do update set status = 'active'""",
            (shop_id, user["id"], shop["owner_id"]),
        )
    return {"ok": True}


@router.delete("/shops/{shop_id}/employees/{user_id}")
def remove_employee(shop_id: str, user_id: str) -> dict:
    with transaction() as conn:
        done = conn.execute(
            "update business_employees set status = 'removed' where business_id = %s and user_id = %s",
            (shop_id, user_id),
        ).rowcount
    if not done:
        raise _fail(404, "not_found", "Employee nahi mila.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Chats and problems
# ---------------------------------------------------------------------------


@router.get("/chat/{user_id}")
def chat(user_id: str, limit: int = 200) -> dict:
    with transaction() as conn:
        user = conn.execute("select id, name, phone, disabled_at from users where id = %s", (user_id,)).fetchone()
        if not user:
            raise _fail(404, "not_found", "User nahi mila.")
        messages = conn.execute(
            """
            select * from (
              select m.id, m.role, m.text, m.intent, m.created_at, m.processing_status, m.delivery_status,
                     coalesce(m.error, m.last_send_error) as error, m.attachment_path is not null as file,
                     b.name as shop
              from messages m join conversations c on c.id = m.conversation_id
              left join businesses b on b.id = m.business_id
              where c.user_id = %s order by m.created_at desc limit %s
            ) x order by created_at
            """,
            (user_id, min(max(limit, 1), 1000)),
        ).fetchall()
    return {"user": user, "messages": messages}


@router.get("/problems")
def problems(days: int = 7) -> list[dict]:
    """Messages the bot didn't understand, failed to handle, or whose reply didn't reach the user."""
    with transaction() as conn:
        return conn.execute(
            """
            select m.id, m.created_at, m.text, m.intent, coalesce(m.error, m.last_send_error) as error,
                   case when m.role = 'bot' then 'undelivered'
                        when m.processing_status = 'failed' then 'error'
                        else 'not_understood' end as kind,
                   u.id as user_id, u.name as user_name, u.phone, b.name as shop
            from messages m join conversations c on c.id = m.conversation_id
            join users u on u.id = c.user_id
            left join businesses b on b.id = m.business_id
            where m.created_at >= now() - make_interval(days => %s)
              and ((m.role = 'user' and (m.intent = 'unknown' or m.processing_status = 'failed'))
                   or (m.role = 'bot' and m.delivery_status = 'failed'))
            order by m.created_at desc limit 300
            """,
            (min(max(days, 1), 90),),
        ).fetchall()
