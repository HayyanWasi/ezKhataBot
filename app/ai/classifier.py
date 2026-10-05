"""LLM classifier: one message in, validated structured fields out.

The AI never touches the database; it only fills a ClassifierOutput.
The call itself (key fallback, retry) is in app/ai/llm.py.
"""

import re
from datetime import datetime

from app.ai.llm import AIError, call_structured
from app.core.config import get_settings
from app.ai.prompts import build_system_prompt, build_user_prompt
from app.schemas.khata import ClassifierOutput
from app.services.replies import detect_language
from app.services.registry import IntentSpec

__all__ = ["AIError", "classify"]

_URDU_SCRIPT = re.compile(r"[؀-ۿ]")


def classify(
    text: str,
    *,
    intents: dict[str, IntentSpec],
    history: list[dict],
    pending_question: str | None,
    memories: list[str],
    now: datetime,
) -> ClassifierOutput:
    messages = [
        ("system", build_system_prompt(intents)),
        ("user", build_user_prompt(text, history, pending_question, memories, now)),
    ]
    cap = get_settings().llm_classify_max_tokens
    result = call_structured(ClassifierOutput, messages, "classify_llm", max_tokens=cap)
    if result.intent not in intents and result.intent != "pending_answer":
        # A made-up intent ("cash_report"): ask once more (the next call goes to the next key/model)
        result = call_structured(ClassifierOutput, messages, "classify_llm", max_tokens=cap)

    # Script is certain, the model's guess is not: Urdu script <=> "ur"
    if _URDU_SCRIPT.search(text):
        result.language = "ur"
    elif result.language == "ur":
        result.language = "roman_ur"
    elif result.language == "en" and detect_language(text, default="en") == "roman_ur":
        result.language = "roman_ur"  # "50 socks aae": common Roman Urdu words decide, not the model's guess
    return result
