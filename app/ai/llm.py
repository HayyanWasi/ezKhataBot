"""One structured LLM call, shared by the classifier and the image extractor.

Any OpenAI-compatible API (Groq, OpenRouter) via the .env settings. The model
returns JSON that LangChain parses into the given Pydantic schema.
On a rate limit the next API key is tried; any other failure gets one retry.
Keys are never logged.
"""

import logging
import time
from functools import lru_cache

from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from openai import RateLimitError
from pydantic import BaseModel

from app.core.config import get_settings

log = logging.getLogger("ezkhata.ai")


class AIError(Exception):
    """The LLM could not produce a valid answer."""


@lru_cache
def _model(schema: type[BaseModel], model_name: str, api_key: str) -> Runnable:
    s = get_settings()
    llm = ChatOpenAI(
        model=model_name,
        base_url=s.llm_base_url,
        api_key=api_key,
        temperature=0,
        timeout=s.llm_timeout_seconds,
        max_retries=0,  # retries and key fallback are handled below
        reasoning_effort=s.llm_reasoning_effort or None,
    )
    # json_mode: the prompt describes the JSON; LangChain parses it into the schema
    return llm.with_structured_output(schema, method="json_mode")


def call_structured[T: BaseModel](schema: type[T], messages: list[tuple[str, str]], run_name: str) -> T:
    settings = get_settings()
    keys = settings.llm_api_keys  # main key first, then fallbacks

    last_error: Exception | None = None
    key_index, failures, attempt = 0, 0, 0
    while key_index < len(keys) and failures < 2:  # one retry on invalid output / API error
        attempt += 1
        model = _model(schema, settings.llm_model, keys[key_index])
        started = time.monotonic()
        try:
            result = model.invoke(messages, config={"run_name": run_name})
        except RateLimitError as e:  # this key is used up: try the next one
            last_error = e
            log.warning("%s call %d: key #%d rate limited, trying the next key", run_name, attempt, key_index + 1)
            key_index += 1
            continue
        except Exception as e:  # API error or unparseable JSON
            last_error = e
            failures += 1
            log.warning("%s call %d failed: %s", run_name, attempt, e)
            continue
        log.info(
            "%s call %d (key #%d): %.2fs -> %s",
            run_name, attempt, key_index + 1, time.monotonic() - started, result.model_dump_json(),
        )
        return result
    raise AIError(str(last_error))
