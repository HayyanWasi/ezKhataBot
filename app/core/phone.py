import re


def normalize_phone(raw: str) -> str:
    """Store every number as digits with country code: 03001234567 / +92 300 1234567 -> 923001234567."""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = "92" + digits[1:]
    if not 10 <= len(digits) <= 15:
        raise ValueError(f"Invalid phone number: {raw!r}")
    return digits
