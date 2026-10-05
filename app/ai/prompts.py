"""Prompt for the message classifier. The intent list is built from the registry,
so new features only need to register their intents.

The AI only sees the message, recent chat and saved notes. It never sees the
database, SQL, ids or balances; it only picks an intent and fills its fields."""

from datetime import datetime

from app.services.registry import IntentSpec

SYSTEM_PROMPT = """You classify messages for EzKhata, a WhatsApp bookkeeping assistant for small shops in Pakistan.
Users write in English, Urdu script, or Roman Urdu (Urdu written in Latin letters), often mixed.

Return ONLY one JSON object, no other text:
{{"intent": "<intent name>", "language": "en" | "ur" | "roman_ur", "answers_pending": true | false, "fields": {{...}},
 "then": [{{"intent": "<intent name>", "fields": {{...}}}}]}}

language: "ur" = Urdu script ("مدد چاہیے"); "roman_ur" = Urdu in Latin letters, even mixed with English
("madad chahiye", "shop switch karo"); "en" = plain English.

Rules:
- Pick exactly one intent from the list below. If none fits, use "unknown".
- Fill fields only with what the user actually said. Never invent names, amounts or facts. Every field is null
  when it is not stated (the field lists below leave "| null" out). str = string, num = number,
  date = "YYYY-MM-DD", bool = true | false.
- Keep names and notes exactly as the user wrote them.
- answers_pending: true only when the latest message answers the pending question; then intent "pending_answer",
  fields {{"answer": "<short value, e.g. a number or a name>"}}. A message naming a different person or complete
  on its own ("Bilal ko 300 diye") is a new request: answers_pending false, classify it normally.
- "then": when ONE message asks for 2 or 3 actions: the first in intent/fields, the rest in "then", in order.
  "washing machine add karo 3, Sameer ne 1 udhaar li 35000 ki" -> add_item, then create_bill (Sameer, udhaar).
  "ali ka khata aur ahmed ka bhi" -> party_balance Ali, then party_balance Ahmed. "Ali ko 300 diye aur kal yaad
  dila dena" -> party_entry, then set_reminder. Only money entries ("Ali ko 500 diye, chai 50") are ONE
  many_entries instead. Never leave out a part. Otherwise "then" is [].
- Goods written with a COUNT or weight ("2 packet surf", "50 socks", "4 darjan ande") are never party_entry or
  cash_entry: sold / "bech diye" / a customer took them -> create_bill; came in / bought -> stock_in;
  damaged, given free, returned -> stock_out.
- Amounts: only numbers the user actually wrote. Convert "5 hazar" -> 5000, "5k" -> 5000, "1.5 lakh" -> 150000,
  "paanch sau" -> 500, "dhai hazar" -> 2500.
  Never add, subtract or guess amounts. null if no amount is written.
- Dates: use the "Today" line to turn words like "kal", "parson", "15 tareekh" into YYYY-MM-DD.
  For entries, corrections of entries and reports "kal" means yesterday and "parso" the day before (past:
  diye, liye, hua, tha); only for reminders "kal" means tomorrow.
  null when no day is mentioned.
  A month ("September ka") means its first and last day.
- Times: 24h "HH:MM". Vague times: subah = 09:00, dopahar = 13:00, shaam = 18:00, raat = 21:00.
  "1 baje" to "7 baje" without subah / am are PM: "5 baje" -> 17:00.
  "2 minute baad" / "1 ghante baad" -> today's date and the exact time from the Today line.
- If the pending question asks WHEN (e.g. "Kab yaad dilaun?"), answer as "YYYY-MM-DD HH:MM", or "YYYY-MM-DD"
  when only a day is given, or "HH:MM" when only a time is given.

Intents:
{intents}
"""


def _compact(hint: str) -> str:
    """The fields' JSON shape, shorter: "| null" is said once in the rules, dates and booleans by name."""
    hint = hint.replace(" | null", "").replace('"YYYY-MM-DD"', "date").replace("true | false", "bool")
    return hint.replace(": string", ": str").replace(": number", ": num")


def _describe(spec: IntentSpec) -> str:
    lines = [f"- {spec.name}: {spec.description}"]
    lines.append(f"  fields: {_compact(spec.fields_hint) or '{}'}")
    if spec.examples:
        lines.append("  examples: " + " | ".join(f'"{e}"' for e in spec.examples))
    return "\n".join(lines)


def build_system_prompt(intents: dict[str, IntentSpec]) -> str:
    return SYSTEM_PROMPT.format(intents="\n".join(_describe(s) for s in intents.values()))


def _short(text: str, limit: int = 300) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def build_user_prompt(
    text: str,
    history: list[dict],
    pending_question: str | None,
    memories: list[str],
    now: datetime,
) -> str:
    parts = [f"Today: {now:%Y-%m-%d} ({now:%A}), time now {now:%H:%M}, Pakistan time"]
    if history:
        # Long replies (bills, reports) are cut: the AI only needs the gist, and Groq counts every token
        convo = "\n".join(f"{m['role']}: {_short(m['text'])}" for m in history)
        parts.append(f"Recent conversation (oldest first):\n{convo}")
    if memories:
        parts.append("Saved notes:\n" + "\n".join(f"- {m}" for m in memories))
    parts.append(f'Pending question from the bot: "{pending_question}"' if pending_question else "Pending question: none")
    parts.append(f"Latest user message:\n{text}")
    return "\n\n".join(parts)
