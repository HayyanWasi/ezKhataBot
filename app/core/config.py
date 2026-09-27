import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

# Put .env into the process environment so SDKs that read it directly
# (LangSmith tracing: LANGSMITH_*) see their settings too.
load_dotenv(ROOT_DIR / ".env")

if os.getenv("LANGSMITH_TRACING", "").lower() == "true" and not os.getenv("LANGSMITH_API_KEY"):
    logging.getLogger("ezkhata").warning("LANGSMITH_TRACING is on but LANGSMITH_API_KEY is empty: tracing disabled")
    os.environ["LANGSMITH_TRACING"] = "false"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # Supabase Postgres (public schema) for app data
    app_database_url: str

    # LLM (any OpenAI-compatible API: Groq, OpenRouter)
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str
    llm_fallback_api_keys: str = ""  # comma-separated; tried in order when a key is rate limited
    llm_model: str = "openai/gpt-oss-120b"
    llm_reasoning_effort: str = "low"  # empty = don't send (for providers that reject it)
    llm_timeout_seconds: float = 20

    # Conversation
    pending_ttl_seconds: int = 600  # pending question expires after 10 min
    history_limit: int = 5  # previous messages sent to the AI as context

    # Duplicate handling: a message stuck in 'received' longer than this is
    # treated as a crashed attempt and may be processed again
    processing_lease_seconds: int = 60

    @property
    def llm_api_keys(self) -> list[str]:
        """Main key first, then the fallbacks."""
        fallbacks = [k.strip() for k in self.llm_fallback_api_keys.split(",") if k.strip()]
        return [self.llm_api_key, *fallbacks]


@lru_cache
def get_settings() -> Settings:
    return Settings()
