"""EzKhata server: WhatsApp webhook + reminders.

    uv run uvicorn app.main:app --port 8000

Run ONE process only (no --workers): the reminder scheduler lives inside it."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import webhooks
from app.core.keep_awake import KeepAwake
from app.core.scheduler import ReminderScheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


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


@app.get("/")
@app.get("/health")
def health() -> dict:
    return {"ok": True}
