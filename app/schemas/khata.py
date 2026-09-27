"""Structured data passed between the AI classifier and the handlers."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Language = Literal["en", "ur", "roman_ur"]


class ClassifierOutput(BaseModel):
    """What the LLM returns for one user message."""

    intent: str
    language: Language = "roman_ur"
    answers_pending: bool = False
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fields", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return v or {}


class PendingAction(BaseModel):
    """The one question the bot is waiting on (stored in conversations.pending_action)."""

    kind: str  # name of the pending resolver that handles the answer
    language: Language
    expects: Literal["choice", "yes_no", "text"] = "text"
    data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Per-intent fields (validated after the AI call)
# ---------------------------------------------------------------------------


class _Fields(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class PendingAnswerFields(_Fields):
    answer: str | None = None


class SwitchBusinessFields(_Fields):
    business_name: str | None = None


class SetLanguageFields(_Fields):
    language: Literal["en", "ur", "roman_ur", "auto"]


class RememberFields(_Fields):
    content: str = Field(min_length=1)


class ForgetMemoryFields(_Fields):
    query: str | None = None
