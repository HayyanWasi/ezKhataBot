"""Statement intent: a PDF of one party's khata, or of all parties.

The AI only gives the party name and the dates. The numbers come from
app/tools/statements.py (SQL + Decimal) and the PDF from app/services/pdf.py.
"""

from datetime import date
from decimal import Decimal

from app.core.database import transaction
from app.core.dates import short_date, today
from app.handlers.party import PARTY_CHOICE_HANDLERS, ask_choose_party, balance_line
from app.schemas.khata import StatementFields
from app.services import pdf
from app.services.amounts import format_rs
from app.services.registry import Context, Outcome, intent
from app.services.replies import t
from app.tools import party as party_tools
from app.tools import statements as tools


def _period(language: str, start: date | None, end: date) -> str:
    if start is None:
        return t("period_full", language)
    return f"{short_date(start)} – {short_date(end)}"


@intent(
    "statement",
    "User asks for a statement / report / PDF / khata sheet of ONE party or of ALL parties, "
    "optionally for a month or date range. For all parties use party_name null. "
    "Only for the party khata: a cash book / cash / bank report is money_report.",
    fields=StatementFields,
    fields_hint=(
        '{"party_name": string | null, "start_date": "YYYY-MM-DD" | null, "end_date": "YYYY-MM-DD" | null}  '
        '(a month -> its first and last day, e.g. "September ka" -> 2026-09-01 .. 2026-09-30; '
        "no period mentioned -> both null)"
    ),
    examples=[
        "Ali ka statement bhejo", "Ali ka September ka statement", "sab ka statement", "all parties report",
        "علی کا اسٹیٹمنٹ",
    ],
    needs_business=True,
)
def statement(ctx: Context, fields: StatementFields) -> Outcome:
    now = today(ctx.business["timezone"])
    end = min(fields.end_date or now, now)
    start = fields.start_date
    if start is not None and start > end:
        return Outcome("statement", t("future_date", ctx.language))

    if not fields.party_name:
        return _all_parties(ctx, start, end)

    with transaction() as conn:
        matches = party_tools.find_parties(conn, ctx.business["id"], fields.party_name)
    if not matches:
        return Outcome("statement", t("party_not_found", ctx.language, name=fields.party_name))
    if len(matches) > 1:
        data = {"start": start.isoformat() if start else None, "end": end.isoformat()}
        return ask_choose_party(ctx, fields.party_name, matches, "statement", data)
    return _party(ctx, matches[0], start, end)


def _party(ctx: Context, party: dict, start: date | None, end: date) -> Outcome:
    with transaction() as conn:
        data = tools.party_statement(conn, ctx.business["id"], party["id"], start, end)
    path = pdf.party_statement_pdf(ctx.business, party, data, start, end)
    reply = t("statement_ready", ctx.language, name=party["name"], period=_period(ctx.language, start, end))
    reply += "\n" + balance_line(ctx.language, party["name"], data["closing"])
    return Outcome("statement", reply, attachment=path)


def _all_parties(ctx: Context, start: date | None, end: date) -> Outcome:
    with transaction() as conn:
        parties = tools.all_parties_summary(conn, ctx.business["id"], start, end)
    if not parties:
        return Outcome("statement", t("no_parties", ctx.language))
    path = pdf.all_parties_pdf(ctx.business, parties, start, end)
    will_get = sum((p["closing"] for p in parties if p["closing"] > 0), Decimal(0))
    will_give = sum((-p["closing"] for p in parties if p["closing"] < 0), Decimal(0))
    reply = t(
        "statement_all_ready", ctx.language, period=_period(ctx.language, start, end),
        get=format_rs(will_get), give=format_rs(will_give),
    )
    return Outcome("statement", reply, attachment=path)


def _after_choice(ctx: Context, party: dict, data: dict) -> Outcome:
    start = date.fromisoformat(data["start"]) if data.get("start") else None
    return _party(ctx, party, start, date.fromisoformat(data["end"]))


PARTY_CHOICE_HANDLERS["statement"] = ("statement", _after_choice)
