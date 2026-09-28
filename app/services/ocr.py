"""OCR: read the text in a photo.

Two providers, picked by which key is set (settings):
  - Gemini (GEMINI_API_KEY): a vision AI that copies the page's text, keeping
    table columns; best with messy handwriting. Used when its key is set.
  - Google Cloud Vision (GOOGLE_VISION_API_KEY): classic OCR; we rebuild the
    columns from word positions (_layout).

Only the image goes to Google; nothing from the database. Keys are never logged.
Either way the text then goes to our extractor, every amount is checked
against this text, and the user confirms before anything is saved.
"""

import base64
import io
import logging
import time
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
    """All text in the image, in reading order and as a column layout (both '' if none)."""
    settings = get_settings()
    if not (settings.gemini_api_key or settings.google_vision_api_key):
        raise OCRError("off", "no OCR key is set")
    path = Path(path)
    if not path.is_file():
        raise OCRError("bad_image", "file not found")
    if path.stat().st_size > settings.ocr_max_image_mb * 1024 * 1024:
        raise OCRError("too_big")
    image = _prepare(path)
    return _read_gemini(image) if settings.gemini_api_key else _read_vision(image)


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

GEMINI_INSTRUCTION = """Copy ALL the text in this photo exactly as written. It is from a small shop in Pakistan:
a khata register page, a bill, a payment screenshot, or a handwritten list, in Urdu, English or both.
- Keep each line of the page on its own line, in the same order.
- For tables, keep the columns: separate the cells of a row with " | ", and keep an empty cell empty
  (so a number stays under its heading).
- Keep Urdu in Urdu script and English as English. Copy numbers exactly; do not convert, add or total anything.
- If a word or number cannot be read, write [?] for it. Never guess or correct anything.
- Return only the text, with no explanation. If there is no text, return nothing."""


def _post_gemini(model: str, body: dict) -> httpx.Response | None:
    """One model; a "busy" answer (503) gets one more try after a short wait. None = no answer (timeout)."""
    response = None
    for attempt in range(2):
        try:
            response = httpx.post(
                GEMINI_URL.format(model=model),
                headers={"x-goog-api-key": get_settings().gemini_api_key},
                json=body,
                timeout=45,
            )
        except httpx.HTTPError as e:
            log.warning("gemini %s: %s", model, type(e).__name__)
            return None
        if response.status_code not in (500, 503) or attempt == 1:
            return response
        time.sleep(3)
    return response


def _read_gemini(image: str) -> OcrResult:
    settings = get_settings()
    body = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": "image/jpeg", "data": image}},
            {"text": GEMINI_INSTRUCTION},
        ]}],
        "generationConfig": {"temperature": 0},
    }
    # The free tier allows ~20 photos a day PER MODEL and is often "busy" (503). Each model in
    # GEMINI_MODELS has its own quota, so when one is full or busy the next one is tried.
    response = None
    for model in settings.gemini_model_list:
        response = _post_gemini(model, body)
        if response is not None and response.status_code not in (404, 429, 500, 503):
            break
        log.warning("gemini %s: %s, trying the next model", model, response.status_code if response else "timeout")
    if response is None:
        raise OCRError("failed", "every Gemini model timed out")

    data = response.json() if response.content else {}
    if response.status_code != 200:
        error = data.get("error", {})
        log.warning("gemini API %s %s", response.status_code, error.get("status"))
        reason = "off" if response.status_code in (401, 403) else "failed"
        raise OCRError(reason, f"{response.status_code} {error.get('status', '')}")

    candidates = data.get("candidates") or []
    parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
    text = "".join(p.get("text", "") for p in parts).strip()
    if not candidates:  # blocked or empty answer
        raise OCRError("failed", str(data.get("promptFeedback", ""))[:100])
    return OcrResult(text=text, layout="")  # the text already keeps the columns (" | "): no separate layout


# ---------------------------------------------------------------------------
# Google Cloud Vision
# ---------------------------------------------------------------------------


def _read_vision(image: str) -> OcrResult:
    settings = get_settings()
    body = {
        "requests": [
            {
                "image": {"content": image},
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
