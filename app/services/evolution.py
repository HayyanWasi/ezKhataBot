"""Evolution API calls (unofficial WhatsApp): send text and files, download a received photo.

Only this file knows Evolution's URLs and JSON shapes."""

import base64
import mimetypes
from pathlib import Path

import requests

from app.core.config import get_settings

TIMEOUT = 30  # seconds; a PDF upload can take a while


def _post(path: str, body: dict) -> dict:
    s = get_settings()
    res = requests.post(
        f"{s.evolution_api_url.rstrip('/')}{path}/{s.evolution_instance}",
        json=body,
        headers={"apikey": s.evolution_api_key},
        timeout=TIMEOUT,
    )
    if res.status_code >= 400:
        raise RuntimeError(f"Evolution {path} failed: {res.status_code} {res.text[:200]}")
    return res.json() if res.content else {}


def _message_id(data: dict) -> str | None:
    return (data.get("key") or {}).get("id")


def send_text(number: str, text: str) -> str | None:
    return _message_id(_post("/message/sendText", {"number": number, "text": text}))


def send_file(number: str, path: str, caption: str) -> str | None:
    """A PDF goes as a document, a photo as an image."""
    file = Path(path)
    mimetype = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    body = {
        "number": number,
        "mediatype": "image" if mimetype.startswith("image/") else "document",
        "mimetype": mimetype,
        "caption": caption,
        "media": base64.b64encode(file.read_bytes()).decode(),
        "fileName": file.name,
    }
    return _message_id(_post("/message/sendMedia", body))


def download_media(message: dict) -> tuple[bytes, str]:
    """The photo of a received message (the webhook's `data`) -> (bytes, mimetype).
    The whole message is sent back, so Evolution doesn't need to keep messages in its database."""
    body = {"message": {"key": message["key"], "message": message["message"]}, "convertToMp4": False}
    data = _post("/chat/getBase64FromMediaMessage", body)
    return base64.b64decode(data["base64"]), data.get("mimetype") or "image/jpeg"
