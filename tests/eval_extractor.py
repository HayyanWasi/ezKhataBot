"""Score the image extractor on tests/ocr_texts.jsonl (OCR text -> rows). No Vision call, no DB.

    uv run tests/eval_extractor.py

A row counts as correct when an extracted row has the same category and amount,
and, where the case gives them, the same direction and party name (case-insensitive).
Extra rows the case does not expect are reported as false rows.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.extractor import extract_rows  # noqa: E402
from app.ai.llm import AIError  # noqa: E402
from app.services.amounts import to_decimal  # noqa: E402

CASES = Path(__file__).with_name("ocr_texts.jsonl")
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=ZoneInfo("Asia/Karachi"))


def matches(expected: dict, row) -> bool:
    if row.category != expected["category"]:
        return False
    if to_decimal(row.amount) != to_decimal(expected.get("amount")):
        return False
    if "direction" in expected and row.direction != expected["direction"]:
        return False
    if expected.get("party_name") and (row.party_name or "").strip().lower() != expected["party_name"].lower():
        return False
    if expected.get("date") and (row.date is None or row.date.isoformat() != expected["date"]):
        return False
    return True


def main() -> None:
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    total = correct = extra = 0
    for case in cases:
        for wait in (0, 30, 60):  # free tier: wait out the per-minute limit
            time.sleep(wait)
            try:
                out = extract_rows(case["text"], NOW, case.get("layout"))
                break
            except AIError as e:
                out = None
                if "429" not in str(e):
                    break
        if out is None:
            print(f"  FAIL {case['name']}: AI error")
            total += len(case["rows"])
            continue
        rows = [r for r in out.rows if r.category != "other"]
        unmatched = list(rows)
        missed = []
        for expected in case["rows"]:
            hit = next((r for r in unmatched if matches(expected, r)), None)
            if hit:
                unmatched.remove(hit)
            else:
                missed.append(expected)
        total += len(case["rows"])
        correct += len(case["rows"]) - len(missed)
        extra += len(unmatched)
        total_ok = "written_total" not in case or to_decimal(out.written_total) == to_decimal(case["written_total"])
        status = "ok  " if not missed and not unmatched and total_ok else "FAIL"
        print(f"  {status} {case['name']}: {len(case['rows']) - len(missed)}/{len(case['rows'])} rows"
              + (f", {len(unmatched)} extra" if unmatched else "") + ("" if total_ok else ", written_total wrong"))
        for m in missed:
            print(f"        missed: {m}")
        for r in unmatched:
            print(f"        extra:  {r.model_dump(exclude_none=True)}")
    print(f"\n  rows correct: {correct}/{total} ({correct / total:.0%}), extra rows: {extra}")


if __name__ == "__main__":
    main()
