import itertools
import random
from collections.abc import Iterator

import pytest
from rich.console import Console

from eye.exploration.encounters import EncounterKind
from eye.persistence.codec import decode
from eye.skilltree.catalog import CATALOG
from eye.tui import app
from tests.session.doubles import ScriptedEncounterRandom

_COMBAT_INPUT_BUDGET = 100


class _FakeSaveStore:
    def __init__(self, data: str | None = None) -> None:
        self._data = data

    def load(self) -> str | None:
        return self._data

    def save(self, data: str) -> None:
        self._data = data


class _RaisingInput:
    def __iter__(self) -> Iterator[str]:
        return self

    def __next__(self) -> str:
        raise KeyboardInterrupt


def test_run_plays_a_generation_to_death_reaches_the_skilltree_menu_and_persists(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rng = ScriptedEncounterRandom([EncounterKind.ENEMY] * 10)
    input_source = itertools.chain(itertools.repeat("1", _COMBAT_INPUT_BUDGET), ["done", "n"])
    store = _FakeSaveStore()

    app.run(Console(), input_source, rng, save_store=store)

    output = capsys.readouterr().out
    assert "Generation ended" in output
    assert "Enter a node number to purchase" in output
    assert "Play another generation?" in output

    saved = store.load()
    assert saved is not None
    snapshot = decode(saved, CATALOG.values())
    assert snapshot.purchased_nodes


def test_run_catches_keyboard_interrupt_and_prints_a_notice(capsys: pytest.CaptureFixture[str]) -> None:
    store = _FakeSaveStore()

    app.run(Console(), _RaisingInput(), random.Random(), save_store=store)

    assert "not saved" in capsys.readouterr().out
    assert store.load() is None
