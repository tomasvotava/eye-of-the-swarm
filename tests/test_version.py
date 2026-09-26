import sys
import types

import pytest

from eye.version import game_version


def test_reports_the_stamped_version(monkeypatch: pytest.MonkeyPatch) -> None:
    stamped = types.ModuleType("eye._version")
    stamped.VERSION = "1.2.3"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "eye._version", stamped)

    assert game_version() == "1.2.3"


def test_reports_none_when_unstamped(monkeypatch: pytest.MonkeyPatch) -> None:
    # A `None` entry makes the import raise ImportError whether or not a stamped file is on disk.
    monkeypatch.setitem(sys.modules, "eye._version", None)

    assert game_version() is None
