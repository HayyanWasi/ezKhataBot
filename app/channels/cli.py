import uuid


class CLIChannel:
    name = "cli"

    def __init__(self) -> None:
        self.fail_next_send = False  # dev: simulate a network failure on the next send

    def send(self, phone: str, text: str) -> str:
        if self.fail_next_send:
            self.fail_next_send = False
            raise ConnectionError("simulated send failure")
        print(f"\nEzKhata> {text}\n")
        return f"cli-{uuid.uuid4().hex[:12]}"
