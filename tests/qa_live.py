"""Live end-to-end QA harness: real pipeline (rules + LLM classifier + handlers + Supabase), CLI-style capture
channel, synthetic phones only (no WhatsApp message is ever sent).

Every step records the user message, the classifier output, the saved intent, the reply, pending state before and
after, DB write counts, and whether the LLM backend failed (so infra errors are never scored as language failures).
"""

import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path

os.environ["LANGSMITH_TRACING"] = "false"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

import app.ai.agent as agent  # noqa: E402
from app.ai.classifier import AIError  # noqa: E402
from app.core.database import transaction  # noqa: E402
from app.db import crud  # noqa: E402
from app.services.handler import handle_message  # noqa: E402

LAST = {"cls": None, "ai_error": None, "calls": []}
_orig_classify = agent.classify


def _spy(*a, **k):
    LAST["cls"] = None
    try:
        out = _orig_classify(*a, **k)
    except AIError as e:
        LAST["ai_error"] = str(e)[:200]
        raise
    LAST["cls"] = out.model_dump()
    return out


agent.classify = _spy


class _LogCatch(logging.Handler):
    def emit(self, rec):
        LAST["calls"].append(rec.getMessage()[:160])


logging.getLogger("ezkhata.ai").addHandler(_LogCatch())
logging.getLogger("ezkhata.ai").setLevel(logging.INFO)


class Chan:
    name = "cli"

    def __init__(self):
        self.sent = []

    def send(self, phone, text):
        self.sent.append(text)
        return "qa-" + uuid.uuid4().hex[:12]

    def send_document(self, phone, path, caption):
        self.sent.append(f"{caption} [document]")
        return "qa-" + uuid.uuid4().hex[:12]


COUNT_SQL = {
    "txn": "select count(*) n from public.business_transactions where business_id=%s and deleted_at is null",
    "accounts": "select count(*) n from public.accounts where business_id=%s and deleted_at is null",
    "items": "select count(*) n from public.items where business_id=%s and deleted_at is null",
    "moves": "select count(*) n from public.stock_moves where business_id=%s",
    "bills": "select count(*) n from public.bills where business_id=%s",
    "emps": "select count(*) n from public.business_employees where business_id=%s",
    "reminders": "select count(*) n from public.reminders where business_id=%s",
}


class Session:
    def __init__(self, phone, shop, results, pause=2.5):
        self.phone, self.shop, self.results, self.pause = phone, shop, results, pause
        self.chan = Chan()
        with transaction() as conn:
            user = crud.get_user_by_phone(conn, phone)
            if user is None:
                user = crud.create_user(conn, phone, "QA " + phone[-3:])
                crud.create_business(conn, user["id"], shop)
            self.user_id = user["id"]
            self.biz = crud.list_user_businesses(conn, user["id"])[0]["id"]

    def counts(self):
        out = {}
        for k, sql in COUNT_SQL.items():
            try:
                with transaction() as conn:
                    out[k] = conn.execute(sql, (self.biz,)).fetchone()["n"]
            except Exception as e:  # table without that column: ignore
                out[k] = None
        return out

    def pending_kind(self):
        with transaction() as conn:
            c = crud.get_or_create_conversation(conn, self.user_id, "cli")
            return (c["pending_action"] or {}).get("kind")

    def say(self, text, tid=None, feature="", style="", exp=None, retries=2, quiet=False):
        exp = exp or {}
        before, pend_before = self.counts(), self.pending_kind()
        attempt = 0
        while True:
            LAST.update(cls=None, ai_error=None, calls=[])
            ext = "qa-" + uuid.uuid4().hex
            n0 = len(self.chan.sent)
            handle_message(self.chan, ext, self.phone, text)
            if LAST["ai_error"] and attempt < retries:  # backend failure: wait and retry the SAME message
                attempt += 1
                time.sleep(25)
                continue
            break
        with transaction() as conn:
            row = conn.execute(
                "select u.intent, u.processing_status, b.text reply from public.messages u "
                "join public.conversations c on c.id=u.conversation_id "
                "left join public.messages b on b.reply_to_id=u.id "
                "where u.external_id=%s and c.user_id=%s",
                (ext, self.user_id),
            ).fetchone()
        after, pend_after = self.counts(), self.pending_kind()
        delta = {k: (after[k] or 0) - (before[k] or 0) for k in after if after[k] is not None}
        delta = {k: v for k, v in delta.items() if v}
        rec = {
            "id": tid, "feature": feature, "style": style, "text": text, "session": self.phone[-3:],
            "intent": row["intent"] if row else None, "reply": (row["reply"] if row else None),
            "cls": LAST["cls"], "ai_error": LAST["ai_error"], "retries": attempt,
            "pend_before": pend_before, "pend_after": pend_after, "delta": delta, "exp": exp,
        }
        rec["verdict"], rec["why"] = grade(rec)
        if tid:
            self.results.append(rec)
        if not quiet:
            print(f"[{tid}] {rec['verdict']:7} {text!r} -> {rec['intent']} pend={pend_after} d={delta}", flush=True)
            print("      " + (rec["reply"] or "").replace("\n", "\n      ")[:400], flush=True)
        time.sleep(self.pause)
        return rec

    def settle(self):
        if self.pending_kind():
            self.say("/cancel", quiet=True)


def grade(r):
    """Automatic first-pass verdict from machine checks; manual review refines it."""
    e = r["exp"]
    why = []
    if r["ai_error"]:
        return "BACKEND", "LLM backend failed after retries: " + r["ai_error"]
    if e.get("i") and r["intent"] not in e["i"]:
        why.append(f"intent {r['intent']!r} not in {e['i']}")
    w = e.get("w")
    wrote = bool(r["delta"]) and any(v > 0 for v in r["delta"].values())
    if w == "none" and wrote:
        why.append(f"UNSAFE write {r['delta']}")
    if w == "some" and not wrote:
        why.append("expected a record to be saved/changed, none was")
    p = e.get("p")
    if p is True and not r["pend_after"]:
        why.append("expected the bot to ask a follow-up question (pending), none")
    if p is False and r["pend_after"]:
        why.append(f"unexpected pending {r['pend_after']}")
    rep = r["reply"] or ""
    if e.get("rx") and not re.search(e["rx"], rep, re.I | re.S):
        why.append(f"reply missing /{e['rx']}/")
    if e.get("nx") and re.search(e["nx"], rep, re.I | re.S):
        why.append(f"reply contains forbidden /{e['nx']}/")
    if not why:
        return "PASS", ""
    unsafe = any(x.startswith("UNSAFE") for x in why)
    return ("UNSAFE" if unsafe else "FAIL"), "; ".join(why)


def save(results, path):
    Path(path).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
