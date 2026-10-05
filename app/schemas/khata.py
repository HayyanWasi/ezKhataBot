"""Structured data passed between the AI classifier and the handlers."""

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Language = Literal["en", "ur", "roman_ur"]


class NextAction(BaseModel):
    """One more thing the same message asks for, done after the first one is saved."""

    intent: str
    fields: dict[str, Any] = Field(default_factory=dict)

    @field_validator("fields", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return v or {}


class ClassifierOutput(BaseModel):
    """What the LLM returns for one user message."""

    intent: str
    language: Language = "roman_ur"
    answers_pending: bool = False
    fields: dict[str, Any] = Field(default_factory=dict)
    then: list[NextAction] = Field(default_factory=list)  # more actions in the same message, in order

    @field_validator("fields", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return v or {}

    @field_validator("then", mode="before")
    @classmethod
    def _actions(cls, v: Any) -> Any:
        return [a for a in v if isinstance(a, dict) and a.get("intent")][:2] if isinstance(v, list) else []


class PendingAction(BaseModel):
    """The one question the bot is waiting on (stored in conversations.pending_action)."""

    kind: str  # name of the pending resolver that handles the answer
    language: Language
    # amount_or_skip: an amount, or "skip" / "nahi" / "0" (e.g. opening cash)
    # choice_or_name: a list number, or a short name (a new category / bank), handled without the AI
    # free_text: any answer is taken as it is, without the AI (e.g. the shop's address)
    expects: Literal["choice", "choice_or_name", "yes_no", "amount", "amount_or_skip", "phone", "text", "free_text"] = "text"
    data: dict[str, Any] = Field(default_factory=dict)
    # More actions from the same message, done once this flow is finished (see app/services/handler.py)
    queue: list[dict[str, Any]] = Field(default_factory=list)


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
    paid_via: Literal["cash", "bank"] | None = None  # real money moved (payment); None = udhaar / goods
    bank_name: str | None = None
    question: bool = False  # user only ASKS whether this happened ("Ali ko 500 diye?"): answer, never save


class AddPartyFields(_Fields):
    name: str | None = None  # "ek aur customer add karo": the name is asked next
    type: PartyType | None = None
    phone: str | None = None
    opening_amount: Any = None
    opening_direction: Literal["will_get", "will_give"] | None = None


class SetPartyPhoneFields(_Fields):
    party_name: str = Field(min_length=1)
    phone: str = Field(min_length=1)


class RenamePartyFields(_Fields):
    party_name: str | None = None  # the name now ("Aleem")
    new_name: str | None = None  # the right name ("Saleem")


class PartyBalanceFields(_Fields):
    party_name: str | None = None


class ListPartiesFields(_Fields):
    type: PartyType | None = None


class DeleteEntryFields(_Fields):
    party_name: str | None = None
    item: str | None = None  # an expense / note word that describes the entry ("bijli", "chai")
    amount: Any = None


class EntryPhotoFields(DeleteEntryFields):
    pass


class RecentEntriesFields(_Fields):
    limit: int | None = None  # "last 3 entries" -> 3; "akhri customer" -> 1
    date: dt.date | None = None  # "aaj kya hua" -> today
    customers_only: bool | None = None  # about customers / sales
    amount: Any = None  # "wo 500 wala entry dikha" -> only entries of 500


class EditEntryFields(_Fields):
    party_name: str | None = None
    item: str | None = None
    amount: Any = None  # the entry's current amount, if said ("500 nahi 600 thi" -> 500)
    new_amount: Any = None
    new_date: dt.date | None = None
    new_note: str | None = None
    new_qty: Any = None  # a stock entry's corrected quantity ("50 nahi 40 socks thay" -> 40)


# ---------------------------------------------------------------------------
# Cash book + banks
# ---------------------------------------------------------------------------


class CashEntryFields(_Fields):
    direction: Literal["in", "out"] | None = None
    amount: Any = None
    date: dt.date | None = None
    note: str | None = None
    category_word: str | None = None  # expense word as written: "bijli", "kiraya", "chai"
    is_sale: bool | None = None
    bank_name: str | None = None


class TransferFields(_Fields):
    direction: Literal["to_bank", "from_bank"] | None = None
    bank_name: str | None = None
    amount: Any = None
    date: dt.date | None = None


class AddBankFields(_Fields):
    name: str = Field(min_length=1)
    account_number: str | None = None
    opening_amount: Any = None


class MoneyReportFields(_Fields):
    account: str | None = None  # "cash", a bank name, or None = cash + all banks
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    pdf: bool | None = None


# ---------------------------------------------------------------------------
# Stock book. Quantities and rates stay raw: code checks them against the text.
# ---------------------------------------------------------------------------


class StockLine(_Fields):
    name: str | None = None  # the item as written ("socks", "jurab", "cheeni")
    qty: Any = None
    unit: str | None = None
    rate: Any = None  # price per unit, if said ("20 wale", "20 ke hisaab se")


def _lines(v: Any) -> Any:
    if isinstance(v, dict):
        return [v]
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


class AddItemFields(_Fields):
    name: str = Field(min_length=1)
    unit: str | None = None
    category: str | None = None  # the AI's guess of a short shop category ("Kapre", "Grocery")
    sale_price: Any = None
    purchase_price: Any = None
    qty: Any = None  # stock the shop has now
    low_stock_level: Any = None
    barcode: str | None = None


class StockInFields(_Fields):
    items: list[StockLine] = Field(default_factory=list)
    supplier_name: str | None = None
    paid_via: Literal["udhaar", "cash", "bank", "none"] | None = None
    paid_amount: Any = None  # paid now when the rest is udhaar ("500 cash diye baqi udhaar")
    bank_name: str | None = None
    date: dt.date | None = None

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, v: Any) -> Any:
        return _lines(v)

    @field_validator("paid_via", mode="before")
    @classmethod
    def _unknown_paid_via(cls, v: Any) -> Any:
        return v if v in ("udhaar", "cash", "bank", "none") else None


class StockOutFields(_Fields):
    items: list[StockLine] = Field(default_factory=list)
    reason: str | None = None  # kharab, muft, istemal ...
    date: dt.date | None = None

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, v: Any) -> Any:
        return _lines(v)


class StockReportFields(_Fields):
    kind: Literal["list", "rates", "low", "value", "in", "out", "item"] = "list"
    item: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    pdf: bool | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _unknown_kind(cls, v: Any) -> Any:
        return v if v in ("list", "rates", "low", "value", "in", "out", "item") else "list"


class EditItemFields(_Fields):
    item: str = Field(min_length=1)
    new_name: str | None = None
    unit: str | None = None
    category: str | None = None
    sale_price: Any = None
    purchase_price: Any = None
    low_stock_level: Any = None


class ItemFields(_Fields):
    item: str = Field(min_length=1)


# ---------------------------------------------------------------------------
# Bills. Numbers stay raw: code checks every one against the text.
# ---------------------------------------------------------------------------


class EmployeeFields(_Fields):
    name: str | None = None
    phone: str | None = None


class ProfitFields(_Fields):
    start_date: dt.date | None = None  # null = today
    end_date: dt.date | None = None


class CreateBillFields(_Fields):
    customer_name: str | None = None  # None = walk-in (counter sale)
    items: list[StockLine] = Field(default_factory=list)
    discount_percent: Any = None
    discount_amount: Any = None
    tax_percent: Any = None
    tax_amount: Any = None
    paid_via: Literal["cash", "bank", "udhaar"] | None = None
    paid_amount: Any = None  # paid now when the rest is udhaar ("1000 diye baqi udhaar")
    bank_name: str | None = None
    date: dt.date | None = None

    @field_validator("items", mode="before")
    @classmethod
    def _items(cls, v: Any) -> Any:
        return _lines(v)

    @field_validator("paid_via", mode="before")
    @classmethod
    def _unknown_paid_via(cls, v: Any) -> Any:
        return v if v in ("cash", "bank", "udhaar") else None


class BillReportFields(_Fields):
    kind: Literal["list", "one"] = "list"
    bill_no: int | None = None
    customer_name: str | None = None
    start_date: dt.date | None = None
    end_date: dt.date | None = None
    pdf: bool | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _unknown_kind(cls, v: Any) -> Any:
        return v if v in ("list", "one") else "list"

    @field_validator("bill_no", mode="before")
    @classmethod
    def _bad_no(cls, v: Any) -> Any:
        try:
            return int(str(v).strip().lstrip("#")) if v not in (None, "") else None
        except ValueError:
            return None


class CancelBillFields(BillReportFields):
    pass


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
    bank_name: str | None = None  # bank rows: JazzCash / Easypaisa / Meezan ...

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
    item_amounts: list[Any] = Field(default_factory=list)  # a bill's line amounts (code adds them up)
    rows: list[ExtractedRow] = Field(default_factory=list)

    @field_validator("item_amounts", mode="before")
    @classmethod
    def _none_items(cls, v: Any) -> Any:
        return v if isinstance(v, list) else []

    @field_validator("kind", mode="before")
    @classmethod
    def _unknown_kind(cls, v: Any) -> Any:
        return v if v in ("register", "bill", "payment", "other") else "other"

    @field_validator("rows", mode="before")
    @classmethod
    def _none_rows(cls, v: Any) -> Any:
        return v or []
