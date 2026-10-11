"""Live classifier QA matrix; writes a resumable, reviewable result file.

Examples:
  .venv/Scripts/python tests/run_live_roman_urdu_matrix.py --start 1 --end 15 --pause 18
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LLM_PROVIDERS"] = "groq"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.ai.agent  # noqa: F401,E402: registers intents
from app.ai import classifier  # noqa: E402
from app.services.amounts import to_decimal  # noqa: E402
from app.services.registry import INTENTS  # noqa: E402

CASES_PATH = Path(__file__).with_name("roman_urdu_live_matrix.jsonl")
OUT = Path(__file__).with_name("roman_urdu_live_matrix_results.json")
NOW = datetime(2026, 10, 5, 12, 0, tzinfo=ZoneInfo("Asia/Karachi"))


def same(expected, actual):
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return to_decimal(actual) == to_decimal(expected)
    return expected == actual


def score(case, actual):
    allowed = case.get("expected_intents", [case["intent"]])
    if actual["error"]:
        return "FAIL", "Critical", ["Live AI classifier error: " + actual["error"]]
    issues = []
    if actual["intent"] not in allowed:
        issues.append(f"intent {actual['intent']!r}; expected one of {allowed!r}")
    if actual["language"] != "roman_ur":
        issues.append(f"language {actual['language']!r}; expected 'roman_ur'")
    if case.get("intent") == "pending_answer" and not actual["answers_pending"]:
        issues.append("pending answer was not marked as an answer")
    for name, expected in case.get("fields", {}).items():
        if not same(expected, actual["fields"].get(name)):
            issues.append(f"fields.{name} {actual['fields'].get(name)!r}; expected {expected!r}")
    if not issues:
        return "PASS", "None", []
    if actual["intent"] in allowed:
        return "PARTIAL", "Medium", issues
    return "FAIL", "High", issues


def run_case(case):
    actual = {"intent": None, "language": None, "answers_pending": None, "fields": {}, "then": [], "error": None}
    started = time.monotonic()
    try:
        out = classifier.classify(
            case["text"], intents=INTENTS, history=[], pending_question=case.get("pending"), memories=[], now=NOW
        )
        actual.update(out.model_dump())
    except classifier.AIError as exc:
        actual["error"] = str(exc)
    actual["elapsed_seconds"] = round(time.monotonic() - started, 2)
    status, severity, issues = score(case, actual)
    return {
        "test_id": case["id"], "feature": case["feature"], "style": case["style"],
        "user_message": case["text"], "expected_intent": case.get("expected_intents", [case["intent"]]),
        "expected_entities": case.get("fields", {}), "expected_behavior": case["expected_behavior"],
        "actual_classifier_response": actual, "intent_understood": actual["intent"] in case.get("expected_intents", [case["intent"]]),
        "entities_extracted_correctly": not any(x.startswith("fields.") for x in issues),
        "status": status, "severity": severity, "failure_explanation": "; ".join(issues) or None,
        "suggested_fix": None if not issues else "Add this labelled Roman Urdu phrasing to evaluation examples and tune routing/extraction.",
    }


def save(cases, results):
    counts = {name: sum(r["status"] == name for r in results) for name in ("PASS", "PARTIAL", "FAIL")}
    OUT.write_text(json.dumps({"run_at": NOW.isoformat(), "case_count": len(cases), "summary": counts,
                               "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1, help="1-based test ID position")
    parser.add_argument("--end", type=int, help="inclusive test ID position")
    parser.add_argument("--pause", type=float, default=18, help="seconds between live calls")
    parser.add_argument("--resume", action="store_true", help="keep prior results before --start")
    parser.add_argument("--cases", help="comma-separated 1-based positions; overrides --start/--end")
    args = parser.parse_args()
    cases = [json.loads(line) for line in CASES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    end = args.end or len(cases)
    if not 1 <= args.start <= end <= len(cases):
        raise SystemExit(f"Use 1 <= start <= end <= {len(cases)}")
    positions = ([int(x) for x in args.cases.split(",")] if args.cases else list(range(args.start, end + 1)))
    if not positions or any(p < 1 or p > len(cases) for p in positions):
        raise SystemExit(f"--cases positions must be between 1 and {len(cases)}")
    results = []
    if args.resume and OUT.exists():
        prior = json.loads(OUT.read_text(encoding="utf-8")).get("results", [])
        selected_ids = {cases[p - 1]["id"] for p in positions}
        results = [r for r in prior if r["test_id"] not in selected_ids]
    try:
        for sequence, position in enumerate(positions, 1):
            index = position - 1
            result = run_case(cases[index])
            results.append(result)
            save(cases, results)
            print(f"{sequence}/{len(positions)} {result['status']} {result['test_id']} {result['actual_classifier_response']['intent']}", flush=True)
            if sequence < len(positions):
                time.sleep(args.pause)
    finally:
        save(cases, results)


if __name__ == "__main__":
    main()
