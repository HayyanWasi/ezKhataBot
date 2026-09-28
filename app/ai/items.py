"""Which stock item does a word mean? ("jurab" -> "Socks", "cheeni" -> "Sugar")

Used only when code finds no match. The LLM sees the word and the shop's item
NAMES (nothing else from the database) and returns one of those names or null.
Code checks the answer is really in the list, and the user always confirms
("Jurab = Socks? haan/nahi") before anything is saved or remembered.
"""

from pydantic import BaseModel, field_validator

from app.ai.llm import AIError, call_structured

SYSTEM_PROMPT = """A shopkeeper in Pakistan wrote a word for an item in their stock. It can be Urdu, Roman Urdu,
English, a short form or a misspelling. Pick the ONE item from the list that means the same thing
(e.g. "jurab" = "Socks", "cheeni" = "Sugar", "anday" = "Eggs", "sabun" = "Soap").
If none of them clearly means the same thing, answer null. Never pick a merely similar item
(a different product, size or brand is NOT the same).

Return ONLY JSON: {"name": "<exactly one name from the list>" | null}"""


class _Guess(BaseModel):
    name: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _blank(cls, v):
        return v.strip() or None if isinstance(v, str) else None


def guess_item(word: str, names: list[str]) -> str | None:
    """One of `names`, or None (also when the AI is unavailable)."""
    if not names:
        return None
    listing = "\n".join(f"- {name}" for name in names[:200])
    try:
        result = call_structured(
            _Guess, [("system", SYSTEM_PROMPT), ("user", f"Word: {word}\nItems:\n{listing}")], "item_guess",
            max_tokens=400,
        )
    except AIError:
        return None
    by_lower = {name.lower(): name for name in names}
    return by_lower.get((result.name or "").lower())
