"""Prompt for the message classifier. The intent list is built from the registry,
so new features only need to register their intents."""

from app.services.registry import IntentSpec

SYSTEM_PROMPT = """You classify messages for EzKhata, a WhatsApp bookkeeping assistant for small shops in Pakistan.
Users write in English, Urdu script, or Roman Urdu (Urdu written in Latin letters), often mixed.

Return ONLY one JSON object, no other text:
{{"intent": "<intent name>", "language": "en" | "ur" | "roman_ur", "answers_pending": true | false, "fields": {{...}}}}

language:
- "ur": the message is written in Urdu script, e.g. "مدد چاہیے".
- "roman_ur": Urdu written in Latin letters, even when mixed with English words, e.g. "madad chahiye", "shop switch karo", "kya haal hai".
- "en": plain English, e.g. "I need help".

Rules:
- Pick exactly one intent from the list below. If none fits, use "unknown".
- Fill fields only with what the user actually said. Never invent names, amounts or facts. Use null when something is not stated.
- Keep names and notes exactly as the user wrote them.
- answers_pending: true only when a pending question is shown and the latest message answers it.
  Then use intent "pending_answer" and fields {{"answer": "<the answer as a short value, e.g. a number or a name>"}}.
- If a pending question exists but the latest message is a new request, answers_pending is false; classify it normally.

Intents:
{intents}
"""


def _describe(spec: IntentSpec) -> str:
    lines = [f"- {spec.name}: {spec.description}"]
    lines.append(f"  fields: {spec.fields_hint or '{}'}")
    if spec.examples:
        lines.append("  examples: " + " | ".join(f'"{e}"' for e in spec.examples))
    return "\n".join(lines)


def build_system_prompt(intents: dict[str, IntentSpec]) -> str:
    return SYSTEM_PROMPT.format(intents="\n".join(_describe(s) for s in intents.values()))


def build_user_prompt(
    text: str,
    history: list[dict],
    pending_question: str | None,
    memories: list[str],
) -> str:
    parts = []
    if history:
        convo = "\n".join(f"{m['role']}: {m['text']}" for m in history)
        parts.append(f"Recent conversation (oldest first):\n{convo}")
    if memories:
        parts.append("Saved notes:\n" + "\n".join(f"- {m}" for m in memories))
    parts.append(f'Pending question from the bot: "{pending_question}"' if pending_question else "Pending question: none")
    parts.append(f"Latest user message:\n{text}")
    return "\n\n".join(parts)
