"""Keeps Render's free services awake: they sleep after 15 min without requests.

A background thread GETs the bot's own public URL and the Evolution URL every few minutes.
Each ping is one tiny request (no database, no AI). Locally no URL is set, so it does nothing."""

import logging
import threading

import requests

from app.core.config import get_settings

log = logging.getLogger("ezkhata.keep_awake")


def urls() -> list[str]:
    s = get_settings()
    found = [u.strip() for u in s.keep_awake_urls.split(",") if u.strip()]
    if s.render_external_url:
        found.insert(0, s.render_external_url.rstrip("/") + "/health")
    return found


class KeepAwake(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="keep-awake", daemon=True)
        self.urls = urls()
        self.stopped = threading.Event()

    def run(self) -> None:
        interval = get_settings().keep_awake_minutes * 60
        while not self.stopped.wait(interval):
            for url in self.urls:
                try:
                    requests.get(url, timeout=30)
                except requests.RequestException as e:
                    log.warning("ping %s failed: %s", url, e)

    def stop(self) -> None:
        self.stopped.set()
