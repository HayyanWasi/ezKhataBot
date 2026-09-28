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
from dataclasses import replace
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

import app.handlers.foundation  # noqa: F401, I001  registers foundation intents (listed first to the AI)
import app.handlers.party  # noqa: F401  registers party khata intents
import app.handlers.cash  # noqa: F401  registers cash book intents
import app.handlers.stock  # noqa: F401  registers stock book intents
import app.handlers.entries  # noqa: F401  registers undo / delete / edit / photo intents
import app.handlers.reminders  # noqa: F401  registers reminder intents
import app.handlers.statements  # noqa: F401  registers the statement intent
from app.ai.classifier import AIError, classify
from app.core.dates import now
from app.core.database import transaction
from app.db import crud
from app.handlers.foundation import ask_choose_business, help_
from app.handlers.images import read_image
from app.handlers.stock import stock_photo
from app.schemas.khata import ClassifierOutput, PendingAction, PendingAnswerFields
from app.services.answers import is_trivial_answer
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
    if pending and is_trivial_answer(ctx.text, pending.expects):
        return {"answer": ctx.text}
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
    except AIError:
        return {"outcome": Outcome("unknown", t("not_understood", ctx.language))}

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
    return {"outcome": resolver(ctx, pending, state["answer"])}


def run_intent(state: AgentState) -> AgentState:
    """A new request: validate the AI's fields and run the intent's handler."""
    ctx, result = state["ctx"], state["classification"]
    spec = INTENTS.get(result.intent) or INTENTS["unknown"]
    try:
        fields = spec.fields.model_validate(result.fields) if spec.fields else None
    except ValidationError as e:
        log.warning("invalid fields for %s: %s", spec.name, e)
        return {"outcome": INTENTS["unknown"].handler(ctx, None)}
    if spec.needs_business and ctx.business is None:
        return {"outcome": Outcome(spec.name, t("no_business", ctx.language))}
    if spec.owner_only and (ctx.business is None or ctx.business["role"] != "owner"):
        return {"outcome": Outcome(spec.name, t("owner_only", ctx.language))}
    return {"outcome": spec.handler(ctx, fields)}


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


def decide(ctx: Context, pending: PendingAction | None, history: list[dict], preference: str | None) -> Outcome:
    """Run the agent for one message and return its decision."""
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
