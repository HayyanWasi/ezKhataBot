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
    llm_max_tokens: int = 2500  # answer cap; without it providers reserve the whole context per call

    # Second provider, tried after every key above is rate limited (empty = off)
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_keys: str = ""  # comma-separated
    openrouter_model: str = "openai/gpt-oss-120b"

    # Conversation
    pending_ttl_seconds: int = 600  # pending question expires after 10 min
    history_limit: int = 5  # previous messages sent to the AI as context

    # Duplicate handling: a message stuck in 'received' longer than this is
    # treated as a crashed attempt and may be processed again
    processing_lease_seconds: int = 60

    # Files (PDF statements). Local disk for now; cloud storage on the server later.
    storage_dir: Path = ROOT_DIR / "storage"

    # Reminders: a reminder for a day (no time) is sent at these times
    reminder_day_times: str = "10:00,18:00"
    scheduler_interval_seconds: int = 30

    # Image entries: OCR reads the photo's text. Gemini (free tier, reads handwriting best) is used
    # when its key is set, else Google Cloud Vision. No key at all = feature off.
    gemini_api_key: str = ""
    # comma-separated, tried in order: each model has its own free daily quota (~20 photos)
    gemini_models: str = "gemini-2.5-flash,gemini-flash-latest,gemini-flash-lite-latest"
    google_vision_api_key: str = ""
    ocr_max_rows: int = 20
    ocr_max_image_mb: int = 10

    @property
    def llm_api_keys(self) -> list[str]:
        """Main key first, then the fallbacks."""
        fallbacks = [k.strip() for k in self.llm_fallback_api_keys.split(",") if k.strip()]
        return [self.llm_api_key, *fallbacks]

    @property
    def gemini_model_list(self) -> list[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]

    @property
    def llm_endpoints(self) -> list[tuple[str, str, str]]:
        """(base_url, model, api_key) in the order they are tried: main provider's keys, then OpenRouter's."""
        main = [(self.llm_base_url, self.llm_model, key) for key in self.llm_api_keys]
        backup = [k.strip() for k in self.openrouter_api_keys.split(",") if k.strip()]
        return main + [(self.openrouter_base_url, self.openrouter_model, key) for key in backup]


@lru_cache
def get_settings() -> Settings:
    return Settings()
