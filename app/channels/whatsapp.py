from app.services import evolution


class WhatsAppChannel:
    name = "whatsapp"

    def send(self, phone: str, text: str) -> str | None:
        return evolution.send_text(phone, text)

    def send_document(self, phone: str, path: str, caption: str) -> str | None:
        return evolution.send_file(phone, path, caption)
