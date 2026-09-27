from typing import Protocol


class Channel(Protocol):
    """Where messages come from and replies go (CLI now, WhatsApp later)."""

    name: str  # stored in conversations.channel

    def send(self, phone: str, text: str) -> str | None:
        """Deliver a reply. Returns the provider's message id. Raises on failure."""
        ...
