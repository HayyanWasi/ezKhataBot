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
        while True:  # ping at once (a deploy restarts this thread), then every few minutes
            for url in self.urls:
                try:
                    # A sleeping service takes ~1 min to wake up, so wait long enough for it
                    res = requests.get(url, timeout=120)
                    log.info("ping %s -> %s in %.1fs", url, res.status_code, res.elapsed.total_seconds())
                except requests.RequestException as e:
                    log.warning("ping %s failed: %s", url, e)
            if self.stopped.wait(interval):
                return

    def stop(self) -> None:
        self.stopped.set()
