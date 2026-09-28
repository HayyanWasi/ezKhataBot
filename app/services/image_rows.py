"""Which photo rows can be saved, and how. One RowSaver per row category.

A photo can hold several kinds of rows (party udhaar, expenses, cash, bank,
sales). Each feature registers a saver for the categories it owns:
    Feature 1 (now):     party_entry        -> app/handlers/images.py
    Feature 2 (later):   expense, cash_in, cash_out, bank
    Feature 3 (later):   sale
Rows whose category has no saver yet are still shown, but not saved.
"""

from collections.abc import Callable
from dataclasses import dataclass

from psycopg import Connection

from app.schemas.khata import ExtractedRow
from app.services.registry import Context


@dataclass
class RowSaver:
    section: str  # reply template key for this category's heading in the preview
    # Check one row (read-only) -> a JSON-safe item with at least "category", "ready" (bool), "line" (preview text)
    prepare: Callable[[Context, ExtractedRow, str], dict]
    # Save one ready item inside the commit transaction. `state` is shared by all items of the photo.
    save: Callable[[Connection, Context, dict, int, dict], None]
    # Reply lines after saving (e.g. new balances), inside the same transaction
    summary: Callable[[Connection, Context, dict], list[str]]
    # For an item that is not ready: an entry draft whose questions fill in what is missing
    follow_up: Callable[[Context, dict, dict], dict] | None = None


ROW_SAVERS: dict[str, RowSaver] = {}
