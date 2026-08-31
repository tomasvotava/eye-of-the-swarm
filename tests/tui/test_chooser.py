import io
from collections.abc import Iterator

import pytest
from rich.console import Console

from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.stats import Combatant, Stats
from eye.tui.chooser import TUIActionChooser

_STATS = Stats(max_hp=20, attack=5, defense=2, meter_capacity=10, meter_fill_rate=1)
_ACTIONS = (
    ActionDefinition(kind=ActionKind.STRUGGLE, name="Struggle"),
    ActionDefinition(kind=ActionKind.SWARM_ATTACK, name="Swarm Attack", requires_full_meter=True),
)


def _chooser(inputs: Iterator[str]) -> tuple[TUIActionChooser, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, width=120)
    return TUIActionChooser(console, inputs), buffer


def _combatant(name: str) -> Combatant:
    return Combatant(name=name, base_stats=_STATS, current_hp=20)


def test_choose_returns_the_action_matching_a_valid_numbered_choice() -> None:
    chooser, _ = _chooser(iter(["2"]))

    chosen = chooser.choose(_combatant("Player"), _combatant("Bramble"), _ACTIONS)

    assert chosen is _ACTIONS[1]


def test_choose_renders_both_combatants_hp_and_the_action_menu() -> None:
    chooser, buffer = _chooser(iter(["1"]))

    chooser.choose(_combatant("Player"), _combatant("Bramble"), _ACTIONS)

    output = buffer.getvalue()
    assert "Player" in output
    assert "Bramble" in output
    assert "20/20" in output
    assert "Struggle" in output
    assert "Swarm Attack" in output


def test_choose_reprompts_on_out_of_range_choice() -> None:
    chooser, buffer = _chooser(iter(["0", "1"]))

    chosen = chooser.choose(_combatant("Player"), _combatant("Bramble"), _ACTIONS)

    assert chosen is _ACTIONS[0]
    assert "between 1 and 2" in buffer.getvalue()


def test_choose_reprompts_on_non_numeric_choice() -> None:
    chooser, _ = _chooser(iter(["struggle", "2"]))

    chosen = chooser.choose(_combatant("Player"), _combatant("Bramble"), _ACTIONS)

    assert chosen is _ACTIONS[1]


def test_choose_reprompts_on_non_ascii_digit_choice() -> None:
    chooser, _ = _chooser(iter(["②", "2"]))

    chosen = chooser.choose(_combatant("Player"), _combatant("Bramble"), _ACTIONS)

    assert chosen is _ACTIONS[1]


def test_choose_raises_when_input_is_exhausted_without_a_valid_choice() -> None:
    chooser, _ = _chooser(iter([]))

    with pytest.raises(RuntimeError):
        chooser.choose(_combatant("Player"), _combatant("Bramble"), _ACTIONS)
