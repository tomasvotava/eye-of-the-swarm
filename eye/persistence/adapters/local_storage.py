from typing import Protocol


class JSStorage(Protocol):
    def getItem(self, key: str) -> str | None: ...  # noqa: N802 -- matches the Web Storage API this mirrors
    def setItem(self, key: str, value: str) -> None: ...  # noqa: N802 -- matches the Web Storage API this mirrors


class LocalStorageSaveStore:
    def __init__(self, storage: JSStorage, key: str) -> None:
        self._storage = storage
        self._key = key

    def load(self) -> str | None:
        return self._storage.getItem(self._key)

    def save(self, data: str) -> None:
        self._storage.setItem(self._key, data)
