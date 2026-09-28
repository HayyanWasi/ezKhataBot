"""Intent and pending-question registries.

Features plug into the pipeline by registering intents here; the pipeline
itself never changes.

    @intent("check_balance", "User asks how much a party owes", fields=BalanceFields, ...)
    def check_balance(ctx, fields) -> Outcome: ...
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from psycopg import Connection
from pydantic import BaseModel

from app.schemas.khata import PendingAction


@dataclass
class Context:
    user: dict
    conversation: dict
    business: dict | None  # active business, None if not chosen yet
    businesses: list[dict]  # all businesses the user can access
    language: str  # reply language
    text: str  # the user's message
    message_id: UUID | None = None  # the user message being handled (source of money entries)

    def business_by_id(self, business_id: str | UUID) -> dict | None:
        return next((b for b in self.businesses if str(b["id"]) == str(business_id)), None)


@dataclass
class Outcome:
    """What a handler decided. Nothing is written until the pipeline's commit phase.

    reply:   the reply text (or the question, when `pending` is set)
    commit:  DB writes to run inside the commit transaction; returns the final reply.
             Handlers must only write through the connection they are given.
    pending: a new question to wait on. Every processed message clears the old one.
    """

    intent: str
    reply: str = ""
    commit: Callable[[Connection], str] | None = None
    pending: PendingAction | None = None
    active_business_id: UUID | None = None
    replay_text: str | None = None  # re-run this message after the outcome (used after choosing a shop)
    attachment: str | None = None  # file sent with the reply (PDF statement)


Handler = Callable[[Context, BaseModel | None], Outcome]
Resolver = Callable[[Context, PendingAction, str], Outcome]


@dataclass
class IntentSpec:
    name: str
    description: str
    handler: Handler
    fields: type[BaseModel] | None = None
    fields_hint: str = ""  # JSON shape shown to the AI
    examples: list[str] = field(default_factory=list)
    needs_business: bool = False
    owner_only: bool = False  # employees can only view (checked in code, not by the AI)


INTENTS: dict[str, IntentSpec] = {}
PENDING_RESOLVERS: dict[str, Resolver] = {}


def intent(
    name: str,
    description: str,
    *,
    fields: type[BaseModel] | None = None,
    fields_hint: str = "",
    examples: list[str] | tuple[str, ...] = (),
    needs_business: bool = False,
    owner_only: bool = False,
) -> Callable[[Handler], Handler]:
    def register(handler: Handler) -> Handler:
        INTENTS[name] = IntentSpec(
            name, description, handler, fields, fields_hint, list(examples), needs_business, owner_only
        )
        return handler

    return register


def pending_resolver(kind: str) -> Callable[[Resolver], Resolver]:
    def register(resolver: Resolver) -> Resolver:
        PENDING_RESOLVERS[kind] = resolver
        return resolver

    return register
