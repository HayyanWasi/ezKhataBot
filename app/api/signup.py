"""Public signup: a shopkeeper asks for the bot. The admin approves it in the dashboard.

POST /api/signup  {name, phone, shop_name, username, password, website}
`website` is a hidden field real people leave empty (bots fill it in). Max SIGNUP_PER_IP_PER_HOUR per IP."""

import re
import threading
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.database import transaction
from app.core.phone import normalize_phone
from app.core.security import hash_password

router = APIRouter(prefix="/api")

USERNAME = re.compile(r"^[a-z0-9_.]{3,30}$")
_hits: dict[str, list[float]] = defaultdict(list)
_hits_lock = threading.Lock()


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=10, max_length=20)
    shop_name: str = Field(min_length=1, max_length=80)
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=6, max_length=100)
    website: str = ""  # honeypot


def client_ip(request: Request) -> str:
    """Render puts the visitor's address first in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")


def too_many(key: str, limit: int, seconds: int = 3600) -> bool:
    now = time.time()
    with _hits_lock:
        recent = [t for t in _hits[key] if now - t < seconds]
        _hits[key] = recent
        if len(recent) >= limit:
            return True
        recent.append(now)
        return False


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.post("/signup")
def signup(body: SignupIn, request: Request) -> dict:
    if body.website:  # a bot filled the hidden field: pretend it worked
        return {"ok": True}
    if too_many(f"signup:{client_ip(request)}", get_settings().signup_per_ip_per_hour):
        raise _fail(429, "too_many", "Bohot zyada koshishen. Thori der baad try karein.")
    try:
        phone = normalize_phone(body.phone)
    except ValueError:
        raise _fail(400, "bad_phone", "WhatsApp number theek nahi. Jaise: 03001234567")
    username = body.username.strip().lower()
    if not USERNAME.match(username):
        raise _fail(400, "bad_username", "Username mein sirf chhote angrezi harf, number, _ aur . (3-30)")

    with transaction() as conn:
        if conn.execute("select 1 from users where phone = %s", (phone,)).fetchone():
            raise _fail(409, "phone_registered", "Yeh number pehle se EzKhata par hai.")
        if conn.execute("select 1 from signup_requests where phone = %s and status = 'pending'", (phone,)).fetchone():
            raise _fail(409, "phone_pending", "Is number ki request pehle se pending hai.")
        taken = conn.execute(
            """select 1 from users where lower(username) = %(u)s
               union all select 1 from signup_requests where lower(username) = %(u)s and status = 'pending'""",
            {"u": username},
        ).fetchone()
        if taken:
            raise _fail(409, "username_taken", "Yeh username kisi aur ka hai. Doosra chunein.")
        conn.execute(
            """insert into signup_requests (name, phone, shop_name, username, password_hash)
               values (%s, %s, %s, %s, %s)""",
            (body.name.strip(), phone, body.shop_name.strip(), username, hash_password(body.password)),
        )
    return {"ok": True, "message": "Shukriya! Approve hote hi aap ka EzKhata bot WhatsApp par chal jaega."}
