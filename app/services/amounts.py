"""Money amounts: read from the user's own text (never trusted from the AI alone),
and formatted for replies. Always Decimal, never float."""

import re
from decimal import Decimal, InvalidOperation

# Urdu/Arabic-Indic digits and separators -> ASCII
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬", "01234567890123456789.,")

_MULTIPLIERS = {
    "k": 1_000, "hazar": 1_000, "hazaar": 1_000, "hzar": 1_000, "hajar": 1_000,
    "thousand": 1_000, "ہزار": 1_000,
    "lakh": 100_000, "lac": 100_000, "لاکھ": 100_000,
    "crore": 10_000_000, "karor": 10_000_000, "کروڑ": 10_000_000,
}

# 500 | 5,000 | 1,50,000 | 1.5  followed by an optional k / hazar / lakh ...
_AMOUNT = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:,\d{2,3})+|\d+)(\.\d{1,2})?(?![\d])"
    r"(?:\s*(k|hazaar|hazar|hzar|hajar|thousand|lakh|lac|crore|karor|ہزار|لاکھ|کروڑ)(?![a-zA-Z]))?",
    re.IGNORECASE,
)

_MAX = Decimal("999999999999.99")  # fits numeric(14,2)


def parse_amounts(text: str) -> list[Decimal]:
    """Every amount written in the text, in order. Phone numbers are skipped."""
    text = text.translate(_DIGITS)
    found = []
    for m in _AMOUNT.finditer(text):
        whole, fraction, unit = m.group(1), m.group(2) or "", m.group(3)
        digits = whole.replace(",", "")
        if len(digits) >= 10 and not unit:  # 03001234567 is a phone, not money
            continue
        try:
            value = Decimal(digits + fraction)
        except InvalidOperation:
            continue
        if unit:
            value = (value * _MULTIPLIERS[unit.lower()]).normalize()
            value = value.quantize(Decimal(1)) if value == value.to_integral() else value
        if 0 < value <= _MAX:
            found.append(value)
    return found


def to_decimal(value: object) -> Decimal | None:
    """The AI's amount (number or string) as a Decimal, or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        amounts = parse_amounts(value)
        return amounts[0] if len(amounts) == 1 else None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def confirmed_amount(text: str, ai_amount: object) -> Decimal | None:
    """The amount to use: the AI's pick, but only if it is written in the user's text."""
    candidates = parse_amounts(text)
    ai_value = to_decimal(ai_amount)
    if ai_value is not None and ai_value in candidates:
        return next(c for c in candidates if c == ai_value)  # keep the user's own precision
    return None


def format_rs(value: Decimal) -> str:
    """Rs 1,200 / Rs 1,200.50: decimals only when there are some."""
    value = abs(value)
    if value == value.to_integral():
        return f"Rs {value:,.0f}"
    return f"Rs {value:,.2f}"


_CURRENCY = re.compile(r"\b(rs\.?|rupay|rupaye|rupees|rupee|pkr)\b|روپے|روپیہ", re.IGNORECASE)


# Words that can sit around a plain amount answer: "bas 500", "500 the", "500 hain"
_FILLER = re.compile(
    r"\b(bas|sirf|only|total|kul|hain|hai|the|tha|thay|ji|jee)\b|ہیں|ہے|تھے|تھا|بس", re.IGNORECASE
)


def parse_amount_answer(text: str) -> Decimal | None:
    """An answer that is ONLY an amount ("500", "5k", "Rs 500"), else None.
    "Bilal ko 300 diye" is a new request, not an answer, so it returns None."""
    cleaned = _FILLER.sub(" ", _CURRENCY.sub(" ", text.translate(_DIGITS)))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .!")
    if not _AMOUNT.fullmatch(cleaned):
        return None
    amounts = parse_amounts(cleaned)
    return amounts[0] if len(amounts) == 1 else None
