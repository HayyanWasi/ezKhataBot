"""Image extractor: OCR text in, khata rows out.

The LLM sees ONLY the text read from the photo and today's date. It never sees
the database. Code checks every row (amount written in the text, direction
clear, party match) before anything is saved, and the user confirms first.
"""

from datetime import datetime

from app.ai.llm import call_structured
from app.schemas.khata import ImageExtraction

SYSTEM_PROMPT = """You read text taken (by OCR) from a photo sent by a small shop in Pakistan, or a chat message typed with
several entries, and list its bookkeeping rows.
The photo can be a khata register page, a supplier bill, a payment screenshot (JazzCash / Easypaisa / bank),
or a mixed sheet with several kinds of rows. OCR text can be messy: words split, columns mixed, Urdu and English together.

Return ONLY one JSON object:
{"kind": "register" | "bill" | "payment" | "other",
 "written_total": number | null,
 "item_amounts": [number, ...],
 "rows": [{"category": "...", "party_name": string | null, "direction": "gave" | "got" | null,
           "amount": number | null, "date": "YYYY-MM-DD" | null, "note": string | null,
           "bank_name": string | null}]}

category, for EACH row on its own:
- "party_entry": money or goods between the shop and a named customer or supplier (udhaar, payment, maal).
- "expense": a shop cost with no party account, e.g. bijli bill, kiraya, chai, salary, transport.
- "cash_in" / "cash_out": cash added to or taken out of the shop's cash box (not tied to a party).
- "bank": money moved into or out of the shop's OWN bank / JazzCash / Easypaisa account with NO other person
  named (e.g. "JazzCash mein 5000 jama karwaye"). A payment screenshot that names who sent or received the money
  is a "party_entry" with that person, even though it went through JazzCash / Easypaisa / a bank.
- "sale": a counter / cash sale with no named customer.
- "other": headings, dates alone, page totals, subtotals, phone numbers, anything that is not a row.

direction (party_entry only), always from the SHOP's side:
- "gave": the shop gave money or goods to the party (udhaar diya, diye, bech diya on credit, paid a supplier, "sent").
- "got": the shop received money or goods from the party (mile, liye, wapis kiye, jama, maal liya, "received").
- A register with two amount columns (diye / liye, gave / got, debit / credit, jama / banam, دیے / لیے) decides the
  direction by the COLUMN the amount is in. Use the LAYOUT: compare the amount's horizontal position with the
  heading positions. If the column cannot be told, use null. Never default to "gave".
- A printed shop pad / receipt / cash memo with a business name and at least one item line with an amount is a
  "bill", even if it also says things like "For Publicity only", "Name of Quality" or has adverts on it.
- A supplier bill / invoice is goods the shop GOT from that supplier: return exactly ONE row for the whole bill:
  category "party_entry", party_name = the business name printed at the top, direction "got",
  amount = the grand total (if no total is written and there is one item line, its amount). Do NOT list the
  item lines as rows. A pen stroke or tick after a number (e.g. "22572/-1") is not a digit.
- A payment screenshot is one row: "received from X" = got, "sent to X" / "paid to X" = gave.
- Owed amounts: "X se 500 lene hain" (the shop will get, X owes) = gave; "X ko 500 dene hain" (the shop must pay)
  = got. "pehle ke" / "reh gaye thay" only says the amount is old; the direction rule is the same.
- If the direction really cannot be told, use null. Never guess.

bank rows: direction "got" = money came INTO the shop's account, "gave" = money went OUT of it (null if unclear).
bank_name: the bank or wallet written for that row (JazzCash, Easypaisa, Meezan, HBL ...), else null.

Rules:
- Copy names exactly as written (keep Urdu script in Urdu script). Do not translate or correct names.
- amount: only a number that is written for that row ("5k" -> 5000, "5 hazar" -> 5000). Never add rows up, never invent.
  If a row has no readable amount, use null.
- date: use the "Today" line to complete partial dates ("12/9" or "12 Sep" -> this year). null if the row has no date.
- written_total: a grand total written on the sheet, if there is one; otherwise null. Totals are NOT rows.
- item_amounts (bills only, else []): the amount written at the end of EACH item line (the line total, not the
  rate), in order, exactly as written, including extra lines like "+40". Do not add them up.
- note: the item or reason if written (e.g. "cheeni", "bijli bill"), else null. For an expense row, note is the
  short expense word as written (e.g. "bijli", "kiraya", "chai", "salary"), without the amount.
- At most 20 rows. If the photo has no bookkeeping rows, return "rows": [].
"""


def extract_rows(
    ocr_text: str, now: datetime, layout: str | None = None, from_message: bool = False
) -> ImageExtraction:
    """`ocr_text` is in reading order; `layout` (if given) keeps each word at its position on the page.
    from_message: the text is a WhatsApp message the shopkeeper typed with several entries, not a photo."""
    heading = 'MESSAGE typed by the shopkeeper (not a photo; kind "register")' if from_message else "TEXT (reading order)"
    user = f"Today: {now:%Y-%m-%d} ({now:%A}), Pakistan time\n\n{heading}:\n{ocr_text}"
    if layout:
        user += f"\n\nLAYOUT (words placed by position, for reading table columns):\n{layout}"
    return call_structured(ImageExtraction, [("system", SYSTEM_PROMPT), ("user", user)], "extract_image_rows")
