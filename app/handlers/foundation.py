"""Foundation intents: greeting, help, shops, language, memories."""

from psycopg import Connection

from app.core.database import transaction
from app.db import crud
from app.schemas.khata import (
    ForgetMemoryFields,
    PendingAction,
    RememberFields,
    SetLanguageFields,
    SwitchBusinessFields,
)
from app.services.answers import pick
from app.services.registry import Context, Outcome, intent, pending_resolver
from app.services.replies import numbered, t

# ---------------------------------------------------------------------------
# Greeting, help, unknown
# ---------------------------------------------------------------------------


@intent(
    "greeting",
    "User says hello / salam or chats: how is the bot, who is it, what is it doing (any spelling or tone).",
    examples=["salam", "assalam o alaikum", "kia krra", "abe tu kya kr raha hai", "tm kon ho", "السلام علیکم"],
)
def greeting(ctx: Context, _) -> Outcome:
    business = ctx.business["name"] if ctx.business else "—"
    return Outcome("greeting", t("greeting", ctx.language, name=ctx.user["name"], business=business))


@intent(
    "help",
    "User asks what the bot can do or how to use it, or complains about the bot.",
    examples=["help", "madad chahiye", "tum kya kar sakte ho", "bekar bot hai", "مدد"],
)
def help_(ctx: Context, _) -> Outcome:
    return Outcome("help", t("help", ctx.language))


@intent("unknown", "Anything that does not match another intent.")
def unknown(ctx: Context, _) -> Outcome:
    return Outcome("unknown", t("not_understood", ctx.language))


# ---------------------------------------------------------------------------
# Shops
# ---------------------------------------------------------------------------


@intent(
    "which_business",
    "User asks which shop is currently selected, or asks for their list of shops.",
    examples=["kaun si dukaan hai", "which shop am I in", "meri dukaanein dikhao"],
)
def which_business(ctx: Context, _) -> Outcome:
    reply = t("current_business", ctx.language, business=ctx.business["name"]) if ctx.business else ""
    if len(ctx.businesses) > 1:
        names = [b["name"] + (" ✅" if ctx.business and b["id"] == ctx.business["id"] else "") for b in ctx.businesses]
        listing = t("your_businesses", ctx.language, options=numbered(names))
        reply = f"{reply}\n\n{listing}" if reply else listing
    return Outcome("which_business", reply or t("no_business", ctx.language))


@intent(
    "switch_business",
    "User wants to change the active shop, optionally naming it.",
    fields=SwitchBusinessFields,
    fields_hint='{"business_name": string | null}',
    examples=["dukaan badlo", "switch to Ali Store", "Hayyan Store pe jao"],
)
def switch_business(ctx: Context, fields: SwitchBusinessFields) -> Outcome:
    if len(ctx.businesses) == 1:
        return Outcome(
            "switch_business", t("only_one_business", ctx.language, business=ctx.businesses[0]["name"])
        )
    if fields.business_name:
        chosen = pick(fields.business_name, ctx.businesses, lambda b: b["name"])
        if chosen:
            return business_switched(ctx, chosen)
    return ask_choose_business(ctx)


def ask_choose_business(ctx: Context, replay_text: str | None = None) -> Outcome:
    """Ask which shop to use. `replay_text` is processed again once the user picks one."""
    options = ctx.businesses
    pending = PendingAction(
        kind="choose_business",
        language=ctx.language,
        expects="choice",
        data={"options": [str(b["id"]) for b in options], "replay_text": replay_text},
    )
    question = t("choose_business", ctx.language, options=numbered([b["name"] for b in options]))
    return Outcome("choose_business", question, pending=pending)


def business_switched(ctx: Context, business: dict, replay_text: str | None = None) -> Outcome:
    return Outcome(
        "switch_business",
        t("business_switched", ctx.language, business=business["name"]),
        active_business_id=business["id"],
        replay_text=replay_text,
    )


@pending_resolver("choose_business")
def resolve_choose_business(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    options = [b for b in (ctx.business_by_id(i) for i in pending.data["options"]) if b]
    chosen = pick(answer, options, lambda b: b["name"])
    if chosen:
        return business_switched(ctx, chosen, pending.data.get("replay_text"))
    names = numbered([b["name"] for b in options])
    return Outcome(
        "choose_business",
        t("invalid_choice", ctx.language, n=len(options), options=names),
        pending=pending,
    )


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------


@intent(
    "set_language",
    "User asks the bot to reply in a specific language (en, ur, roman_ur), "
    "or to go back to replying in whatever language they write (auto).",
    fields=SetLanguageFields,
    fields_hint='{"language": "en" | "ur" | "roman_ur" | "auto"}',
    examples=["mujhse English mein baat karo", "urdu mein likho", "roman urdu mein jawab do", "talk in any language"],
)
def set_language(ctx: Context, fields: SetLanguageFields) -> Outcome:
    language = None if fields.language == "auto" else fields.language
    reply = t("language_auto", ctx.language) if language is None else t("language_set", language)

    def commit(conn: Connection) -> str:
        crud.set_language_preference(conn, ctx.user["id"], language)
        return reply

    return Outcome("set_language", commit=commit)


# ---------------------------------------------------------------------------
# Memories (saved only when the user explicitly asks)
# ---------------------------------------------------------------------------

REMEMBER_HINT = (
    '{"content": string}  (only the fact itself in the user\'s language, without words like '
    '"yaad rakhna" / "remember"; e.g. "yaad rakhna Ali Rohaan ka bhai hai" -> "Ali Rohaan ka bhai hai")'
)


@intent(
    "remember_user_fact",
    "User asks to remember a note about THEMSELVES (how to address them, own habits). About other people or "
    "the shop: remember_business_fact. Reminding at a time (\"yaad dilana\"): set_reminder.",
    fields=RememberFields,
    fields_hint=REMEMBER_HINT,
    examples=["mujhe Hayyan bhai kehna", "call me boss", "yaad rakhna main subah 9 baje aata hoon"],
)
def remember_user_fact(ctx: Context, fields: RememberFields) -> Outcome:
    def commit(conn: Connection) -> str:
        crud.add_user_memory(conn, ctx.user["id"], fields.content)
        return t("remembered", ctx.language)

    return Outcome("remember_user_fact", commit=commit)


@intent(
    "remember_business_fact",
    "User asks to remember a non-money note about the SHOP or OTHER people (customers, relations, timings), "
    "with no reminding time.",
    fields=RememberFields,
    fields_hint=REMEMBER_HINT,
    examples=["yaad rakhna Ali Rohaan ka bhai hai", "remember the shop is closed on Friday"],
    needs_business=True,
)
def remember_business_fact(ctx: Context, fields: RememberFields) -> Outcome:
    def commit(conn: Connection) -> str:
        crud.add_business_memory(conn, ctx.business["id"], ctx.user["id"], fields.content)
        return t("remembered", ctx.language)

    return Outcome("remember_business_fact", commit=commit)


_FILLER_WORDS = {
    "wali", "wala", "wale", "baat", "baaten", "note", "notes", "that", "the", "about", "waali", "cheez",
}


def _load_memories(ctx: Context) -> list[dict]:
    """User + active-business memories as [{kind, id, content}], oldest first."""
    with transaction() as conn:
        items = [
            {"kind": "user", "id": str(m["id"]), "content": m["content"]}
            for m in crud.list_user_memories(conn, ctx.user["id"])
        ]
        if ctx.business:
            items += [
                {"kind": "business", "id": str(m["id"]), "content": m["content"]}
                for m in crud.list_business_memories(conn, ctx.business["id"])
            ]
    return items


@intent(
    "list_memories",
    "User asks what the bot remembers / has saved.",
    examples=["kya kya yaad hai tmhe", "what do you remember", "mere notes dikhao"],
)
def list_memories(ctx: Context, _) -> Outcome:
    items = _load_memories(ctx)
    if not items:
        return Outcome("list_memories", t("no_memories", ctx.language))
    return Outcome("list_memories", t("memories", ctx.language, items=numbered([m["content"] for m in items])))


@intent(
    "forget_memory",
    "User asks the bot to forget / delete something it remembered.",
    fields=ForgetMemoryFields,
    fields_hint='{"query": string | null}  (key names/words identifying the note, e.g. "Ali wali baat bhool jao" -> "Ali")',
    examples=["Ali wali baat bhool jao", "forget that the shop is closed on Friday", "ek note delete karo"],
)
def forget_memory(ctx: Context, fields: ForgetMemoryFields) -> Outcome:
    items = _load_memories(ctx)
    if not items:
        return Outcome("forget_memory", t("no_memories", ctx.language))
    words = [w for w in (fields.query or "").lower().split() if len(w) > 2 and w not in _FILLER_WORDS]
    if words:
        matches = [m for m in items if any(w in m["content"].lower() for w in words)]
        if not matches:
            return Outcome("forget_memory", t("memory_not_found", ctx.language))
        if len(matches) == 1:
            return _forget(ctx, matches[0])
        items = matches
    pending = PendingAction(kind="choose_memory", language=ctx.language, expects="choice", data={"options": items})
    return Outcome(
        "forget_memory",
        t("choose_memory", ctx.language, options=numbered([m["content"] for m in items])),
        pending=pending,
    )


def _forget(ctx: Context, memory: dict) -> Outcome:
    def commit(conn: Connection) -> str:
        if memory["kind"] == "user":
            crud.delete_user_memory(conn, memory["id"], ctx.user["id"])
        else:
            crud.delete_business_memory(conn, memory["id"], ctx.business["id"])
        return t("forgotten", ctx.language, item=memory["content"])

    return Outcome("forget_memory", commit=commit)


@pending_resolver("choose_memory")
def resolve_choose_memory(ctx: Context, pending: PendingAction, answer: str) -> Outcome:
    options = pending.data["options"]
    chosen = pick(answer, options, lambda m: m["content"])
    if chosen:
        return _forget(ctx, chosen)
    return Outcome(
        "forget_memory",
        t("invalid_choice", ctx.language, n=len(options), options=numbered([m["content"] for m in options])),
        pending=pending,
    )
