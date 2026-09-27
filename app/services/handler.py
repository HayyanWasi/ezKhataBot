"""The message pipeline, shared by every channel (CLI now, WhatsApp later).

handle_message() runs four phases:
  1. claim  - save the incoming message by its provider id (duplicate check)
  2. think  - the LangGraph agent (app/ai/agent.py) decides an Outcome (no DB transaction held)
  3. commit - one transaction: handler writes + pending state + prepared reply
  4. send   - deliver the saved reply; delivery tracked separately
"""

import logging
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import UUID

from langsmith import traceable
from psycopg import Connection

from app.ai import agent
from app.channels.base import Channel
from app.core.config import get_settings
from app.core.database import transaction
from app.db import crud
from app.schemas.khata import PendingAction
from app.services.registry import Context, Outcome
from app.services.replies import detect_language, t

log = logging.getLogger("ezkhata")


class Result(StrEnum):
    PROCESSED = "processed"
    RESENT = "resent"  # duplicate: saved reply delivered again
    DUPLICATE_IGNORED = "duplicate_ignored"  # duplicate: already handled
    IN_PROGRESS = "in_progress"  # duplicate: another attempt is still running
    NOT_REGISTERED = "not_registered"


class SimulatedCrash(Exception):
    """Dev only: stop between think and commit, like a process dying."""


DEV = {"crash_before_commit": False}


def _trace_message_inputs(inputs: dict) -> dict:
    """What LangSmith shows for an incoming message: channel name, masked phone."""
    return {
        "channel": inputs["channel"].name,
        "external_id": inputs["external_id"],
        "phone": "***" + inputs["phone"][-4:],
        "text": inputs["text"],
    }


@traceable(name="handle_message", run_type="chain", process_inputs=_trace_message_inputs)
def handle_message(channel: Channel, external_id: str, phone: str, text: str) -> Result:
    text = text.strip()
    settings = get_settings()

    # ---- Phase 1: claim -------------------------------------------------
    with transaction() as conn:
        user = crud.get_user_by_phone(conn, phone)
        if user is None:
            conversation = message = None
        else:
            conversation = crud.get_or_create_conversation(conn, user["id"], channel.name)
            message = crud.claim_user_message(conn, conversation["id"], external_id, text)
            if message is None:
                action, row = _check_duplicate(
                    conn, conversation["id"], external_id, settings.processing_lease_seconds
                )

    if user is None:
        _send_unsaved(channel, phone, t("not_registered", detect_language(text)))
        return Result.NOT_REGISTERED

    if message is None:
        if action == "resend":
            log.info("duplicate %s: resending saved reply", external_id)
            _send(channel, phone, row)
            return Result.RESENT
        if action == "ignore":
            log.info("duplicate %s: already handled, ignored", external_id)
            return Result.DUPLICATE_IGNORED
        if action == "in_progress":
            log.info("duplicate %s: still being processed, ignored", external_id)
            return Result.IN_PROGRESS
        log.info("duplicate %s: previous attempt died before commit, resuming", external_id)
        message = row

    # ---- Phase 2 + 3: think, commit -------------------------------------
    try:
        outcome, business_id = _think(user, conversation["id"], message)
        if DEV["crash_before_commit"]:
            DEV["crash_before_commit"] = False
            raise SimulatedCrash("simulated crash before commit")
        reply = _commit(conversation["id"], message["id"], outcome, business_id)
    except SimulatedCrash:
        raise
    except Exception as e:
        log.exception("processing failed for %s", external_id)
        reply = _commit_failure(conversation["id"], message["id"], e, detect_language(text))

    if reply is None:  # another attempt committed first
        return Result.IN_PROGRESS

    # ---- Phase 4: send --------------------------------------------------
    _send(channel, phone, reply)
    return Result.PROCESSED


# ---------------------------------------------------------------------------
# Phase 1 helpers
# ---------------------------------------------------------------------------


def _check_duplicate(
    conn: Connection, conversation_id: UUID, external_id: str, lease_seconds: int
) -> tuple[str, dict | None]:
    message = crud.get_user_message(conn, conversation_id, external_id)
    if message["processing_status"] == "received":
        taken = crud.take_over_stale_message(conn, message["id"], lease_seconds)
        return ("process", taken) if taken else ("in_progress", None)
    reply = crud.get_reply(conn, message["id"])
    if reply and reply["delivery_status"] in ("pending", "failed"):
        return "resend", reply
    return "ignore", None


# ---------------------------------------------------------------------------
# Phase 2: think (load context, then the LangGraph agent decides)
# ---------------------------------------------------------------------------


def _think(user: dict, conversation_id: UUID, message: dict) -> tuple[Outcome, UUID | None]:
    settings = get_settings()
    with transaction() as conn:
        conversation = crud.get_conversation(conn, conversation_id)
        businesses = crud.list_user_businesses(conn, user["id"])
        preference = crud.get_language_preference(conn, user["id"])
        history = crud.recent_messages(conn, conversation_id, message["id"], settings.history_limit)

    pending = None
    if conversation["pending_action"] and conversation["pending_expires_at"] > datetime.now(timezone.utc):
        pending = PendingAction.model_validate(conversation["pending_action"])

    text = message["text"]
    # Commands and bare numbers carry no language: fall back to the pending
    # question's language, then to the user's previous message
    last_user_text = next((m["text"] for m in reversed(history) if m["role"] == "user"), "")
    fallback = pending.language if pending else detect_language(last_user_text)
    language = preference or (fallback if text.startswith("/") else detect_language(text, default=fallback))
    # The agent doesn't need the phone; leaving it out keeps it out of LangSmith traces
    agent_user = {k: v for k, v in user.items() if k != "phone"}
    ctx = Context(agent_user, conversation, None, businesses, language, text)

    if not businesses:
        return Outcome("no_business", t("no_business", language)), None

    active_id = conversation["active_business_id"]
    ctx.business = ctx.business_by_id(active_id) if active_id else None
    if ctx.business is None and len(businesses) == 1:
        ctx.business = businesses[0]

    outcome = agent.decide(ctx, pending, history, preference)

    # Save an auto-selected (only) business as the active one
    if (
        outcome.active_business_id is None
        and ctx.business is not None
        and str(ctx.business["id"]) != str(active_id)
    ):
        outcome.active_business_id = ctx.business["id"]
    business_id = outcome.active_business_id or (ctx.business["id"] if ctx.business else None)
    return outcome, business_id


# ---------------------------------------------------------------------------
# Phase 3: commit
# ---------------------------------------------------------------------------


@traceable(
    name="commit",
    process_inputs=lambda i: {"message_id": str(i["message_id"]), "intent": i["outcome"].intent},
    process_outputs=lambda reply: {"reply": reply["text"] if reply else None},
)
def _commit(
    conversation_id: UUID, message_id: UUID, outcome: Outcome, business_id: UUID | None
) -> dict | None:
    """Handler writes, pending state and the prepared reply: all or nothing."""
    ttl = timedelta(seconds=get_settings().pending_ttl_seconds)
    with transaction() as conn:
        if crud.lock_user_message(conn, message_id)["processing_status"] != "received":
            return None
        reply_text = outcome.commit(conn) if outcome.commit else outcome.reply
        if outcome.active_business_id:
            crud.set_active_business(conn, conversation_id, outcome.active_business_id)
        if outcome.pending:
            crud.set_pending(
                conn,
                conversation_id,
                outcome.pending.model_dump(),
                reply_text,
                datetime.now(timezone.utc) + ttl,
            )
        else:
            crud.clear_pending(conn, conversation_id)
        reply = crud.insert_bot_reply(conn, conversation_id, message_id, reply_text, business_id, outcome.intent)
        crud.finish_user_message(conn, message_id, "processed", business_id, outcome.intent)
    return reply


def _commit_failure(
    conversation_id: UUID, message_id: UUID, error: Exception, language: str
) -> dict | None:
    with transaction() as conn:
        if crud.lock_user_message(conn, message_id)["processing_status"] != "received":
            return None
        reply = crud.insert_bot_reply(conn, conversation_id, message_id, t("error", language), None, None)
        crud.finish_user_message(conn, message_id, "failed", error=repr(error))
    return reply


# ---------------------------------------------------------------------------
# Phase 4: send
# ---------------------------------------------------------------------------


@traceable(name="send", process_inputs=lambda i: {"reply_id": str(i["reply"]["id"]), "text": i["reply"]["text"]})
def _send(channel: Channel, phone: str, reply: dict) -> bool:
    try:
        provider_message_id = channel.send(phone, reply["text"])
    except Exception as e:
        log.warning("send failed for reply %s: %s", reply["id"], e)
        with transaction() as conn:
            crud.record_send_failure(conn, reply["id"], repr(e))
        return False
    with transaction() as conn:
        crud.record_send_success(conn, reply["id"], provider_message_id)
    return True


def _send_unsaved(channel: Channel, phone: str, text: str) -> None:
    """Reply to an unknown number; nothing is stored for them."""
    try:
        channel.send(phone, text)
    except Exception as e:
        log.warning("send to unregistered %s failed: %s", phone, e)
