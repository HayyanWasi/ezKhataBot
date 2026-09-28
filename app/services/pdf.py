"""PDF statements (English sheet, A4), built with fpdf2.

The numbers come from app/tools/statements.py; this file only lays them out.
Noto Naskh Arabic is a fallback font, so a name typed in Urdu script still renders.
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fpdf import FPDF
from fpdf.fonts import FontFace

from app.core.config import get_settings
from app.services.amounts import format_rs

FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"
HEADER_FILL = (234, 88, 12)  # orange, like DigiKhata
HEADER_TEXT = (255, 255, 255)
ZEBRA = (248, 244, 240)
GREEN, RED, GREY = (22, 128, 61), (185, 28, 28), (90, 90, 90)


class _Sheet(FPDF):
    def __init__(self, title: str) -> None:
        super().__init__(format="A4")
        self.sheet_title = title
        self.add_font("Noto", "", str(FONTS / "NotoSans-Regular.ttf"))
        self.add_font("Noto", "B", str(FONTS / "NotoSans-Bold.ttf"))
        self.add_font("Naskh", "", str(FONTS / "NotoNaskhArabic-Regular.ttf"))
        self.set_fallback_fonts(["Naskh"])
        self.set_text_shaping(True)
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(14, 14, 14)
        self.add_page()

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Noto", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 6, f"EzKhata  ·  {self.sheet_title}  ·  Page {self.page_no()}/{{nb}}", align="C")


def _money(value: Decimal) -> str:
    """1,200 (no 'Rs' inside the table), empty for zero."""
    return format_rs(value).removeprefix("Rs ") if value else ""


def _signed(value: Decimal) -> str:
    """Balance cell: '1,200 get' (party owes you), '1,200 give' (you owe), '0'."""
    if value > 0:
        return f"{_money(value)} get"
    if value < 0:
        return f"{_money(value)} give"
    return "0"


def _balance_text(value: Decimal) -> str:
    if value > 0:
        return f"{format_rs(value)}  (you will get)"
    if value < 0:
        return f"{format_rs(value)}  (you will give)"
    return "Settled"


def _period(start: date | None, end: date) -> str:
    if start is None:
        return f"Full khata (till {end:%d %b %Y})"
    return f"{start:%d %b %Y} – {end:%d %b %Y}"


def _header(pdf: _Sheet, shop: str, title: str, lines: list[str]) -> None:
    pdf.set_font("Noto", "B", 16)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 9, shop, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "B", 12)
    pdf.set_text_color(*HEADER_FILL)
    pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Noto", "", 9.5)
    pdf.set_text_color(*GREY)
    for line in lines:
        pdf.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def _summary(pdf: _Sheet, items: list[tuple[str, str, tuple[int, int, int]]]) -> None:
    """A row of boxes: label on top, value below."""
    width = (pdf.epw - 3 * (len(items) - 1)) / len(items)
    x, y = pdf.l_margin, pdf.get_y()
    for label, value, color in items:
        pdf.set_draw_color(220, 220, 220)
        pdf.rect(x, y, width, 16)
        pdf.set_xy(x + 2, y + 2)
        pdf.set_font("Noto", "", 8)
        pdf.set_text_color(*GREY)
        pdf.cell(width - 4, 4.5, label)
        pdf.set_xy(x + 2, y + 7.5)
        pdf.set_font("Noto", "B", 10.5)
        pdf.set_text_color(*color)
        pdf.cell(width - 4, 6, value)
        x += width + 3
    pdf.set_xy(pdf.l_margin, y + 20)
    pdf.set_text_color(0, 0, 0)


def _table(pdf: _Sheet, headings: list[str], widths: tuple, align: tuple, rows: list[list[str]], bold_last=False):
    pdf.set_font("Noto", "", 9)
    heading_style = FontFace(emphasis="BOLD", color=HEADER_TEXT, fill_color=HEADER_FILL)
    with pdf.table(
        col_widths=widths,
        text_align=align,
        headings_style=heading_style,
        cell_fill_color=ZEBRA,
        cell_fill_mode="ROWS",
        line_height=6.5,
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        header = table.row()
        for h in headings:
            header.cell(h)
        for i, values in enumerate(rows):
            style = FontFace(emphasis="BOLD") if bold_last and i == len(rows) - 1 else None
            row = table.row(style=style)
            for v in values:
                row.cell(v)


def _save(pdf: _Sheet, business_id, slug: str, start: date | None, end: date) -> str:
    folder = get_settings().storage_dir / "statements" / str(business_id)
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9]+", "-", slug).strip("-").lower() or "party"
    name = f"{safe}_{start.isoformat() if start else 'all'}_{end.isoformat()}_{uuid.uuid4().hex[:6]}.pdf"
    path = folder / name
    pdf.output(str(path))
    return str(path)


def _generated() -> str:
    return f"Generated {datetime.now():%d %b %Y, %I:%M %p}"


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


def party_statement_pdf(business: dict, party: dict, data: dict, start: date | None, end: date) -> str:
    """One party's statement. Returns the file path."""
    pdf = _Sheet("Party Statement")
    details = [f"{party['name']}  ·  {party['type'].title()}" + (f"  ·  +{party['phone']}" if party.get("phone") else "")]
    _header(pdf, business["name"], "Party Statement", details + [_period(start, end), _generated()])

    _summary(pdf, [
        ("Opening balance", format_rs(data["opening"]), GREY),
        ("You gave", format_rs(data["total_gave"]), GREEN),
        ("You got", format_rs(data["total_got"]), RED),
        ("Closing balance", _balance_text(data["closing"]).replace("  (", " ("), (0, 0, 0)),
    ])

    rows = []
    if start is not None:
        rows.append([f"{start:%d %b %Y}", "Opening balance", "", "", _signed(data["opening"])])
    for r in data["rows"]:
        label = {"gave": "Gave", "got": "Got", "opening_balance": "Opening balance"}[r["transaction_type"]]
        details = f"{label} — {r['notes']}" if r["notes"] else label
        gave = r["amount"] if r["amount"] > 0 else Decimal(0)
        got = -r["amount"] if r["amount"] < 0 else Decimal(0)
        rows.append([f"{r['transaction_date']:%d %b %Y}", details, _money(gave), _money(got), _signed(r["balance"])])
    rows.append(["", "Total", _money(data["total_gave"]) or "0", _money(data["total_got"]) or "0",
                 _signed(data["closing"])])

    _table(
        pdf,
        ["Date", "Details", "You gave", "You got", "Balance"],
        (26, 72, 28, 28, 28),
        ("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"),
        rows,
        bold_last=True,
    )
    pdf.ln(3)
    pdf.set_font("Noto", "", 8.5)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 5, "get = the party owes you  ·  give = you owe the party")
    return _save(pdf, business["id"], party["name"], start, end)


_CASH_LABELS = {
    "cash_in": "Cash in", "cash_out": "Cash out", "sale": "Sale", "transfer": "Transfer",
    "opening_balance": "Opening balance", "adjustment": "Adjustment", "gave": "Paid", "got": "Received",
}


def _plain(value: Decimal) -> str:
    """Cash/bank balance cell: '1,200', '-300', '0'."""
    return f"-{_money(value)}" if value < 0 else (_money(value) or "0")


def cash_book_pdf(business: dict, account: dict, summary: dict, rows: list[dict], start: date, end: date) -> str:
    """Cash (or one bank) for a period: opening, every entry, in / out, closing. Returns the file path."""
    title = "Cash Book" if account["type"] == "cash" else f"{account['name']} Book"
    pdf = _Sheet(title)
    _header(pdf, business["name"], title, [_period(start, end), _generated()])

    _summary(pdf, [
        ("Opening", _plain(summary["opening"]), GREY),
        ("Money in", format_rs(summary["money_in"]), GREEN),
        ("Money out", format_rs(summary["money_out"]), RED),
        ("Closing", _plain(summary["closing"]), (0, 0, 0)),
    ])

    table = [[f"{start:%d %b %Y}", "Opening balance", "", "", _plain(summary["opening"])]]
    for r in rows:
        if r["transaction_type"] == "opening_balance" and r["transaction_date"] >= start:
            continue  # already counted in the opening row
        name = r["category"] or r["other"]
        note = r["notes"] if r["notes"] and r["notes"].lower() != (name or "").lower() else None
        detail = " — ".join(x for x in (_CASH_LABELS.get(r["transaction_type"], ""), name, note) if x)
        money_in = r["amount"] if r["amount"] > 0 else Decimal(0)
        money_out = -r["amount"] if r["amount"] < 0 else Decimal(0)
        table.append([f"{r['transaction_date']:%d %b %Y}", detail, _money(money_in), _money(money_out),
                      _plain(r["balance"])])
    table.append(["", "Total", _money(summary["money_in"]) or "0", _money(summary["money_out"]) or "0",
                  _plain(summary["closing"])])
    _table(
        pdf,
        ["Date", "Details", "In", "Out", "Balance"],
        (26, 72, 28, 28, 28),
        ("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT"),
        table,
        bold_last=True,
    )

    if summary["categories"]:
        pdf.ln(4)
        pdf.set_font("Noto", "B", 10)
        pdf.cell(0, 6, "Expenses by category", new_x="LMARGIN", new_y="NEXT")
        _table(
            pdf,
            ["Category", "Total"],
            (130, 52),
            ("LEFT", "RIGHT"),
            [[c["name"], _money(c["total"])] for c in summary["categories"]],
        )
    return _save(pdf, business["id"], title, start, end)


def all_parties_pdf(business: dict, parties: list[dict], start: date | None, end: date) -> str:
    """Every party with opening, gave, got, closing. Returns the file path."""
    pdf = _Sheet("All Parties")
    _header(pdf, business["name"], "All Parties Statement", [_period(start, end), _generated()])

    will_get = sum((p["closing"] for p in parties if p["closing"] > 0), Decimal(0))
    will_give = sum((-p["closing"] for p in parties if p["closing"] < 0), Decimal(0))
    _summary(pdf, [
        ("Parties", str(len(parties)), (0, 0, 0)),
        ("You will get", format_rs(will_get), GREEN),
        ("You will give", format_rs(will_give), RED),
    ])

    rows = [
        [p["name"], p["type"].title(), _signed(p["opening"]), _money(p["gave"]), _money(p["got"]),
         _signed(p["closing"])]
        for p in parties
    ]
    rows.append(["Total", "", "", _money(sum((p["gave"] for p in parties), Decimal(0))) or "0",
                 _money(sum((p["got"] for p in parties), Decimal(0))) or "0",
                 f"get {_money(will_get) or 0} / give {_money(will_give) or 0}"])
    _table(
        pdf,
        ["Party", "Type", "Opening", "You gave", "You got", "Closing"],
        (48, 22, 26, 26, 26, 34),
        ("LEFT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"),
        rows,
        bold_last=True,
    )
    return _save(pdf, business["id"], "all-parties", start, end)
