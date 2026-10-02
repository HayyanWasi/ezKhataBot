"""Queries for the foundation tables.

Every function takes an open connection; the caller decides the transaction
boundary (see app.core.database.transaction).
"""

from datetime import datetime
from uuid import UUID

from psycopg import Connection
from psycopg.types.json import Jsonb

Row = dict

# ---------------------------------------------------------------------------
# Users and businesses
# ---------------------------------------------------------------------------


def get_user_by_phone(conn: Connection, phone: str) -> Row | None:
    return conn.execute("select * from users where phone = %s", (phone,)).fetchone()


def create_user(conn: Connection, phone: str, name: str) -> Row:
    return conn.execute(
        "insert into users (phone, name) values (%s, %s) returning *", (phone, name)
    ).fetchone()


def create_business(conn: Connection, owner_id: UUID, name: str) -> Row:
    return conn.execute(
        "insert into businesses (owner_id, name) values (%s, %s) returning *", (owner_id, name)
    ).fetchone()


def bot_allowed(conn: Connection, phone: str) -> bool:
    """The bot answers this number: a registered user the admin hasn't turned off, with at least one open shop."""
    user = get_user_by_phone(conn, phone)
    return bool(user and user.get("disabled_at") is None and list_user_businesses(conn, user["id"]))


def list_user_businesses(conn: Connection, user_id: UUID) -> list[Row]:
    """Businesses the user can access (owner or active employee), oldest first, with role.
    A shop the admin turned off is left out."""
    return conn.execute(
        """
        select b.*, 'owner' as role
        from businesses b
        where b.owner_id = %(user_id)s and b.disabled_at is null
        union all
        select b.*, 'employee' as role
        from businesses b
        join business_employees e on e.business_id = b.id
        where e.user_id = %(user_id)s and e.status = 'active' and b.owner_id <> %(user_id)s
          and b.disabled_at is null
        order by created_at
        """,
        {"user_id": user_id},
    ).fetchall()


def can_access_business(conn: Connection, user_id: UUID, business_id: UUID) -> bool:
    row = conn.execute(
        "select user_can_access_business(%s, %s) as ok", (user_id, business_id)
    ).fetchone()
    return row["ok"]


# ---------------------------------------------------------------------------
# Conversations and pending question
# ---------------------------------------------------------------------------


def get_or_create_conversation(conn: Connection, user_id: UUID, channel: str) -> Row:
    conn.execute(
        """
        insert into conversations (user_id, channel) values (%s, %s)
        on conflict (user_id, channel) do nothing
        """,
        (user_id, channel),
    )
    return conn.execute(
        "select * from conversations where user_id = %s and channel = %s", (user_id, channel)
    ).fetchone()


def get_conversation(conn: Connection, conversation_id: UUID) -> Row:
    return conn.execute("select * from conversations where id = %s", (conversation_id,)).fetchone()


def set_active_business(conn: Connection, conversation_id: UUID, business_id: UUID) -> None:
    conn.execute(
        "update conversations set active_business_id = %s, updated_at = now() where id = %s",
        (business_id, conversation_id),
    )


def set_pending(
    conn: Connection, conversation_id: UUID, action: dict, question: str, expires_at: datetime
) -> None:
    conn.execute(
        """
        update conversations
        set pending_action = %s, pending_question = %s, pending_expires_at = %s, updated_at = now()
        where id = %s
        """,
        (Jsonb(action), question, expires_at, conversation_id),
    )


def clear_pending(conn: Connection, conversation_id: UUID) -> None:
    conn.execute(
        """
        update conversations
        set pending_action = null, pending_question = null, pending_expires_at = null, updated_at = now()
        where id = %s and pending_action is not null
        """,
        (conversation_id,),
    )


# ---------------------------------------------------------------------------
# Messages: claim -> commit -> send
# ---------------------------------------------------------------------------


def claim_user_message(
    conn: Connection, conversation_id: UUID, external_id: str, text: str, attachment_path: str | None = None
) -> Row | None:
    """Insert an incoming message (with its photo, if any). Returns None if this external_id was already received."""
    return conn.execute(
        """
        insert into messages
            (conversation_id, role, text, external_id, attachment_path, processing_status, processing_started_at)
        values (%s, 'user', %s, %s, %s, 'received', now())
        on conflict (conversation_id, external_id) where role = 'user' do nothing
        returning *
        """,
        (conversation_id, text, external_id, attachment_path),
    ).fetchone()


def get_user_message(conn: Connection, conversation_id: UUID, external_id: str) -> Row | None:
    return conn.execute(
        "select * from messages where conversation_id = %s and external_id = %s and role = 'user'",
        (conversation_id, external_id),
    ).fetchone()


def take_over_stale_message(conn: Connection, message_id: UUID, lease_seconds: int) -> Row | None:
    """Restart a message whose previous attempt died before commit. None if still within lease."""
    return conn.execute(
        """
        update messages set processing_started_at = now()
        where id = %s
          and processing_status = 'received'
          and processing_started_at < now() - make_interval(secs => %s)
        returning *
        """,
        (message_id, lease_seconds),
    ).fetchone()


def lock_user_message(conn: Connection, message_id: UUID) -> Row:
    return conn.execute("select * from messages where id = %s for update", (message_id,)).fetchone()


def finish_user_message(
    conn: Connection,
    message_id: UUID,
    status: str,
    business_id: UUID | None = None,
    intent: str | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        update messages set processing_status = %s, business_id = %s, intent = %s, error = %s
        where id = %s
        """,
        (status, business_id, intent, error, message_id),
    )


def queue_notice(conn: Connection, user_id: UUID, channel: str, text: str, business_id: UUID | None) -> Row:
    """A message the bot starts (a new employee's welcome, a low-stock alert to the owner). It is saved
    here, inside the caller's commit, and the scheduler sends it within seconds (and retries it)."""
    conversation = get_or_create_conversation(conn, user_id, channel)
    return insert_bot_reply(conn, conversation["id"], None, text, business_id, "notice")


def insert_bot_reply(
    conn: Connection,
    conversation_id: UUID,
    reply_to_id: UUID | None,
    text: str,
    business_id: UUID | None,
    intent: str | None,
    attachment_path: str | None = None,
) -> Row:
    """A bot message to send. reply_to_id is None for messages the bot starts (reminders)."""
    return conn.execute(
        """
        insert into messages
            (conversation_id, role, text, reply_to_id, business_id, intent, attachment_path, delivery_status)
        values (%s, 'bot', %s, %s, %s, %s, %s, 'pending')
        returning *
        """,
        (conversation_id, text, reply_to_id, business_id, intent, attachment_path),
    ).fetchone()


def get_reply(conn: Connection, user_message_id: UUID) -> Row | None:
    return conn.execute(
        "select * from messages where reply_to_id = %s and role = 'bot'", (user_message_id,)
    ).fetchone()


def record_send_success(conn: Connection, reply_id: UUID, provider_message_id: str | None) -> None:
    conn.execute(
        """
        update messages
        set delivery_status = 'sent', provider_message_id = %s, send_attempts = send_attempts + 1,
            sent_at = now(), last_send_error = null
        where id = %s
        """,
        (provider_message_id, reply_id),
    )


def record_send_failure(conn: Connection, reply_id: UUID, error: str) -> None:
    conn.execute(
        """
        update messages
        set delivery_status = 'failed', send_attempts = send_attempts + 1, last_send_error = %s
        where id = %s
        """,
        (error, reply_id),
    )


def recent_messages(
    conn: Connection, conversation_id: UUID, exclude_id: UUID, limit: int
) -> list[Row]:
    """Last `limit` messages (user and bot) before the current one, oldest first."""
    rows = conn.execute(
        """
        select role, text from messages
        where conversation_id = %s and id <> %s
        order by created_at desc
        limit %s
        """,
        (conversation_id, exclude_id, limit),
    ).fetchall()
    return list(reversed(rows))


# ---------------------------------------------------------------------------
# Preferences and memories
# ---------------------------------------------------------------------------


def get_language_preference(conn: Connection, user_id: UUID) -> str | None:
    row = conn.execute(
        "select language from user_preferences where user_id = %s", (user_id,)
    ).fetchone()
    return row["language"] if row else None


def set_language_preference(conn: Connection, user_id: UUID, language: str | None) -> None:
    conn.execute(
        """
        insert into user_preferences (user_id, language) values (%s, %s)
        on conflict (user_id) do update set language = excluded.language, updated_at = now()
        """,
        (user_id, language),
    )


def add_user_memory(conn: Connection, user_id: UUID, content: str) -> Row:
    return conn.execute(
        "insert into user_memories (user_id, content) values (%s, %s) returning *",
        (user_id, content),
    ).fetchone()


def add_business_memory(conn: Connection, business_id: UUID, created_by: UUID, content: str) -> Row:
    return conn.execute(
        "insert into business_memories (business_id, created_by, content) values (%s, %s, %s) returning *",
        (business_id, created_by, content),
    ).fetchone()


def list_user_memories(conn: Connection, user_id: UUID) -> list[Row]:
    return conn.execute(
        "select * from user_memories where user_id = %s and deleted_at is null order by created_at",
        (user_id,),
    ).fetchall()


def list_business_memories(conn: Connection, business_id: UUID) -> list[Row]:
    return conn.execute(
        "select * from business_memories where business_id = %s and deleted_at is null order by created_at",
        (business_id,),
    ).fetchall()


def delete_user_memory(conn: Connection, memory_id: UUID, user_id: UUID) -> None:
    conn.execute(
        "update user_memories set deleted_at = now() where id = %s and user_id = %s",
        (memory_id, user_id),
    )


def delete_business_memory(conn: Connection, memory_id: UUID, business_id: UUID) -> None:
    conn.execute(
        "update business_memories set deleted_at = now() where id = %s and business_id = %s",
        (memory_id, business_id),
    )
