class FakeSaveStore:
    def __init__(self, data: str | None = None) -> None:
        self._data = data

    def load(self) -> str | None:
        return self._data

    def save(self, data: str) -> None:
        self._data = data
