"""Structured data passed between the AI classifier and the handlers."""

import datetime as dt
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
    expects: Literal["choice", "yes_no", "amount", "text"] = "text"
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


# ---------------------------------------------------------------------------
# Party khata fields. Amounts stay raw here: the code checks them against the
# user's own text (app/services/amounts.py) before anything is saved.
# ---------------------------------------------------------------------------

PartyType = Literal["customer", "supplier"]


class PartyEntryFields(_Fields):
    party_name: str | None = None
    party_type: PartyType | None = None
    direction: Literal["gave", "got"] | None = None
    amount: Any = None
    date: dt.date | None = None
    note: str | None = None


class AddPartyFields(_Fields):
    name: str = Field(min_length=1)
    type: PartyType | None = None
    phone: str | None = None
    opening_amount: Any = None
    opening_direction: Literal["will_get", "will_give"] | None = None


class SetPartyPhoneFields(_Fields):
    party_name: str = Field(min_length=1)
    phone: str = Field(min_length=1)


class PartyBalanceFields(_Fields):
    party_name: str | None = None


class ListPartiesFields(_Fields):
    type: PartyType | None = None


class DeleteEntryFields(_Fields):
    party_name: str | None = None
    amount: Any = None


# ---------------------------------------------------------------------------
# Statements + reminders
# ---------------------------------------------------------------------------


class StatementFields(_Fields):
    party_name: str | None = None  # None = all parties
    start_date: dt.date | None = None  # None = full khata
    end_date: dt.date | None = None


class SetReminderFields(_Fields):
    text: str | None = None
    date: dt.date | None = None
    time: dt.time | None = None
    party_name: str | None = None


class CancelReminderFields(_Fields):
    query: str | None = None


# ---------------------------------------------------------------------------
# Image entries (OCR text -> rows). Amounts stay raw: code checks each one
# against the OCR text before anything is saved.
# ---------------------------------------------------------------------------

RowCategory = Literal["party_entry", "expense", "cash_in", "cash_out", "bank", "sale", "other"]


class ExtractedRow(_Fields):
    category: RowCategory = "other"
    party_name: str | None = None
    direction: Literal["gave", "got"] | None = None
    amount: Any = None
    date: dt.date | None = None
    note: str | None = None

    @field_validator("category", mode="before")
    @classmethod
    def _unknown_category(cls, v: Any) -> Any:
        allowed = {"party_entry", "expense", "cash_in", "cash_out", "bank", "sale", "other"}
        return v if v in allowed else "other"

    @field_validator("direction", mode="before")
    @classmethod
    def _unknown_direction(cls, v: Any) -> Any:
        return v if v in ("gave", "got") else None

    @field_validator("date", mode="before")
    @classmethod
    def _bad_date(cls, v: Any) -> Any:
        """An unreadable date becomes None (the row then uses today and shows it)."""
        if isinstance(v, str):
            try:
                return dt.date.fromisoformat(v.strip())
            except ValueError:
                return None
        return v


class ImageExtraction(BaseModel):
    kind: Literal["register", "bill", "payment", "other"] = "other"
    written_total: Any = None  # a total written on the sheet, if any (checked against the rows)
    rows: list[ExtractedRow] = Field(default_factory=list)

    @field_validator("kind", mode="before")
    @classmethod
    def _unknown_kind(cls, v: Any) -> Any:
        return v if v in ("register", "bill", "payment", "other") else "other"

    @field_validator("rows", mode="before")
    @classmethod
    def _none_rows(cls, v: Any) -> Any:
        return v or []
