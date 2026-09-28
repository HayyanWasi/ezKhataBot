from typing import Protocol


class Channel(Protocol):
    """Where messages come from and replies go (CLI now, WhatsApp later)."""

    name: str  # stored in conversations.channel

    def send(self, phone: str, text: str) -> str | None:
        """Deliver a text message. Returns the provider's message id. Raises on failure."""
        ...

    def send_document(self, phone: str, path: str, caption: str) -> str | None:
        """Deliver a file (PDF statement) with a caption. Returns the provider's message id."""
        ...
