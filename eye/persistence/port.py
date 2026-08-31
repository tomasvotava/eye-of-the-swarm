from typing import Protocol


class SaveStore(Protocol):
    def load(self) -> str | None: ...  # None = no save yet
    def save(self, data: str) -> None: ...
