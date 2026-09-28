"""Reminder tools: the ONLY code that reads or writes reminders.

The AI never calls these. Scoped to one business and one user, except the
scheduler tools (claim_due_sends, unsent_reminder_messages), which work across
all shops because they only deliver what users already asked for.
"""

from datetime import date, datetime, time

from psycopg import Connection

from app.tools.party import Id


def create_reminder(
    conn: Connection,
    *,
    business_id: Id,
    user_id: Id,
    conversation_id: Id,
    language: str,
    text: str,
    account_id: Id | None,
    remind_date: date,
    remind_time: time | None,
    send_times: list[datetime],
    message_id: Id,
) -> dict:
    """One reminder + one send row per moment it should go out."""
    reminder = conn.execute(
        """
        insert into reminders (business_id, user_id, conversation_id, language, text, account_id,
                               remind_date, remind_time, source_message_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        returning *
        """,
        (business_id, user_id, conversation_id, language, text, account_id, remind_date, remind_time, message_id),
    ).fetchone()
    for send_at in send_times:
        conn.execute("insert into reminder_sends (reminder_id, send_at) values (%s, %s)", (reminder["id"], send_at))
    return reminder


def list_upcoming(conn: Connection, business_id: Id, user_id: Id, limit: int = 10) -> list[dict]:
    """The user's live reminders that still have something to send, soonest first."""
    return conn.execute(
        """
        select r.id, r.text, r.account_id, min(s.send_at) as next_send
        from reminders r join reminder_sends s on s.reminder_id = r.id and s.status = 'pending'
        where r.business_id = %s and r.user_id = %s and r.cancelled_at is null
        group by r.id
        order by next_send
        limit %s
        """,
        (business_id, user_id, limit),
    ).fetchall()


def cancel_reminder(conn: Connection, business_id: Id, user_id: Id, reminder_id: Id) -> bool:
    row = conn.execute(
        """
        update reminders set cancelled_at = now()
        where id = %s and business_id = %s and user_id = %s and cancelled_at is null
        returning id
        """,
        (reminder_id, business_id, user_id),
    ).fetchone()
    if row is None:
        return False
    conn.execute(
        "update reminder_sends set status = 'cancelled' where reminder_id = %s and status = 'pending'",
        (reminder_id,),
    )
    return True


# ---------------------------------------------------------------------------
# Scheduler tools
# ---------------------------------------------------------------------------


def claim_due_sends(conn: Connection, now: datetime, limit: int = 20) -> list[dict]:
    """Due sends, locked for this transaction. `skip locked` means two schedulers
    can never take the same send; the caller marks each one queued before commit."""
    return conn.execute(
        """
        select s.id as send_id, r.id as reminder_id, r.business_id, r.conversation_id, r.language,
               r.text, r.account_id, c.channel, u.phone
        from reminder_sends s
        join reminders r on r.id = s.reminder_id
        join conversations c on c.id = r.conversation_id
        join users u on u.id = r.user_id
        where s.status = 'pending' and s.send_at <= %s and r.cancelled_at is null
        order by s.send_at
        for update of s skip locked
        limit %s
        """,
        (now, limit),
    ).fetchall()


def mark_queued(conn: Connection, send_id: Id, message_id: Id) -> None:
    conn.execute(
        "update reminder_sends set status = 'queued', message_id = %s where id = %s and status = 'pending'",
        (message_id, send_id),
    )


def unsent_reminder_messages(conn: Connection, max_attempts: int = 3, older_than_seconds: int = 60) -> list[dict]:
    """Reminder messages that failed (or were never sent because the process stopped)."""
    return conn.execute(
        """
        select m.*, c.channel, u.phone
        from messages m
        join conversations c on c.id = m.conversation_id
        join users u on u.id = c.user_id
        where m.role = 'bot' and m.intent = 'reminder'
          and m.delivery_status in ('pending', 'failed') and m.send_attempts < %s
          and m.created_at < now() - make_interval(secs => %s)
        order by m.created_at
        limit 20
        """,
        (max_attempts, older_than_seconds),
    ).fetchall()
