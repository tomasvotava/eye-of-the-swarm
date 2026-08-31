from eye.persistence.adapters.local_storage import LocalStorageSaveStore


class FakeJSStorage:
    def __init__(self) -> None:
        self._items: dict[str, str] = {}

    def getItem(self, key: str) -> str | None:  # noqa: N802 -- matches the Web Storage API this mirrors
        return self._items.get(key)

    def setItem(self, key: str, value: str) -> None:  # noqa: N802 -- matches the Web Storage API this mirrors
        self._items[key] = value


def test_load_returns_none_when_no_save_exists() -> None:
    store = LocalStorageSaveStore(FakeJSStorage(), key="eye-of-the-swarm-save")

    assert store.load() is None


def test_save_then_load_round_trips_the_data() -> None:
    store = LocalStorageSaveStore(FakeJSStorage(), key="eye-of-the-swarm-save")

    store.save("some data")

    assert store.load() == "some data"


def test_save_overwrites_a_previous_save() -> None:
    store = LocalStorageSaveStore(FakeJSStorage(), key="eye-of-the-swarm-save")
    store.save("first")

    store.save("second")

    assert store.load() == "second"


def test_load_and_save_scope_to_the_configured_key() -> None:
    storage = FakeJSStorage()
    storage.setItem("some-other-key", "other data")
    store = LocalStorageSaveStore(storage, key="eye-of-the-swarm-save")

    assert store.load() is None
    store.save("this game's data")

    assert storage.getItem("some-other-key") == "other data"
    assert storage.getItem("eye-of-the-swarm-save") == "this game's data"
