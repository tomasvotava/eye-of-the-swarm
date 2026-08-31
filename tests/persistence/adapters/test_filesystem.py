import os
from pathlib import Path

import pytest

from eye.persistence.adapters.filesystem import FilesystemSaveStore


def test_load_returns_none_when_no_save_file_exists(tmp_path: Path) -> None:
    store = FilesystemSaveStore(tmp_path / "save.json")

    assert store.load() is None


def test_save_creates_the_parent_directory_when_it_does_not_exist_yet(tmp_path: Path) -> None:
    store = FilesystemSaveStore(tmp_path / "nested" / "config" / "save.json")

    store.save("some data")

    assert store.load() == "some data"


def test_save_then_load_round_trips_the_data(tmp_path: Path) -> None:
    store = FilesystemSaveStore(tmp_path / "save.json")

    store.save("some data")

    assert store.load() == "some data"


def test_save_overwrites_a_previous_save(tmp_path: Path) -> None:
    store = FilesystemSaveStore(tmp_path / "save.json")
    store.save("first")

    store.save("second")

    assert store.load() == "second"


def test_save_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    store = FilesystemSaveStore(tmp_path / "save.json")

    store.save("some data")

    assert {entry.name for entry in tmp_path.iterdir()} == {"save.json"}


def test_save_leaves_the_original_file_untouched_if_the_atomic_replace_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "save.json"
    store = FilesystemSaveStore(path)
    store.save("original")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError, match="simulated crash mid-write"):
        store.save("corrupted")

    assert path.read_text() == "original"


def test_save_leaves_no_temp_file_behind_if_the_atomic_replace_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FilesystemSaveStore(tmp_path / "save.json")

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError, match="simulated crash mid-write"):
        store.save("data")

    assert list(tmp_path.iterdir()) == []
