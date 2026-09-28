"""Background scheduler: sends due reminders every few seconds.

Runs as a daemon thread inside whichever process is up (the CLI now, the
server later). Only one process should run it at a time.
"""

import logging
import threading

from app.channels.base import Channel
from app.core.config import get_settings

log = logging.getLogger("ezkhata.scheduler")


class ReminderScheduler(threading.Thread):
    def __init__(self, channels: dict[str, Channel], interval: float | None = None) -> None:
        super().__init__(name="reminder-scheduler", daemon=True)
        self.channels = channels
        self.interval = interval or get_settings().scheduler_interval_seconds
        self.stopped = threading.Event()

    def run(self) -> None:
        from app.services.reminders import run_due_reminders  # imported here: loads the whole app

        while not self.stopped.is_set():
            try:
                run_due_reminders(self.channels)
            except Exception:
                log.exception("reminder run failed")
            self.stopped.wait(self.interval)

    def stop(self) -> None:
        self.stopped.set()
