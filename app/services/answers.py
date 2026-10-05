"""Rule-based parsing of short answers, so they don't need an AI call."""

import re
from collections.abc import Callable
from typing import TypeVar

from app.services.amounts import parse_amount_answer

T = TypeVar("T")

# Urdu/Arabic-Indic digits -> ASCII
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_YES = {
    "haan", "han", "haa", "ha", "ji", "jee", "g", "yes", "y", "ok", "okay", "theek", "thik", "bilkul", "sahi",
    "hanji", "haanji", "haan ji", "han ji", "haa ji", "han g", "haan g", "ji haan", "jee haan", "ji han", "g han",
    "theek hai", "thik hai", "ok hai", "kr do", "kar do", "krdo", "kardo", "kar dein", "kr dain", "haan kar do",
    "han kr do", "han krdo", "haan krdo", "ok kar do", "save karo", "save kr do",
    "ہاں", "جی", "ٹھیک", "جی ہاں", "ہاں جی", "ٹھیک ہے", "کر دو",
}
_NO = {
    "nahi", "nhi", "nai", "na", "no", "n", "nahin", "nahi ji", "nhi ji", "na ji", "nai ji", "nahin ji",
    "mat karo", "mat kro", "mat", "nahi karo", "nhi kro", "nahi karna", "nhi krna", "cancel", "cancel karo",
    "cancel kr do", "cancel kardo", "nahi chahiye", "nhi chahiye", "rehne do", "rehnay do", "rhne do", "rehne dein",
    "chor do", "chhor do", "chhoro", "choro", "chodo", "bas karo", "bas kro",
    "نہیں", "نہ", "مت کرو", "رہنے دو", "چھوڑو", "نہیں جی",
}
# Said instead of answering: drop the question ("rehne do"); with no question, just "theek hai"
_CANCEL = _NO - {"nahi", "nhi", "nai", "na", "no", "n", "nahin", "nahi ji", "nhi ji", "na ji", "nai ji",
                 "nahin ji", "mat", "نہیں", "نہ", "نہیں جی"}
_FILLER_WORDS = {"bhai", "yaar", "yar", "please", "plz", "pls", "sir", "boss"}


def _plain(text: str) -> str:
    """"Haan ji bhai!" -> "haan ji": lower case, no punctuation, no trailing bhai / yaar."""
    words = re.sub(r"[.!,?؟۔]+", " ", text.strip().lower()).split()
    while len(words) > 1 and words[-1] in _FILLER_WORDS:
        words.pop()
    return " ".join(words)


def parse_number(text: str) -> int | None:
    text = text.strip().translate(_DIGITS)
    return int(text) if re.fullmatch(r"\d{1,3}", text) else None


def parse_yes_no(text: str) -> bool | None:
    word = _plain(text)
    if word in _YES:
        return True
    if word in _NO:
        return False
    return None


def is_cancel(text: str) -> bool:
    """"rehne do", "cancel karo", "chor do": the user wants to stop, not to answer."""
    return _plain(text) in _CANCEL


_THANKS = re.compile(r"^(shukriya|shukria|shukrya|thanks|thank you|thank u|thx|jazakallah\w*|meherbani|"
                     r"mehrbani|شکریہ|جزاک اللہ)\b", re.IGNORECASE)


def is_thanks(text: str) -> bool:
    return bool(_THANKS.search(_plain(text))) and len(text.split()) <= 4 and not re.search(r"\d", text)


# Words that decide how goods were paid for (stock in, bills). Code decides, not the AI,
# so the same sentence always gives the same result.
UDHAAR_WORDS = {"udhaar", "udhar", "udhari", "credit", "baqi", "baaki", "ادھار", "باقی"}
CASH_WORDS = {"cash", "nakad", "naqad", "nakd", "نقد", "کیش"}
ONLINE_WORDS = {"online", "jazzcash", "easypaisa", "transfer", "آن", "لائن"}


# "<name> ne ... udhaar ki / li / khareedi": the person TOOK the goods (a sale to them), unlike
# "<name> ne 50 socks diye / bheje" or "<name> se aaye" (goods the shop got from a supplier)
_TOOK_WORDS = {"udhaar", "udhar", "li", "liya", "lia", "le", "gaya", "gya", "kharidi", "kharida", "kharide",
               "khareedi", "khareeda", "khareede", "bought", "took", "لی", "لیا", "خریدی", "خریدا", "ادھار"}
_GAVE_WORDS = {"diye", "diya", "di", "bheje", "bheja", "aaye", "aae", "aya", "aaya", "aai", "supply",
               "دیے", "دیا", "بھیجے"}


def bought_by(text: str, name: str | None) -> bool:
    if not name:
        return False
    low, who = text.lower(), re.escape(name.lower())
    if not re.search(rf"\b{who}\s+ne\b", low) or re.search(rf"\b{who}\s+se\b", low):
        return False
    words = set(re.findall(r"\w+", low))
    return bool(words & _TOOK_WORDS) and not words & _GAVE_WORDS




_SKIP = {"skip", "chhor", "chhoro", "chor", "choro", "pata nahi", "pata nhi", "nahi pata", "nhi pata", "چھوڑو"}


def is_skip(text: str) -> bool:
    """"skip" / "nahi" / "pata nahi": the user doesn't want to answer."""
    word = _plain(text)
    return word in _SKIP or parse_yes_no(word) is False


def is_trivial_answer(text: str, expects: str) -> bool:
    """True if the message can be answered by rules alone (no AI)."""
    if expects == "free_text":
        return bool(text.strip())
    if expects == "choice":
        return parse_number(text) is not None
    if expects == "yes_no":
        return parse_yes_no(text) is not None
    if expects == "amount":
        return parse_amount_answer(text) is not None
    if expects == "amount_or_skip":
        return parse_amount_answer(text) is not None or text.strip() == "0" or is_skip(text)
    if expects == "phone":  # "0333-1234567", "+92 333 1234567"
        return bool(re.fullmatch(r"\+?[\d\s-]{4,20}", text.strip()))
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
