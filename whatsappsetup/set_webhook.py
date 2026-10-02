"""Tell Evolution where to send incoming WhatsApp messages (the EzKhata server's webhook).

    uv run python -m whatsappsetup.set_webhook http://host.docker.internal:8000      (bot on this PC)
    uv run python -m whatsappsetup.set_webhook https://<bot>.onrender.com            (bot on Render)

The secret part of the URL comes from WEBHOOK_SECRET in .env and is never printed."""

import sys

import requests

from app.core.config import get_settings


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    s = get_settings()
    if not s.webhook_secret:
        sys.exit("Set WEBHOOK_SECRET in .env first (a long random string).")
    url = f"{sys.argv[1].rstrip('/')}/webhook/evolution/{s.webhook_secret}"
    webhook = {"enabled": True, "url": url, "webhookByEvents": False, "webhookBase64": False, "events": ["MESSAGES_UPSERT"]}
    res = requests.post(
        f"{s.evolution_api_url.rstrip('/')}/webhook/set/{s.evolution_instance}",
        json={"webhook": webhook},
        headers={"apikey": s.evolution_api_key},
        timeout=15,
    )
    print("Webhook set." if res.ok else f"Failed: {res.status_code} {res.text[:300]}")


if __name__ == "__main__":
    main()
