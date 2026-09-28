"""Delivering reminders when they are due. Called by the scheduler (app/core/scheduler.py).

    1. claim   - one transaction: take due sends (locked), save each as a bot message, mark it queued
    2. send    - deliver each saved message through its channel (same send tracking as replies)
    3. retry   - reminder messages that failed, or were never sent, get up to 3 attempts
"""

import logging
from datetime import datetime, timezone

from langsmith import traceable

from app.channels.base import Channel
from app.core.database import transaction
from app.db import crud
from app.handlers.party import balance_line
from app.services.handler import send_saved_message
from app.services.replies import t
from app.tools import party as party_tools
from app.tools import reminders as tools

log = logging.getLogger("ezkhata.reminders")


def run_due_reminders(channels: dict[str, Channel]) -> int:
    """Send everything that is due. Returns how many reminders were sent out."""
    with transaction() as conn:
        due = tools.claim_due_sends(conn, datetime.now(timezone.utc))
        queued = [(row, _queue(conn, row)) for row in due]

    if queued:
        _deliver(channels, queued)

    with transaction() as conn:
        retries = tools.unsent_reminder_messages(conn)
    for message in retries:
        channel = channels.get(message["channel"])
        if channel:
            log.info("retrying reminder message %s (attempt %d)", message["id"], message["send_attempts"] + 1)
            send_saved_message(channel, message["phone"], message)
    return len(queued)


def _queue(conn, row: dict) -> dict:
    """Save the reminder as a bot message (inside the claim transaction)."""
    text = t("reminder_fire", row["language"], text=row["text"])
    if row["account_id"]:
        party = party_tools.get_party(conn, row["business_id"], row["account_id"])
        if party:
            balance = party_tools.get_balance(conn, row["business_id"], party["id"])
            text += "\n" + balance_line(row["language"], party["name"], balance)
    message = crud.insert_bot_reply(conn, row["conversation_id"], None, text, row["business_id"], "reminder")
    tools.mark_queued(conn, row["send_id"], message["id"])
    return message


@traceable(
    name="reminders_run",
    process_inputs=lambda i: {"count": len(i["queued"]), "texts": [m["text"] for _, m in i["queued"]]},
)
def _deliver(channels: dict[str, Channel], queued: list[tuple[dict, dict]]) -> None:
    for row, message in queued:
        channel = channels.get(row["channel"])
        if channel is None:  # e.g. a WhatsApp reminder while only the CLI runs: retried later
            log.warning("no %s channel running for reminder message %s", row["channel"], message["id"])
            continue
        send_saved_message(channel, row["phone"], message)
