import uuid


class CLIChannel:
    name = "cli"

    def __init__(self) -> None:
        self.fail_next_send = False  # dev: simulate a network failure on the next send

    def _check_failure(self) -> None:
        if self.fail_next_send:
            self.fail_next_send = False
            raise ConnectionError("simulated send failure")

    def send(self, phone: str, text: str) -> str:
        self._check_failure()
        print(f"\nEzKhata> {text}\n")
        return f"cli-{uuid.uuid4().hex[:12]}"

    def send_document(self, phone: str, path: str, caption: str) -> str:
        self._check_failure()
        print(f"\nEzKhata> {caption}\n         📎 {path}\n")
        return f"cli-{uuid.uuid4().hex[:12]}"
