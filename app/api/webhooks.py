"""Evolution webhook: WhatsApp messages come in here.

Evolution posts every new message to /webhook/evolution/<WEBHOOK_SECRET>. The request is answered
at once and the message is handled in the background (the AI can take several seconds), one
message at a time per phone, so a shopkeeper's quick messages are handled in the order sent.

Skipped without a reply: our own messages, groups, status updates, messages older than
MESSAGE_MAX_AGE_SECONDS (the bot was down), and numbers that are not registered."""

import hmac
import logging
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.channels.whatsapp import WhatsAppChannel
from app.core.config import get_settings
from app.core.database import transaction
from app.core.phone import normalize_phone
from app.db import crud
from app.services import evolution, handler
from app.services.replies import detect_language, t

log = logging.getLogger("ezkhata.webhook")
router = APIRouter()
channel = WhatsAppChannel()

# Kinds that get "text or photo only"; anything else (reactions, edits, deletes, receipts) is ignored
UNSUPPORTED = {
    "audioMessage", "videoMessage", "stickerMessage", "documentMessage", "documentWithCaptionMessage",
    "contactMessage", "contactsArrayMessage", "locationMessage", "liveLocationMessage", "ptvMessage",
}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


@dataclass
class Incoming:
    external_id: str
    phone: str
    text: str
    kind: str  # text | image | unsupported
    data: dict  # Evolution's message, needed to download a photo


def _phone(key: dict, data: dict) -> str | None:
    jid = key.get("remoteJid") or ""
    if jid.endswith("@lid"):  # WhatsApp's hidden id: the real number comes alongside
        jid = key.get("remoteJidAlt") or key.get("senderPn") or data.get("senderPn") or ""
    if not jid.endswith("@s.whatsapp.net"):  # groups, status, channels, unknown ids
        return None
    try:
        return normalize_phone(jid.split("@")[0])
    except ValueError:
        return None


def parse(data: dict) -> Incoming | None:
    """One Evolution `messages.upsert` item -> what the bot needs, or None to skip it."""
    key = data.get("key") or {}
    log.debug("upsert key=%s keys=%s message=%s", key, sorted(data), sorted(data.get("message") or {}))
    if key.get("fromMe") or not key.get("id"):
        return None
    phone = _phone(key, data)
    if phone is None:
        log.info("no phone number in %s, skipped", key.get("remoteJid"))
        return None
    sent_at = int(data.get("messageTimestamp") or 0)
    if sent_at and time.time() - sent_at > get_settings().message_max_age_seconds:
        log.info("old message %s from %s skipped", key["id"], phone)
        return None

    message = data.get("message") or {}
    if "imageMessage" in message:
        caption = message["imageMessage"].get("caption") or ""
        return Incoming(key["id"], phone, caption, "image", data)
    text = message.get("conversation") or (message.get("extendedTextMessage") or {}).get("text") or ""
    if text.strip():
        return Incoming(key["id"], phone, text, "text", data)
    if UNSUPPORTED & message.keys():
        return Incoming(key["id"], phone, "", "unsupported", data)
    return None


def _lock(phone: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(phone, threading.Lock())


def process(msg: Incoming) -> None:
    with _lock(msg.phone):
        try:
            with transaction() as conn:
                registered = crud.get_user_by_phone(conn, msg.phone) is not None
            if not registered:  # only chosen numbers use the bot; others get no reply
                log.info("unregistered %s ignored", msg.phone)
                return
            if msg.kind == "unsupported":
                channel.send(msg.phone, t("text_or_photo_only", detect_language(msg.text)))
                return
            if msg.kind == "image":
                _handle_photo(msg)
                return
            handler.handle_message(channel, msg.external_id, msg.phone, msg.text)
        except Exception:
            log.exception("webhook message %s from %s failed", msg.external_id, msg.phone)


def _handle_photo(msg: Incoming) -> None:
    content, mimetype = evolution.download_media(msg.data)
    suffix = ".png" if "png" in mimetype else ".webp" if "webp" in mimetype else ".jpg"
    # The handler copies the photo into storage/uploads, so the download is only temporary
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(content)
    try:
        handler.handle_message(channel, msg.external_id, msg.phone, msg.text, image_path=f.name)
    finally:
        Path(f.name).unlink(missing_ok=True)


@router.post("/webhook/evolution/{secret}")
async def evolution_webhook(secret: str, request: Request, background: BackgroundTasks) -> dict:
    expected = get_settings().webhook_secret
    if not expected or not hmac.compare_digest(secret, expected):
        raise HTTPException(status_code=404)
    payload = await request.json()
    if str(payload.get("event", "")).lower().replace("_", ".") != "messages.upsert":
        return {"ok": True}
    items = payload.get("data")
    for data in items if isinstance(items, list) else [items or {}]:
        msg = parse(data)
        if msg:
            background.add_task(process, msg)
    return {"ok": True}
