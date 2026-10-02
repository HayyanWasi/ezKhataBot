import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL") or os.getenv("SERVER_URL") or "http://localhost:8080"
API_KEY = os.getenv("API_KEY") or os.getenv("AUTHENTICATION_API_KEY")
INSTANCE = os.getenv("INSTANCE") or "ezkhata"
MY_NUMBER = os.getenv("ALLOWED_NUMBER") or os.getenv("MY_NUMBER")


def is_authorized(payload: dict) -> str | None:
    """Returns command if from MY_NUMBER and starts with 'bot', otherwise None."""
    data = payload.get("data", {})
    sender = data.get("key", {}).get("remoteJid", "").split("@")[0]

    if not MY_NUMBER or sender != MY_NUMBER:
        return None

    msg = data.get("message", {})
    text = (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
        or ""
    ).strip()

    # Only activate if message starts with "bot" (case-insensitive)
    if not text.lower().startswith("bot"):
        return None

    # Return the clean command without the 'bot' prefix (e.g. 'bot 500 coffee' -> '500 coffee')
    clean_command = text[3:].lstrip(": ").strip()
    return clean_command if clean_command else "bot"


def send_reply(text: str) -> bool:
    """Sends a WhatsApp reply strictly to MY_NUMBER only."""
    if not MY_NUMBER:
        return False

    url = f"{API_URL}/message/sendText/{INSTANCE}"
    res = requests.post(
        url,
        json={"number": MY_NUMBER, "text": text},
        headers={"apikey": API_KEY, "Content-Type": "application/json"},
        timeout=10,
    )
    return res.status_code in (200, 201)
