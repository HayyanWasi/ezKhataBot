"""Read a barcode from a photo, for free, on our own server (zxing-cpp; no API, no quota).

Packet barcodes (EAN-13 / EAN-8 / UPC), QR codes and printed shop codes (Code 128) are read.
A small or blurry photo is tried again enlarged. When the bars can't be read (scratched,
stained), the digits printed under them can still be used: from_text() finds a number whose
check digit is right, so a misread digit is never accepted.
"""

import logging
import re
from pathlib import Path

import zxingcpp
from PIL import Image, ImageOps

log = logging.getLogger("ezkhata.barcode")


def read(path: str | Path) -> str | None:
    """The barcode's number / text, or None if there is no readable barcode."""
    try:
        with Image.open(path) as img:
            image = ImageOps.exif_transpose(img).convert("L")
    except Exception as e:
        log.warning("barcode: cannot open image: %s", type(e).__name__)
        return None
    tries = [image]
    if max(image.size) < 1200:  # a small photo: enlarge it too
        scale = 3 if max(image.size) < 600 else 2
        tries.append(image.resize((image.width * scale, image.height * scale), Image.LANCZOS))
    for candidate in tries:
        for result in zxingcpp.read_barcodes(candidate):
            if result.valid and result.text.strip():
                return result.text.strip()
    return None


def _check_digit_ok(code: str) -> bool:
    """EAN-8 / UPC-A (12) / EAN-13: the last digit checks the others."""
    digits = [int(d) for d in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def from_text(text: str) -> str | None:
    """A valid EAN / UPC number written in some text (the digits under the bars), else None.
    "8 964001 025047" -> "8964001025047"."""
    for match in re.finditer(r"\d[\d \-]{6,20}\d", text):
        code = re.sub(r"\D", "", match.group())
        if len(code) in (8, 12, 13) and _check_digit_ok(code):
            return code
    return None
