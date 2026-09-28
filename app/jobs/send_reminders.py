"""Send due reminders once, then exit. For a Render Cron Job running every minute:

    uv run python -m app.jobs.send_reminders

Locally the CLI does the same thing every 30 s in a background thread.
"""

import logging

from app.channels.cli import CLIChannel
from app.services.reminders import run_due_reminders


def channels() -> dict:
    # The WhatsApp channel is added here on WhatsApp day
    return {"cli": CLIChannel()}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    sent = run_due_reminders(channels())
    logging.getLogger("ezkhata.jobs").info("reminders sent: %d", sent)


if __name__ == "__main__":
    main()
