"""Send due reminders once, then exit. For a Render Cron Job running every minute:

    uv run python -m app.jobs.send_reminders

The CLI and the server (app/main.py) already do this every 30 s in a background thread,
so this job is only for a setup without them.
"""

import logging

from app.channels.cli import CLIChannel
from app.channels.whatsapp import WhatsAppChannel
from app.services.reminders import run_due_reminders


def channels() -> dict:
    return {"cli": CLIChannel(), "whatsapp": WhatsAppChannel()}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    sent = run_due_reminders(channels())
    logging.getLogger("ezkhata.jobs").info("reminders sent: %d", sent)


if __name__ == "__main__":
    main()
