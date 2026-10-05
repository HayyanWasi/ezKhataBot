import logging
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
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
    llm_classify_max_tokens: int = 1000  # the classifier's JSON is short; Groq counts prompt + cap per minute
    # Which providers answer AI calls: any of groq, openrouter, gemini (comma-separated; empty = all).
    # Calls take turns across every key of these providers, so no single key hits its per-minute limit.
    llm_providers: str = ""

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
    gemini_fallback_api_keys: str = ""  # comma-separated; more free quota (each key has its own)
    gemini_openai_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    # Gemini as an LLM too (every key x every model takes turns); empty = off. The free tier is often
    # busy (503) or slow, so there are several: a busy / slow one passes the call on.
    gemini_llm_models: str = "gemini-2.5-flash,gemini-flash-latest,gemini-3.1-flash-lite-preview"
    # comma-separated, tried in order: each model has its own free daily quota (~20 photos)
    gemini_models: str = "gemini-2.5-flash,gemini-flash-latest,gemini-flash-lite-latest"
    google_vision_api_key: str = ""
    ocr_max_rows: int = 20
    ocr_max_image_mb: int = 10

    # WhatsApp through Evolution API (same .env names as the whatsappsetup/ scripts)
    evolution_api_url: str = Field("http://localhost:8080", validation_alias=AliasChoices("EVOLUTION_API_URL", "API_URL"))
    evolution_api_key: str = Field("", validation_alias=AliasChoices("EVOLUTION_API_KEY", "API_KEY"))
    evolution_instance: str = Field("ezkhata", validation_alias=AliasChoices("EVOLUTION_INSTANCE", "INSTANCE"))
    # Part of the webhook URL, so only Evolution can post messages to the bot. Empty = webhook off.
    webhook_secret: str = ""
    message_max_age_seconds: int = 600  # older messages (the bot was down) are ignored
    # Render's free plan sleeps after 15 min without requests, so the server pings these every few
    # minutes. Render sets RENDER_EXTERNAL_URL (the bot's own URL); locally both are empty = off.
    render_external_url: str = ""
    keep_awake_urls: str = ""  # comma-separated, e.g. the Evolution service URL
    keep_awake_minutes: int = 5  # Render sleeps after 15 min idle: 5 leaves room for a missed ping

    @property
    def llm_api_keys(self) -> list[str]:
        """Main key first, then the fallbacks."""
        fallbacks = [k.strip() for k in self.llm_fallback_api_keys.split(",") if k.strip()]
        return [self.llm_api_key, *fallbacks]

    @property
    def gemini_api_keys(self) -> list[str]:
        fallbacks = [k.strip() for k in self.gemini_fallback_api_keys.split(",") if k.strip()]
        return [k for k in [self.gemini_api_key.strip(), *fallbacks] if k]

    @property
    def gemini_model_list(self) -> list[str]:
        return [m.strip() for m in self.gemini_models.split(",") if m.strip()]

    @property
    def llm_endpoints(self) -> list[tuple[str, str, str]]:
        """(base_url, model, api_key) for every key of the allowed providers (LLM_PROVIDERS).
        app/ai/llm.py starts each call at the next one in turn and falls through the rest on a limit."""
        wanted = {p.strip().lower() for p in self.llm_providers.split(",") if p.strip()}
        endpoints = []
        if not wanted or "groq" in wanted:
            endpoints += [(self.llm_base_url, self.llm_model, key) for key in self.llm_api_keys]
        if not wanted or "openrouter" in wanted:
            keys = [k.strip() for k in self.openrouter_api_keys.split(",") if k.strip()]
            endpoints += [(self.openrouter_base_url, self.openrouter_model, key) for key in keys]
        if not wanted or "gemini" in wanted:
            models = [m.strip() for m in self.gemini_llm_models.split(",") if m.strip()]
            endpoints += [(self.gemini_openai_url, m, key) for m in models for key in self.gemini_api_keys]
        return endpoints


@lru_cache
def get_settings() -> Settings:
    return Settings()
