"""Score the AI classifier on tests/ai_phrases.jsonl.

    uv run tests/eval_classifier.py                        # model from .env
    uv run tests/eval_classifier.py --model openai/gpt-oss-20b --model llama-3.3-70b-versatile

Rerun after every prompt change. Checks intent, language, answers_pending and
the listed fields (case-insensitive for strings).
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.handlers.foundation  # noqa: E402,F401  registers intents
import app.handlers.party  # noqa: E402,F401
from app.ai import classifier  # noqa: E402
from app.services.amounts import to_decimal  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.services.registry import INTENTS  # noqa: E402

PHRASES = Path(__file__).with_name("ai_phrases.jsonl")
TODAY = date(2026, 9, 28)  # fixed, so "kal" in the phrases is always 2026-09-27


def _same(expected, actual) -> bool:
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return to_decimal(actual) == to_decimal(expected)
    return expected == actual


def check(case: dict, out) -> list[str]:
    problems = []
    if out.intent != case["intent"]:
        problems.append(f"intent {out.intent!r} != {case['intent']!r}")
    if "language" in case and out.language != case["language"]:
        problems.append(f"language {out.language!r} != {case['language']!r}")
    if "answers_pending" in case and out.answers_pending != case["answers_pending"]:
        problems.append(f"answers_pending {out.answers_pending} != {case['answers_pending']}")
    for key, expected in case.get("fields", {}).items():
        if not _same(expected, out.fields.get(key)):
            problems.append(f"fields.{key} {out.fields.get(key)!r} != {expected!r}")
    return problems


def run(model: str, cases: list[dict]) -> None:
    get_settings().llm_model = model
    passed, slow = 0, 0.0
    print(f"\n=== {model} ===")
    for case in cases:
        elapsed = 0.0
        for wait in (0, 30, 60):  # free tier: wait out the per-minute limit, then retry
            time.sleep(wait)
            started = time.monotonic()
            try:
                out = classifier.classify(
                    case["text"], intents=INTENTS, history=[], pending_question=case.get("pending"),
                    memories=[], today=TODAY,
                )
                problems = check(case, out)
                elapsed = time.monotonic() - started
                break
            except classifier.AIError as e:
                problems = [f"AI error: {e}"]
                if "429" not in str(e):
                    break
        slow = max(slow, elapsed)
        if problems:
            print(f"  FAIL {case['text']!r}: " + "; ".join(problems))
        else:
            passed += 1
    print(f"  {passed}/{len(cases)} passed ({passed / len(cases):.0%}), slowest {slow:.2f}s")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", action="append", help="model id (repeatable); default from .env")
    args = parser.parse_args()
    cases = [json.loads(line) for line in PHRASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    for model in args.model or [get_settings().llm_model]:
        run(model, cases)


if __name__ == "__main__":
    main()
