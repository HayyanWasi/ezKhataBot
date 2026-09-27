"""LLM classifier: one message in, validated structured fields out.

The AI never touches the database; it only fills a ClassifierOutput.
Uses LangChain's ChatOpenAI, which works with any OpenAI-compatible API
(Groq, OpenRouter) via the .env settings.
"""

import logging
import re
import time
from datetime import date
from functools import lru_cache

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from openai import RateLimitError

from app.ai.prompts import build_system_prompt, build_user_prompt
from app.core.config import get_settings
from app.schemas.khata import ClassifierOutput
from app.services.registry import IntentSpec

log = logging.getLogger("ezkhata.ai")

_URDU_SCRIPT = re.compile(r"[؀-ۿ]")


class AIError(Exception):
    """The classifier could not produce a valid answer."""


@lru_cache
def _model(model_name: str, api_key: str) -> Runnable:
    s = get_settings()
    llm = ChatOpenAI(
        model=model_name,
        base_url=s.llm_base_url,
        api_key=api_key,
        temperature=0,
        timeout=s.llm_timeout_seconds,
        max_retries=0,  # retries and key fallback are handled in classify()
        reasoning_effort=s.llm_reasoning_effort or None,
    )
    # json_mode: the prompt describes the JSON; LangChain parses it into ClassifierOutput
    return llm.with_structured_output(ClassifierOutput, method="json_mode")


def classify(
    text: str,
    *,
    intents: dict[str, IntentSpec],
    history: list[dict],
    pending_question: str | None,
    memories: list[str],
    today: date,
) -> ClassifierOutput:
    messages = [
        ("system", build_system_prompt(intents)),
        ("user", build_user_prompt(text, history, pending_question, memories, today)),
    ]
    settings = get_settings()
    keys = settings.llm_api_keys  # main key first, then fallbacks

    last_error: Exception | None = None
    key_index, failures, attempt = 0, 0, 0
    while key_index < len(keys) and failures < 2:  # one retry on invalid output / API error
        attempt += 1
        model = _model(settings.llm_model, keys[key_index])
        started = time.monotonic()
        try:
            result: ClassifierOutput = model.invoke(messages, config={"run_name": "classify_llm"})
        except RateLimitError as e:  # this key is used up: try the next one (keys are never logged)
            last_error = e
            log.warning("ai call %d: key #%d rate limited, trying the next key", attempt, key_index + 1)
            key_index += 1
            continue
        except Exception as e:  # API error or unparseable JSON
            last_error = e
            failures += 1
            log.warning("ai call %d failed: %s", attempt, e)
            continue

        # Script is certain, the model's guess is not: Urdu script <=> "ur"
        if _URDU_SCRIPT.search(text):
            result.language = "ur"
        elif result.language == "ur":
            result.language = "roman_ur"

        log.info(
            "ai call %d (key #%d): %.2fs -> %s",
            attempt, key_index + 1, time.monotonic() - started, result.model_dump_json(),
        )
        return result
    raise AIError(str(last_error))
