"""Reminder intents: set, list, cancel. Reminders go only to the user who asked.

The AI gives the text, date and time. Code works out the exact send times
(in the shop's timezone) and refuses times in the past:
    date + time -> that moment
    time only   -> today at that time, or tomorrow if it has passed
    date only   -> that day at 10:00 and 18:00 (settings.reminder_day_times)
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from psycopg import Connection

from app.core.config import get_settings
from app.core.database import transaction
from app.core.dates import DEFAULT_TZ, short_date
from app.handlers.party import PARTY_CHOICE_HANDLERS, ask_choose_party
from app.schemas.khata import CancelReminderFields, PendingAction, SetReminderFields
from app.services.answers import pick
from app.services.registry import Context, Outcome, intent, pending_resolver
from app.services.replies import numbered, t
from app.tools import party as party_tools
from app.tools import reminders as tools

_FILLER_WORDS = {"wali", "wala", "wale", "reminder", "reminders", "the", "about", "cancel", "karo", "yaad"}


def _zone(ctx: Context) -> ZoneInfo:
    return ZoneInfo(ctx.business["timezone"] or DEFAULT_TZ)


def send_times(zone: ZoneInfo, day: date | None, at: time | None, now: datetime) -> list[datetime]:
    """When the reminder goes out. Times already in the past are dropped."""
    if day and at:
        times = [datetime.combine(day, at, zone)]
    elif at:
        first = datetime.combine(now.date(), at, zone)
        times = [first if first > now else first + timedelta(days=1)]
    else:
        day_times = [time.fromisoformat(x.strip()) for x in get_settings().reminder_day_times.split(",")]
        times = [datetime.combine(day, x, zone) for x in day_times]
    return [x for x in times if x > now]


def _when_text(language: str, times: list[datetime]) -> str:
    """29 Sep, 10:00 AM  /  30 Sep, 10:00 AM aur 06:00 PM"""
    clock = [f"{x:%I:%M %p}" for x in times]
    return f"{short_date(times[0].date())}, " + f" {t('word_and', language)} ".join(clock)


def _ask(ctx: Context, kind: str, draft: dict, question: str) -> Outcome:
    pending = PendingAction(kind=kind, language=ctx.language, expects="text", data={"draft": draft})
    return Outcome("set_reminder", question, pending=pending)


# ---------------------------------------------------------------------------
# Set
# ---------------------------------------------------------------------------


@intent(
    "set_reminder",
    "User ASKS to be reminded at a time or day (\"yaad dilana\", \"yaad krwana\", \"remind me\"), about anything. A"
    " note with no time is remember_*_fact. A remark (\"ali ne kaha kal dega\") is not a reminder.",
    fields=SetReminderFields,
    fields_hint=(
        '{"text": string | null (without the time words), '
        '"date": "YYYY-MM-DD" | null, "time": "HH:MM" (24h) | null, '
        '"party_name": string | null (a customer/supplier the reminder is about)}'
    ),
    examples=[
        "kal 10 baje yaad dilana Rohaan ko payment karni hai", "30 Sep ko yaad dilana Ali se paise lene hain",
        "remind me at 5 pm to call the supplier", "shaam ko yaad krwana dukaan band karni hai",
    ],
    needs_business=True,
)
def set_reminder(ctx: Context, fields: SetReminderFields) -> Outcome:
    draft = {
        "text": fields.text,
        "date": fields.date.isoformat() if fields.date else None,
        "time": fields.time.isoformat(timespec="minutes") if fields.time else None,
        "party_name": fields.party_name,
        "account_id": None,
        "party_checked": False,
    }
    return next_step(ctx, draft)


def next_step(ctx: Context, draft: dict) -> Outcome:
    language = ctx.language
    if not draft["text"]:
        return _ask(ctx, "reminder_what", draft, t("ask_reminder_what", language))
    if not draft["date"] and not draft["time"]:
        return _ask(ctx, "reminder_when", draft, t("ask_reminder_when", language))

    # Optional link to a party: its balance is added when the reminder is sent
    if draft["party_name"] and not draft["party_checked"]:
        draft["party_checked"] = True
        with transaction() as conn:
            matches = party_tools.find_parties(conn, ctx.business["id"], draft["party_name"])
        if len(matches) == 1:
            draft["account_id"] = str(matches[0]["id"])
        elif len(matches) > 1:
            return ask_choose_party(ctx, draft["party_name"], matches, "reminder", {"draft": draft})

    zone = _zone(ctx)
    day = date.fromisoformat(draft["date"]) if draft["date"] else None
    at = time.fromisoformat(draft["time"]) if draft["time"] else None
    times = send_times(zone, day, at, datetime.now(zone))
    if not times:
        return Outcome("set_reminder", t("past_time", language))
    return _save(ctx, draft, times, at)


def _save(ctx: Context, draft: dict, times: list[datetime], at: time | None) -> Outcome:
    reply = t("reminder_set", ctx.language, when=_when_text(ctx.language, times), text=draft["text"])

    def commit(conn: Connection) -> str:
        tools.create_reminder(
            conn,
            business_id=ctx.business["id"],
            user_id=ctx.user["id"],
            conversation_id=ctx.conversation["id"],
            language=ctx.language,
            text=draft["text"],
            account_id=draft["account_id"],
            remind_date=times[0].date(),
            remind_time=at,
            send_times=times,
            message_id=ctx.message_id,
        )
        return reply

    return Outcome("set_reminder", commit=commit)


@pending_resolver("reminder_what")
def resolve_reminder_what(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    draft = dict(pending.data["draft"])
    draft["text"] = answer.strip()
    return next_step(ctx, draft)


@pending_resolver("reminder_when")
def resolve_reminder_when(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    """The AI answers this question as "YYYY-MM-DD HH:MM", "YYYY-MM-DD" or "HH:MM"."""
    draft = dict(pending.data["draft"])
    value = answer.strip()
    try:
        if len(value) > 10:
            moment = datetime.fromisoformat(value)
            draft["date"], draft["time"] = moment.date().isoformat(), moment.time().isoformat(timespec="minutes")
        elif "-" in value:
            draft["date"] = date.fromisoformat(value).isoformat()
        else:
            draft["time"] = time.fromisoformat(value).isoformat(timespec="minutes")
    except ValueError:
        return Outcome("set_reminder", t("ask_reminder_when", ctx.language), pending=pending)
    return next_step(ctx, draft)


def _after_party_choice(ctx: Context, party: dict, data: dict) -> Outcome:
    draft = dict(data["draft"])
    draft["account_id"] = party["id"]
    return next_step(ctx, draft)


PARTY_CHOICE_HANDLERS["reminder"] = ("set_reminder", _after_party_choice)


# ---------------------------------------------------------------------------
# List + cancel
# ---------------------------------------------------------------------------


def _upcoming(ctx: Context, limit: int = 10) -> list[dict]:
    with transaction() as conn:
        return tools.list_upcoming(conn, ctx.business["id"], ctx.user["id"], limit)


def _label(ctx: Context, reminder: dict) -> str:
    moment = reminder["next_send"].astimezone(_zone(ctx))
    return f"{short_date(moment.date())}, {moment:%I:%M %p} — {reminder['text']}"


@intent(
    "list_reminders",
    "User asks which reminders are set / what the bot will remind them about.",
    examples=["meri reminders", "kya kya yaad dilana hai", "show my reminders"],
    needs_business=True,
)
def list_reminders(ctx: Context, _) -> Outcome:
    items = _upcoming(ctx)
    if not items:
        return Outcome("list_reminders", t("no_reminders", ctx.language))
    return Outcome("list_reminders", t("reminders_list", ctx.language, items=numbered([_label(ctx, r) for r in items])))


@intent(
    "cancel_reminder",
    "User wants to cancel / delete / stop a reminder.",
    fields=CancelReminderFields,
    fields_hint='{"query": string | null}  (words identifying the reminder, e.g. "Rohaan wali reminder cancel karo" -> "Rohaan")',
    examples=["Rohaan wali reminder cancel karo", "cancel the chai reminder", "reminder hatao"],
    needs_business=True,
)
def cancel_reminder(ctx: Context, fields: CancelReminderFields) -> Outcome:
    items = _upcoming(ctx, limit=50)
    if not items:
        return Outcome("cancel_reminder", t("no_reminders", ctx.language))
    words = [w for w in (fields.query or "").lower().split() if len(w) > 2 and w not in _FILLER_WORDS]
    if words:
        items = [r for r in items if any(w in r["text"].lower() for w in words)]
        if not items:
            return Outcome("cancel_reminder", t("reminder_not_found", ctx.language))
    if len(items) == 1:
        return _cancel(ctx, items[0])
    options = [{"id": str(r["id"]), "text": r["text"], "label": _label(ctx, r)} for r in items[:10]]
    pending = PendingAction(kind="choose_reminder", language=ctx.language, expects="choice", data={"options": options})
    return Outcome(
        "cancel_reminder",
        t("choose_reminder", ctx.language, options=numbered([o["label"] for o in options])),
        pending=pending,
    )


def _cancel(ctx: Context, reminder: dict) -> Outcome:
    def commit(conn: Connection) -> str:
        if not tools.cancel_reminder(conn, ctx.business["id"], ctx.user["id"], reminder["id"]):
            return t("reminder_not_found", ctx.language)
        return t("reminder_cancelled", ctx.language, text=reminder["text"])

    return Outcome("cancel_reminder", commit=commit)


@pending_resolver("choose_reminder")
def resolve_choose_reminder(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    options = pending.data["options"]
    chosen = pick(answer, options, lambda o: o["text"])
    if chosen:
        return _cancel(ctx, chosen)
    return Outcome(
        "cancel_reminder",
        t("invalid_choice", ctx.language, n=len(options), options=numbered([o["label"] for o in options])),
        pending=pending,
    )
