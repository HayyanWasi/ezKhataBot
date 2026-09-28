"""One structured LLM call, shared by the classifier and the image extractor.

Any OpenAI-compatible API via the .env settings: Groq keys first, then
OpenRouter keys (settings.llm_endpoints). The model returns JSON that LangChain
parses into the given Pydantic schema. On a rate limit (or no credits left) the
next key is tried; any other failure gets one retry. Keys are never logged.
"""

import logging
import time
from functools import lru_cache

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from openai import APIStatusError, RateLimitError
from pydantic import BaseModel

from app.core.config import get_settings

log = logging.getLogger("ezkhata.ai")


class AIError(Exception):
    """The LLM could not produce a valid answer."""


def _used_up(error: Exception) -> bool:
    """Rate limited (429), or no credits left on this key (402)."""
    return isinstance(error, RateLimitError) or (isinstance(error, APIStatusError) and error.status_code == 402)


@lru_cache
def _model(schema: type[BaseModel], base_url: str, model_name: str, api_key: str) -> Runnable:
    s = get_settings()
    llm = ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=0,
        timeout=s.llm_timeout_seconds,
        max_retries=0,  # retries and key fallback are handled below
        max_tokens=s.llm_max_tokens,
        reasoning_effort=s.llm_reasoning_effort or None,
    )
    # json_mode: the prompt describes the JSON; LangChain parses it into the schema
    return llm.with_structured_output(schema, method="json_mode")


def call_structured[T: BaseModel](schema: type[T], messages: list[tuple[str, str]], run_name: str) -> T:
    endpoints = get_settings().llm_endpoints  # Groq keys first, then OpenRouter keys

    last_error: Exception | None = None
    key_index, failures, attempt = 0, 0, 0
    while key_index < len(endpoints) and failures < 2:  # one retry on invalid output / API error
        attempt += 1
        model = _model(schema, *endpoints[key_index])
        started = time.monotonic()
        try:
            result = model.invoke(messages, config={"run_name": run_name})
        except Exception as e:
            last_error = e
            if _used_up(e):  # this key is used up: try the next one
                log.warning("%s call %d: key #%d used up, trying the next key", run_name, attempt, key_index + 1)
                key_index += 1
            else:  # API error or unparseable JSON
                failures += 1
                log.warning("%s call %d failed: %s", run_name, attempt, e)
            continue
        log.info(
            "%s call %d (key #%d): %.2fs -> %s",
            run_name, attempt, key_index + 1, time.monotonic() - started, result.model_dump_json(),
        )
        return result
    raise AIError(str(last_error))
