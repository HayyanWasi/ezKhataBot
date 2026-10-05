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


def typed_phone(raw: str) -> str:
    """A WhatsApp number the user typed (an employee's): a Pakistani mobile (03001234567, 3001234567,
    +92 300 1234567), or a foreign number written with + / 00. "1234567890" or "0333" is refused."""
    raw = raw.strip()
    digits = re.sub(r"\D", "", raw)
    foreign = raw.startswith("+") or digits.startswith("00")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("03"):
        digits = "92" + digits[1:]
    elif len(digits) == 10 and digits.startswith("3"):
        digits = "92" + digits
    if re.fullmatch(r"923\d{9}", digits):
        return digits
    if foreign and not digits.startswith("92") and 10 <= len(digits) <= 15:
        return digits
    raise ValueError(f"Invalid phone number: {raw!r}")
