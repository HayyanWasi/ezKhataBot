"""Rule-based parsing of short answers, so they don't need an AI call."""

import re
from collections.abc import Callable
from typing import TypeVar

from app.services.amounts import parse_amount_answer

T = TypeVar("T")

# Urdu/Arabic-Indic digits -> ASCII
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_YES = {"haan", "han", "haa", "ha", "ji", "jee", "yes", "y", "ok", "okay", "theek", "thik", "ہاں", "جی", "ٹھیک"}
_NO = {"nahi", "nhi", "nai", "na", "no", "n", "نہیں", "نہ"}


def parse_number(text: str) -> int | None:
    text = text.strip().translate(_DIGITS)
    return int(text) if re.fullmatch(r"\d{1,3}", text) else None


def parse_yes_no(text: str) -> bool | None:
    word = text.strip().lower().rstrip(".!")
    if word in _YES:
        return True
    if word in _NO:
        return False
    return None


_SKIP = {"skip", "chhor", "chhoro", "chor", "choro", "pata nahi", "pata nhi", "nahi pata", "nhi pata", "چھوڑو"}


def is_skip(text: str) -> bool:
    """"skip" / "nahi" / "pata nahi": the user doesn't want to answer."""
    word = text.strip().lower().rstrip(".!")
    return word in _SKIP or parse_yes_no(word) is False


def is_trivial_answer(text: str, expects: str) -> bool:
    """True if the message can be answered by rules alone (no AI)."""
    if expects == "choice":
        return parse_number(text) is not None
    if expects == "yes_no":
        return parse_yes_no(text) is not None
    if expects == "amount":
        return parse_amount_answer(text) is not None
    if expects == "amount_or_skip":
        return parse_amount_answer(text) is not None or text.strip() == "0" or is_skip(text)
    if expects == "choice_or_name":  # "2", or a short name like "Bills" / "Ghar ka kharcha"
        words = text.split()
        if parse_number(text) is not None:
            return True
        not_a_name = is_skip(text) or parse_yes_no(text) is not None or text.strip().lower() in ("undo", "cancel")
        return 0 < len(words) <= 3 and not re.search(r"\d", text) and not not_a_name
    return False


def pick(answer: str, items: list[T], label: Callable[[T], str]) -> T | None:
    """Pick an item by list number ("2") or by a unique name match ("hayyan store")."""
    number = parse_number(answer)
    if number is not None:
        return items[number - 1] if 1 <= number <= len(items) else None
    needle = answer.strip().lower()
    if not needle:
        return None
    exact = [x for x in items if label(x).lower() == needle]
    if len(exact) == 1:
        return exact[0]
    partial = [x for x in items if needle in label(x).lower()]
    return partial[0] if len(partial) == 1 else None
