"""EzKhata server: WhatsApp webhook + reminders.

    uv run uvicorn app.main:app --port 8000

Run ONE process only (no --workers): the reminder scheduler lives inside it."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import webhooks
from app.core.config import get_settings
from app.core.keep_awake import KeepAwake
from app.core.scheduler import ReminderScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("ezkhata").setLevel(os.getenv("EZKHATA_LOG_LEVEL", "INFO").upper())


class _HideSecret(logging.Filter):
    """uvicorn logs every request path; the webhook path holds WEBHOOK_SECRET."""

    def filter(self, record: logging.LogRecord) -> bool:
        secret = get_settings().webhook_secret
        if secret and isinstance(record.args, tuple):
            record.args = tuple(a.replace(secret, "***") if isinstance(a, str) else a for a in record.args)
        return True


logging.getLogger("uvicorn.access").addFilter(_HideSecret())


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = ReminderScheduler({webhooks.channel.name: webhooks.channel})
    scheduler.start()
    keep_awake = KeepAwake()
    if keep_awake.urls:
        keep_awake.start()
    yield
    scheduler.stop()
    keep_awake.stop()


app = FastAPI(title="EzKhata", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(webhooks.router)


@app.api_route("/", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])  # uptime monitors check with HEAD
def health() -> dict:
    return {"ok": True}
