"""One structured LLM call, shared by the classifier and the image extractor.

Any OpenAI-compatible API via the .env settings: Groq, OpenRouter and Gemini keys
(settings.llm_endpoints). Calls take turns across the keys. The model returns JSON
that LangChain parses into the given Pydantic schema. On a rate limit, no credits
left or an error, the next key is tried. Keys are never logged.
"""

import itertools
import logging
import time
from functools import lru_cache

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from openai import APIStatusError, RateLimitError
from pydantic import BaseModel

from app.core.config import get_settings

log = logging.getLogger("ezkhata.ai")

_turn = itertools.count()  # which key the next call starts at


class AIError(Exception):
    """The LLM could not produce a valid answer."""


def _used_up(error: Exception) -> bool:
    """Rate limited (429), no credits left (402), the model is not open to this key (404), the request is
    over this key's per-minute token limit (413, Groq free tier), or it is busy (500 / 503). The next key
    is tried without counting it as a failure."""
    return isinstance(error, RateLimitError) or (
        isinstance(error, APIStatusError) and error.status_code in (402, 404, 413, 500, 503)
    )


@lru_cache
def _model(
    schema: type[BaseModel], base_url: str, model_name: str, api_key: str, max_tokens: int,
    reasoning_effort: str, top_p: float | None,
) -> Runnable:
    s = get_settings()
    llm = ChatOpenAI(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        temperature=s.llm_temperature,
        top_p=top_p,
        timeout=s.llm_timeout_seconds,
        max_retries=0,  # retries and key fallback are handled below
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort or None,
    )
    # json_mode: the prompt describes the JSON; LangChain parses it into the schema
    return llm.with_structured_output(schema, method="json_mode")


def call_structured[T: BaseModel](
    schema: type[T], messages: list[tuple[str, str]], run_name: str, max_tokens: int | None = None
) -> T:
    """max_tokens: the answer cap. Groq counts prompt + cap against its per-minute limit, so short
    answers (the classifier) use a small cap; the default (settings) is for long ones (photo rows).

    Calls take turns: each one starts at the next key (Groq, OpenRouter, Gemini ...), so the load is
    spread and no single key hits its per-minute limit. A key that is used up or fails passes the call
    on to the next one; after 4 real failures (not limits) the call gives up."""
    settings = get_settings()
    endpoints = settings.llm_endpoints
    if not endpoints:
        raise AIError("no LLM key is set")
    cap = max_tokens or settings.llm_max_tokens
    start = next(_turn) % len(endpoints)
    order = endpoints[start:] + endpoints[:start]

    last_error: Exception | None = None
    failures = 0
    for attempt, endpoint in enumerate(order, 1):
        key_no = endpoints.index(endpoint) + 1
        base_url, model_name, api_key, (reasoning_effort, top_p, short_cap) = endpoint
        # A short call (the classifier) uses the provider's own short cap when it has one (Qwen)
        call_cap = short_cap if max_tokens and short_cap else cap
        model = _model(schema, base_url, model_name, api_key, call_cap, reasoning_effort, top_p)
        started = time.monotonic()
        try:
            result = model.invoke(messages, config={"run_name": run_name})
        except Exception as e:
            last_error = e
            if _used_up(e):
                log.warning("%s call %d: key #%d used up / busy, trying the next key", run_name, attempt, key_no)
            else:  # API error, timeout or unparseable JSON
                failures += 1
                log.warning("%s call %d (key #%d) failed: %s", run_name, attempt, key_no, e)
                if failures >= 4:
                    break
            continue
        log.info(
            "%s call %d (key #%d): %.2fs -> %s",
            run_name, attempt, key_no, time.monotonic() - started, result.model_dump_json(),
        )
        return result
    raise AIError(str(last_error))
