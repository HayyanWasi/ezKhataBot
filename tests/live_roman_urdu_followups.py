"""Run live multi-turn employee checks on the synthetic CLI shop."""

import json
import time
from pathlib import Path

from live_roman_urdu_bot import CaptureChannel, send, setup

OUT = Path(__file__).with_name("live_roman_urdu_followup_results.json")
MESSAGES = [
    "Ali ko employee add karo 999000000000002",
    "haan ji",
    "employees dikhao",
    "Ali ko employee add karo 999000000000002",
    "Ali ko employee se hatao",
    "nahi",
    "employees dikhao",
    "employee add karo Sana and number",
    "999000000000003",
    "employees dikhao",
]


def main():
    user_id, shop_id = setup()
    channel = CaptureChannel()
    results = []
    try:
        for i, message in enumerate(MESSAGES, 1):
            item = send(channel, message)
            item["index"] = i
            results.append(item)
            OUT.write_text(json.dumps({"user_id": user_id, "shop_id": shop_id, "results": results},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{i}/{len(MESSAGES)} {item['intent']} pending={item['pending_kind']} {message!r}", flush=True)
            time.sleep(22 if i not in (2, 6) else 2)
    finally:
        OUT.write_text(json.dumps({"user_id": user_id, "shop_id": shop_id, "results": results},
                                  ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
