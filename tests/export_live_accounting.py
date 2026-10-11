"""Export the five live accounting replies from the synthetic audit conversation."""

import json
from pathlib import Path

from live_roman_urdu_bot import PHONE
from app.core.database import transaction

TEXTS = ["chai 200", "0", "1", "aaj ka cash dikhao", "aaj ka hisaab"]
OUT = Path(__file__).with_name("live_roman_urdu_accounting_results.json")

with transaction() as conn:
    rows = conn.execute(
        """select u.text as input, u.intent, u.processing_status, u.error,
                  b.text as reply, b.delivery_status
           from public.messages u
           join public.conversations c on c.id = u.conversation_id
           left join public.messages b on b.reply_to_id = u.id
           join public.users owner on owner.id = c.user_id
           where owner.phone = %s and c.channel = 'cli' and u.role = 'user'
             and u.text = any(%s)
           order by u.created_at desc""",
        (PHONE, TEXTS),
    ).fetchall()

latest = {}
for row in rows:
    latest.setdefault(row["input"], dict(row))
if set(latest) != set(TEXTS):
    raise RuntimeError(f"Missing live accounting messages: {set(TEXTS) - set(latest)}")
OUT.write_text(json.dumps([latest[t] for t in TEXTS], ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Exported {len(TEXTS)} exact live replies")
