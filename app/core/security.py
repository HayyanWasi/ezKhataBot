"""Passwords and admin tokens, with the standard library only.

Passwords are stored as "pbkdf2_sha256$<iterations>$<salt>$<hash>", never as typed.
An admin token is "<expiry unix time>.<HMAC of it>", signed with ADMIN_SECRET.

    uv run python -m app.core.security        (asks a password, prints its hash for ADMIN_PASSWORD_HASH)
"""

import base64
import hashlib
import hmac
import secrets
import time

ITERATIONS = 390_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${base64.b64encode(digest).decode()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$")
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
    return hmac.compare_digest(base64.b64encode(digest).decode(), expected)


def make_token(secret: str, hours: int = 12) -> str:
    expiry = str(int(time.time()) + hours * 3600)
    return f"{expiry}.{_sign(secret, expiry)}"


def token_ok(secret: str, token: str) -> bool:
    expiry, _, signature = token.partition(".")
    if not expiry.isdigit() or int(expiry) < time.time():
        return False
    return hmac.compare_digest(signature, _sign(secret, expiry))


def _sign(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), f"admin:{value}".encode(), hashlib.sha256).hexdigest()


if __name__ == "__main__":
    import getpass

    print(hash_password(getpass.getpass("Admin password: ")))
