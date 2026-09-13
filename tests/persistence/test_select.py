import sys
import types
from pathlib import Path

import pytest

from eye.persistence.adapters.filesystem import FilesystemSaveStore
from eye.persistence.adapters.local_storage import LocalStorageSaveStore
from eye.persistence.select import default_save_store
from tests.persistence.adapters.test_local_storage import FakeJSStorage


def _install_fake_emscripten_platform(monkeypatch: pytest.MonkeyPatch, storage: FakeJSStorage) -> None:
    fake_platform = types.SimpleNamespace(window=types.SimpleNamespace(localStorage=storage))
    monkeypatch.setattr(sys, "platform", "emscripten")
    monkeypatch.setitem(sys.modules, "platform", fake_platform)


def test_returns_a_local_storage_store_under_emscripten_without_a_filesystem_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = FakeJSStorage()
    _install_fake_emscripten_platform(monkeypatch, storage)

    store = default_save_store("save-1")

    assert isinstance(store, LocalStorageSaveStore)
    store.save("some data")
    assert storage.getItem("eye-of-the-swarm-save-1") == "some data"


def test_returns_a_local_storage_store_under_emscripten_ignoring_a_supplied_filesystem_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    storage = FakeJSStorage()
    _install_fake_emscripten_platform(monkeypatch, storage)

    store = default_save_store("save-1", filesystem_path=tmp_path / "save.json")

    assert isinstance(store, LocalStorageSaveStore)
    store.save("some data")
    assert storage.getItem("eye-of-the-swarm-save-1") == "some data"
    assert not (tmp_path / "save.json").exists()


def test_returns_a_filesystem_store_outside_emscripten_when_given_a_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    path = tmp_path / "save.json"

    store = default_save_store("save-1", filesystem_path=path)

    assert isinstance(store, FilesystemSaveStore)
    store.save("some data")
    assert path.read_text() == "some data"


def test_raises_outside_emscripten_without_a_filesystem_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")

    with pytest.raises(ValueError, match="filesystem_path"):
        default_save_store("save-1")


def test_different_namespaces_get_different_emscripten_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = FakeJSStorage()
    _install_fake_emscripten_platform(monkeypatch, storage)

    default_save_store("save-1").save("slot one")
    default_save_store("settings").save("settings data")

    assert storage.getItem("eye-of-the-swarm-save-1") == "slot one"
    assert storage.getItem("eye-of-the-swarm-settings") == "settings data"
