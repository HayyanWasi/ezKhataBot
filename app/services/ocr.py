"""OCR: read the text in a photo with Google Cloud Vision.

Only the image goes to Google; nothing from the database. The API key comes
from settings (GOOGLE_VISION_API_KEY) and is never logged.
"""

import base64
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from app.core.config import get_settings

log = logging.getLogger("ezkhata.ocr")

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
MAX_SIDE = 2000  # px; big phone photos are shrunk before sending


@dataclass
class OcrResult:
    text: str  # reading order (correct for Urdu, right to left)
    layout: str  # words placed by their position on the page, so table columns stay visible


class OCRError(Exception):
    """The image could not be read. `reason` is one of: off, too_big, bad_image, failed."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


def _prepare(path: Path) -> str:
    """Rotate by EXIF, convert to RGB, shrink to MAX_SIDE, JPEG -> base64."""
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((MAX_SIDE, MAX_SIDE))
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=85)
    except Exception as e:
        raise OCRError("bad_image", str(e)) from e
    return base64.b64encode(buffer.getvalue()).decode()


def _layout(annotation: dict, width: int = 100) -> str:
    """Rebuild the page as text lines, putting each word at its horizontal position.
    A number under a "Liye" heading then stays under it, so the columns can be read."""
    words = []
    for page in annotation.get("pages", []):
        page_width = page.get("width") or 1
        for block in page.get("blocks", []):
            for paragraph in block.get("paragraphs", []):
                for word in paragraph.get("words", []):
                    xs = [v.get("x", 0) for v in word["boundingBox"]["vertices"]]
                    ys = [v.get("y", 0) for v in word["boundingBox"]["vertices"]]
                    text = "".join(sym["text"] for sym in word.get("symbols", []))
                    words.append((sum(ys) / len(ys), max(ys) - min(ys) or 1, min(xs) / page_width, text))
    if not words:
        return ""

    words.sort()
    lines: list[list[tuple]] = []
    for word in words:  # same line when the vertical centres are close
        if lines and abs(word[0] - lines[-1][-1][0]) < 0.6 * word[1]:
            lines[-1].append(word)
        else:
            lines.append([word])

    out = []
    for line in lines:
        row = ""
        for _, _, x, text in sorted(line, key=lambda w: w[2]):
            column = int(x * width)
            row += " " * max(1, column - len(row)) if row else " " * column
            row += text
        out.append(row.rstrip())
    return "\n".join(out)


def read_text(path: str | Path) -> OcrResult:
    """All text in the image, in reading order and as a position layout (both '' if none)."""
    settings = get_settings()
    if not settings.google_vision_api_key:
        raise OCRError("off", "GOOGLE_VISION_API_KEY is not set")
    path = Path(path)
    if not path.is_file():
        raise OCRError("bad_image", "file not found")
    if path.stat().st_size > settings.ocr_max_image_mb * 1024 * 1024:
        raise OCRError("too_big")

    body = {
        "requests": [
            {
                "image": {"content": _prepare(path)},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                "imageContext": {"languageHints": ["ur", "en"]},
            }
        ]
    }
    try:
        response = httpx.post(VISION_URL, params={"key": settings.google_vision_api_key}, json=body, timeout=30)
    except httpx.HTTPError as e:
        raise OCRError("failed", type(e).__name__) from e

    data = response.json() if response.content else {}
    if response.status_code != 200:
        error = data.get("error", {})
        # e.g. 403 PERMISSION_DENIED (billing off / key restricted), 429 RESOURCE_EXHAUSTED (quota)
        log.warning("vision API %s %s", response.status_code, error.get("status"))
        reason = "off" if response.status_code == 403 else "failed"
        raise OCRError(reason, f"{response.status_code} {error.get('status', '')}")

    result = data["responses"][0]
    if "error" in result:
        raise OCRError("failed", result["error"].get("message", ""))
    annotation = result.get("fullTextAnnotation", {})
    return OcrResult(text=annotation.get("text", ""), layout=_layout(annotation))
