"""Money amounts: read from the user's own text (never trusted from the AI alone),
and formatted for replies. Always Decimal, never float."""

import re
from decimal import Decimal, InvalidOperation

# Urdu/Arabic-Indic digits and separators -> ASCII
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬", "01234567890123456789.,")

_MULTIPLIERS = {
    "sau": 100, "k": 1_000, "hazar": 1_000, "hazaar": 1_000, "hzar": 1_000, "hajar": 1_000,
    "thousand": 1_000, "ہزار": 1_000,
    "lakh": 100_000, "lac": 100_000, "لاکھ": 100_000,
    "crore": 10_000_000, "karor": 10_000_000, "کروڑ": 10_000_000,
}

# 500 | 5,000 | 1,50,000 | 1.5  followed by an optional k / hazar / lakh ...
_AMOUNT = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:,\d{2,3})+|\d+)(\.\d{1,2})?(?![\d])"
    r"(?:\s*(sau|k|hazaar|hazar|hzar|hajar|thousand|lakh|lac|crore|karor|ہزار|لاکھ|کروڑ)(?![a-zA-Z]))?",
    re.IGNORECASE,
)

_MAX = Decimal("999999999999.99")  # fits numeric(14,2)


# Amounts written in words: "paanch sau" 500, "dhai hazar" 2500, "do hazar paanch sau" 2500.
# A number word only counts before sau / hazar / lakh: alone, "do" is "give" and "saath" is "with".
_NUMBER_WORDS = {
    "ek": 1, "aik": 1, "ik": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "panj": 5, "chay": 6, "chhe": 6, "che": 6, "chhay": 6, "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9,
    "das": 10, "dus": 10, "gyarah": 11, "gyara": 11, "barah": 12, "bara": 12, "pandrah": 15, "pandra": 15,
    "bees": 20, "pachees": 25, "pachchees": 25, "tees": 30, "chalees": 40, "chalis": 40, "pachas": 50,
    "pachaas": 50, "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90,
}
# After a hundred / thousand, a tens word can follow alone: "ek sau bees" 120
_TAIL_WORDS = {w: v for w, v in _NUMBER_WORDS.items() if v >= 10 and w != "saath"}
_FRACTIONS = {"dhai": Decimal("2.5"), "dhaai": Decimal("2.5"), "adhai": Decimal("2.5"),
              "dedh": Decimal("1.5"), "derh": Decimal("1.5"), "dairh": Decimal("1.5")}
_QUARTERS = {"sawa": Decimal("0.25"), "sava": Decimal("0.25"), "paune": Decimal("-0.25"), "pone": Decimal("-0.25")}
_WORD_UNITS = {"sau": 100, "so": 100, "hazar": 1_000, "hazaar": 1_000, "hzar": 1_000, "hajar": 1_000,
               "lakh": 100_000, "lac": 100_000, "crore": 10_000_000, "karor": 10_000_000}


def _term(words: list[str], i: int) -> tuple[Decimal, int, int] | None:
    """One "<number word> <unit>" at words[i] ("dhai hazar", "sawa do sau") -> (value, unit, words used)."""
    j, quarter = i, Decimal(0)
    if j < len(words) and words[j] in _QUARTERS:
        quarter, j = _QUARTERS[words[j]], j + 1
    if j < len(words) and words[j] in _FRACTIONS:
        number, j = _FRACTIONS[words[j]], j + 1
    elif j < len(words) and words[j] in _NUMBER_WORDS:
        number, j = Decimal(_NUMBER_WORDS[words[j]]), j + 1
    elif quarter:
        number = Decimal(1)  # "sawa sau" 125, "paune hazar" 750
    else:
        return None
    if j < len(words) and words[j] in _WORD_UNITS:
        unit = _WORD_UNITS[words[j]]
        return (number + quarter) * unit, unit, j + 1 - i
    return None


def _spell_run(match: re.Match) -> str:
    """Words separated only by spaces ("ko dhai hazar diye") with their number words as digits."""
    words = match.group(0).split()
    low = [w.lower() for w in words]
    out, i = [], 0
    while i < len(low):
        total, used, last_unit = Decimal(0), 0, None
        while (term := _term(low, i + used)) and (last_unit is None or term[1] < last_unit):
            total, last_unit, used = total + term[0], term[1], used + term[2]
        if used and i + used < len(low) and low[i + used] in _TAIL_WORDS:
            total, used = total + _TAIL_WORDS[low[i + used]], used + 1
        if used and total == total.to_integral():
            out.append(str(int(total)))
            i += used
        else:
            out.append(words[i])
            i += 1
    return " ".join(out)


def _spell_out(text: str) -> str:
    """Number words -> digits: "Ali ko dhai hazar diye" -> "Ali ko 2500 diye"."""
    return re.sub(r"[^\W\d_]+(?:[ \t]+[^\W\d_]+)*", _spell_run, text)


def parse_amounts(text: str) -> list[Decimal]:
    """Every amount written in the text, in order. Phone numbers are skipped."""
    text = _spell_out(text.translate(_DIGITS))
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
    cleaned = _FILLER.sub(" ", _CURRENCY.sub(" ", _spell_out(text.translate(_DIGITS))))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .!")
    if not _AMOUNT.fullmatch(cleaned):
        return None
    amounts = parse_amounts(cleaned)
    return amounts[0] if len(amounts) == 1 else None
