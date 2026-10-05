r"""The EzKhata agent, built as a LangGraph graph.

It decides WHAT to do with one message and returns an Outcome.
It never writes to the database: the pipeline (app/services/handler.py)
commits the Outcome in one transaction afterwards.

    START -> check_rules --(done)-----------------------------------> finish -> END
                  |  |  \--(pending answer)--> resolve_pending --(done)--^
                  |  |                              \--(replay)--> replay --> check_rules
                  |  \--(no shop)--> ask_business ---------------------> finish
                  \--(needs AI)--> classify --(pending answer)--> resolve_pending
                                      |--(new request)--> run_intent --> finish
                                      |--(no shop)------> ask_business
                                      \--(AI failed)----> finish
"""

import logging
import re
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

import app.handlers.foundation  # noqa: F401, I001  registers foundation intents (listed first to the AI)
import app.handlers.party  # noqa: F401  registers party khata intents
import app.handlers.cash  # noqa: F401  registers cash book intents
import app.handlers.stock  # noqa: F401  registers stock book intents
import app.handlers.bills  # noqa: F401  registers bill intents
import app.handlers.entries  # noqa: F401  registers undo / delete / edit / photo intents
import app.handlers.reminders  # noqa: F401  registers reminder intents
import app.handlers.statements  # noqa: F401  registers the statement intent
import app.handlers.employees  # noqa: F401  registers the employee intents
from app.ai.classifier import AIError, classify
from app.core.dates import now
from app.core.database import transaction
from app.db import crud
from app.handlers.foundation import ask_choose_business, help_
from app.handlers.images import name_fixes, read_image
from app.handlers.stock import stock_photo
from app.schemas.khata import ClassifierOutput, PendingAction, PendingAnswerFields
from app.services.amounts import format_rs, parse_amounts
from app.services.answers import is_cancel, is_thanks, is_trivial_answer
from app.services.registry import INTENTS, PENDING_RESOLVERS, Context, Outcome, chain
from app.services.replies import t

log = logging.getLogger("ezkhata.agent")


class AgentState(TypedDict, total=False):
    ctx: Context  # who, which shop, message text, reply language
    pending: PendingAction | None  # question the bot is waiting on
    history: list[dict]  # last few messages, for the AI
    preference: str | None  # saved language preference (None = mirror the user)
    answer: str | None  # the user's answer to the pending question
    classification: ClassifierOutput  # what the AI understood
    outcome: Outcome | None  # the decision
    first_outcome: Outcome | None  # set when a message is replayed (e.g. after choosing a shop)
    queued: bool  # a queued action from an earlier message (no AI call)


# ---------------------------------------------------------------------------
# Nodes: each one reads the state and returns the fields it changes
# ---------------------------------------------------------------------------


def check_rules(state: AgentState) -> AgentState:
    """Handle what needs no AI: commands, number/yes-no answers, missing shop."""
    ctx, pending = state["ctx"], state.get("pending")
    command = ctx.text.lower()

    if command == "/cancel":
        return {"outcome": Outcome("cancel", t("cancelled" if pending else "nothing_to_cancel", ctx.language))}
    if command == "/help":
        return {"outcome": help_(ctx, None)}
    if ctx.image_path:  # a photo: read it (OCR), no classifier call
        if ctx.business is None:
            return {}  # after_rules asks which shop; the photo is kept for the replay
        item_photo = stock_photo(ctx)  # an item's barcode / picture (a barcode lookup is open to staff)
        if item_photo:
            return {"outcome": item_photo}
        if ctx.business["role"] != "owner":  # photos write money
            return {"outcome": Outcome("read_image", t("owner_only", ctx.language))}
        return {"outcome": read_image(ctx)}
    if is_thanks(ctx.text):  # "shukriya bhai": a friendly word; a waiting question keeps waiting
        return {"outcome": _keep_waiting(ctx, pending, t("thanks_reply", ctx.language), "greeting")}
    # "rehne do" / "cancel karo": stop, never a new request. A yes/no question takes it as "nahi", and
    # where a skip is allowed (opening cash, shop details) it is a skip.
    if is_cancel(ctx.text) and not (pending and pending.expects in ("yes_no", "amount_or_skip", "free_text")):
        return {"outcome": Outcome("cancel", t("cancelled" if pending else "okay", ctx.language))}
    if pending and is_trivial_answer(ctx.text, pending.expects):
        return {"answer": ctx.text}
    if pending and pending.kind == "confirm_image" and _corrects_preview(ctx.text, pending):
        return {"answer": ctx.text}  # "han kardo, urqan nhi hai furqan hai": a name fix to the list just shown
    return {}


def classify_message(state: AgentState) -> AgentState:
    """One LLM call: intent + fields + language."""
    ctx, pending = state["ctx"], state.get("pending")

    def call_ai(pending_question: str | None):
        return classify(
            ctx.text,
            intents=INTENTS,
            history=state.get("history", []),
            pending_question=pending_question,
            memories=_memory_texts(ctx),
            now=now(ctx.business["timezone"] if ctx.business else None),
        )

    try:
        result = call_ai(ctx.conversation["pending_question"] if pending else None)
        # Money guard: an amount question is answered only by a plain amount ("500", "Rs 500"),
        # which check_rules already handles. Anything else (e.g. "Bilal ko 300 diye") is a new
        # request, so it is classified again without the question.
        if pending and pending.expects in ("amount", "amount_or_skip") and result.answers_pending:
            result = call_ai(None)
    except AIError:  # the AI service is busy or down: the user's wording was not the problem
        return {"outcome": _keep_waiting(ctx, pending, t("ai_busy", ctx.language))}

    # The AI's language guess is used unless a language is saved, or the message is one
    # word ("undo", "ok"), which is too short to tell
    if not state.get("preference") and len(ctx.text.split()) > 1:
        ctx = replace(ctx, language=result.language)

    if pending and result.answers_pending:
        answer = PendingAnswerFields.model_validate(result.fields).answer or ctx.text
        return {"ctx": ctx, "answer": answer}
    return {"ctx": ctx, "classification": result}


def resolve_pending(state: AgentState) -> AgentState:
    """The user answered the pending question: let its resolver decide."""
    ctx, pending = state["ctx"], state["pending"]
    resolver = PENDING_RESOLVERS.get(pending.kind)
    if resolver is None:
        log.warning("no resolver for pending kind %s", pending.kind)
        return {"outcome": INTENTS["unknown"].handler(ctx, None)}
    outcome = resolver(ctx, pending, state["answer"])
    outcome.continued = True  # the same flow goes on: the message's queued actions wait for it
    return {"outcome": outcome}


# Words that mean a day or time is written; without one, an entry is for today
_DATE_HINT = re.compile(
    r"\b(kal|kl|parso|parson|parsun|aaj|aj|today|yesterday|tomorrow|tareekh|tarikh|tarik|date|"
    r"jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*|"
    r"pichl\w*|pichh\w*|guzr\w*|last|pehle|hafte|week|mahine|month|din|raat|subah|shaam|dopahar|"
    r"baje|baad|minute|ghant\w*|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"somwar|peer|mangal|budh|jumerat|jumma|hafta|itwar|\d{1,2}(st|nd|rd|th))\b"
    r"|\d{1,2}\s*[/.-]\s*\d{1,2}|کل|آج|پرسوں|تاریخ",
    re.IGNORECASE,
)


def run_intent(state: AgentState) -> AgentState:
    """A new request: validate the AI's fields and run the intent's handler."""
    ctx, result, pending = state["ctx"], state["classification"], state.get("pending")
    spec = INTENTS.get(result.intent) or INTENTS["unknown"]
    if spec.name == "unknown" and pending:  # "han" to a 1/2 question: ask the same question again
        return {"outcome": _keep_waiting(ctx, pending, t("ask_again", ctx.language))}
    raw = dict(result.fields)
    if raw.get("date") and not _DATE_HINT.search(ctx.text):
        raw["date"] = None  # "Sameer ne 4 topi li": no day is written, so the AI's "4 Oct" is a guess
    if "reminder" not in spec.name and _KAL.search(ctx.text):
        _kal_is_yesterday(raw, now(ctx.business["timezone"] if ctx.business else None).date())
    try:
        fields = spec.fields.model_validate(raw) if spec.fields else None
    except ValidationError as e:
        log.warning("invalid fields for %s: %s", spec.name, e)
        return {"outcome": INTENTS["unknown"].handler(ctx, None)}
    if spec.needs_business and ctx.business is None:
        return {"outcome": Outcome(spec.name, t("no_business", ctx.language))}
    if spec.owner_only and (ctx.business is None or ctx.business["role"] != "owner"):
        return {"outcome": Outcome(spec.name, t("owner_only", ctx.language))}
    outcome = spec.handler(ctx, fields)
    outcome.then = [a.model_dump() for a in result.then]  # done one by one after this one is saved
    if not state.get("queued"):
        missed = unused_amounts(ctx.text, result)
        if missed:  # "Ali ko 300 diye aur ..." where a part was not understood: say so, never drop it silently
            amounts = ", ".join(format_rs(a) for a in missed)
            outcome = with_note(outcome, t("part_not_done", ctx.language, amounts=amounts))
    return {"outcome": outcome}


_KAL = re.compile(r"\b(kal|kl|kall)\b|کل", re.IGNORECASE)


def _kal_is_yesterday(raw: dict, today: date) -> None:
    """"Tariq ko kal 500 diye", "kal ki sale": for entries and reports "kal" is yesterday. A date the AI
    set to tomorrow is moved to yesterday (only reminders look ahead)."""
    tomorrow = today + timedelta(days=1)
    for key in ("date", "start_date", "end_date"):
        if str(raw.get(key) or "") == tomorrow.isoformat():
            raw[key] = (today - timedelta(days=1)).isoformat()


def _corrects_preview(text: str, pending: PendingAction) -> bool:
    return bool(name_fixes(text, [i.get("name") for i in pending.data.get("items", [])]))


def _keep_waiting(ctx: Context, pending: PendingAction | None, reply: str, intent: str = "unknown") -> Outcome:
    """Reply, and keep the question the bot is waiting on (asked again under the reply)."""
    if pending is None:
        return Outcome(intent, reply)
    question = ctx.conversation.get("pending_question") or ""
    return Outcome(intent, f"{reply}\n\n{question}".strip(), pending=pending, question=question or None)


# A second request in the same message: "aur", "and", "phir", a comma ...
_JOINER = re.compile(r"\b(aur|or|and|phir|fir|then|sath|saath|bhi|plus)\b|[,;\n]", re.IGNORECASE)
# Numbers that are not money: times, days, dates ("5 baje", "2 din", "15 tareekh", "5/10")
_NOT_MONEY = re.compile(
    r"\d+\s*(baje|bje|minute|mint|min|ghant\w*|din|hafte|mahine|tareekh|tarikh|tarik|st|nd|rd|th|am|pm|%)\b"
    r"|\d{1,2}\s*[:/]\s*\d{1,2}",
    re.IGNORECASE,
)


def _numbers(value: object) -> set[Decimal]:
    """Every number in the AI's fields (amounts, quantities, prices, dates)."""
    if isinstance(value, dict):
        return set().union(*(_numbers(v) for v in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_numbers(v) for v in value)) if value else set()
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, (int, float, Decimal)):
        return {Decimal(str(value))}
    return set(parse_amounts(str(value))) | {Decimal(d) for d in re.findall(r"\d+", str(value))}


def unused_amounts(text: str, result: ClassifierOutput) -> list[Decimal]:
    """Amounts written in a message with two or more parts that no action uses. Quantity x price and
    the sum of the numbers count as used ("2 charger 3000 ke" may be stored as 2 x 1500)."""
    # many_entries has no fields: its rows are read in a second step, which shows every amount it found
    if result.intent in ("unknown", "many_entries") or not _JOINER.search(text):
        return []
    used = _numbers([result.fields] + [a.fields for a in result.then])
    small = [n for n in used if n < 100_000]
    used |= {a * b for a in small for b in small} | {sum(used, Decimal(0))}
    written = parse_amounts(_NOT_MONEY.sub(" ", text))
    return [a for a in dict.fromkeys(written) if a not in used]


def with_note(outcome: Outcome, note: str) -> Outcome:
    """The outcome with a line added under its reply."""
    if outcome.commit:
        commit = outcome.commit
        outcome.commit = lambda conn: commit(conn) + "\n\n" + note
    else:
        outcome.reply = f"{outcome.reply}\n\n{note}" if outcome.reply else note
    return outcome


def ask_business(state: AgentState) -> AgentState:
    """User has several shops and none is selected: ask, and remember the message."""
    ctx = state["ctx"]
    return {"outcome": ask_choose_business(ctx, replay_text=ctx.text)}


def replay(state: AgentState) -> AgentState:
    """A shop was chosen: now handle the message that triggered the question."""
    ctx, outcome = state["ctx"], state["outcome"]
    ctx = replace(ctx, business=ctx.business_by_id(outcome.active_business_id), text=outcome.replay_text)
    return {"ctx": ctx, "pending": None, "answer": None, "outcome": None, "first_outcome": outcome}


def finish(state: AgentState) -> AgentState:
    """Join a replayed message's outcome with the shop-switch outcome."""
    first = state.get("first_outcome")
    if first is None:
        return {}
    return {"outcome": chain(first, state["outcome"])}


# ---------------------------------------------------------------------------
# Routing: which node runs next
# ---------------------------------------------------------------------------


def _needs_shop(state: AgentState) -> bool:
    pending = state.get("pending")
    choosing = pending is not None and pending.kind == "choose_business"
    return state["ctx"].business is None and not choosing


def after_rules(state: AgentState) -> str:
    if state.get("outcome"):
        return "finish"
    if state.get("answer"):
        return "resolve_pending"
    if _needs_shop(state):
        return "ask_business"
    return "classify"


def after_classify(state: AgentState) -> str:
    if state.get("outcome"):
        return "finish"
    if state.get("answer"):
        return "resolve_pending"
    if state["ctx"].business is None:  # was asked to choose a shop but sent a new request
        return "ask_business"
    return "run_intent"


def after_resolve(state: AgentState) -> str:
    return "replay" if state["outcome"].replay_text else "finish"


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node("check_rules", check_rules)
    graph.add_node("classify", classify_message)
    graph.add_node("resolve_pending", resolve_pending)
    graph.add_node("run_intent", run_intent)
    graph.add_node("ask_business", ask_business)
    graph.add_node("replay", replay)
    graph.add_node("finish", finish)

    graph.add_edge(START, "check_rules")
    graph.add_conditional_edges("check_rules", after_rules, ["finish", "resolve_pending", "ask_business", "classify"])
    graph.add_conditional_edges("classify", after_classify, ["finish", "resolve_pending", "ask_business", "run_intent"])
    graph.add_conditional_edges("resolve_pending", after_resolve, ["replay", "finish"])
    graph.add_edge("replay", "check_rules")
    graph.add_edge("run_intent", "finish")
    graph.add_edge("ask_business", "finish")
    graph.add_edge("finish", END)

    return graph.compile()


agent = build_agent()


def decide(
    ctx: Context,
    pending: PendingAction | None,
    history: list[dict],
    preference: str | None,
    action: dict | None = None,
) -> Outcome:
    """Run the agent for one message and return its decision.
    action: a queued action from an earlier message ({"intent", "fields"}), run without the AI."""
    if action is not None:
        if ctx.business is None:
            return ask_choose_business(ctx, replay_text=ctx.text)
        classification = ClassifierOutput(intent=action["intent"], language=ctx.language, fields=action["fields"])
        return run_intent({"ctx": ctx, "classification": classification, "queued": True})["outcome"]
    state = agent.invoke(
        {"ctx": ctx, "pending": pending, "history": history, "preference": preference},
        # Shown in LangSmith: filter traces by user, shop or channel
        config={
            "run_name": "ezkhata_agent",
            "tags": [ctx.conversation["channel"]],
            "metadata": {
                "user_id": str(ctx.user["id"]),
                "business_id": str(ctx.business["id"]) if ctx.business else None,
                "conversation_id": str(ctx.conversation["id"]),
                "has_pending": pending is not None,
            },
        },
    )
    return state["outcome"]


def _memory_texts(ctx: Context) -> list[str]:
    with transaction() as conn:
        items = [m["content"] for m in crud.list_user_memories(conn, ctx.user["id"])]
        if ctx.business:
            items += [m["content"] for m in crud.list_business_memories(conn, ctx.business["id"])]
    return items
