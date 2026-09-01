import io

import pytest
from rich.console import Console

from eye.bestiary import BESTIARY
from eye.character import Character
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.stats import Combatant, Stats
from eye.exploration.encounters import EncounterKind, Strain
from eye.exploration.events import EnemyEncountered
from eye.session.generation import Generation
from eye.tui.combat import _prompt_action, play_battle
from tests.session.doubles import ScriptedEncounterRandom

_STATS = Stats(max_hp=20, attack=5, defense=2, meter_capacity=10, meter_fill_rate=1)
_ACTIONS = (
    ActionDefinition(kind=ActionKind.STRUGGLE, name="Struggle"),
    ActionDefinition(kind=ActionKind.SWARM_ATTACK, name="Swarm Attack", requires_full_meter=True),
)


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, width=120), buffer


def _combatant(name: str) -> Combatant:
    return Combatant(name=name, base_stats=_STATS, current_hp=20)


def test_prompt_action_returns_the_action_matching_a_valid_numbered_choice() -> None:
    console, _ = _console()

    chosen = _prompt_action(console, iter(["2"]), _combatant("Player"), _combatant("Bramble"), _ACTIONS)

    assert chosen is _ACTIONS[1]


def test_prompt_action_renders_both_combatants_hp_and_the_action_menu() -> None:
    console, buffer = _console()

    _prompt_action(console, iter(["1"]), _combatant("Player"), _combatant("Bramble"), _ACTIONS)

    output = buffer.getvalue()
    assert "Player" in output
    assert "Bramble" in output
    assert "20/20" in output
    assert "Struggle" in output
    assert "Swarm Attack" in output


def test_prompt_action_reprompts_on_out_of_range_choice() -> None:
    console, buffer = _console()

    chosen = _prompt_action(console, iter(["0", "1"]), _combatant("Player"), _combatant("Bramble"), _ACTIONS)

    assert chosen is _ACTIONS[0]
    assert "between 1 and 2" in buffer.getvalue()


def test_prompt_action_reprompts_on_non_numeric_choice() -> None:
    console, _ = _console()

    chosen = _prompt_action(console, iter(["struggle", "2"]), _combatant("Player"), _combatant("Bramble"), _ACTIONS)

    assert chosen is _ACTIONS[1]


def test_prompt_action_reprompts_on_non_ascii_digit_choice() -> None:
    console, _ = _console()

    chosen = _prompt_action(console, iter(["②", "2"]), _combatant("Player"), _combatant("Bramble"), _ACTIONS)

    assert chosen is _ACTIONS[1]


def test_prompt_action_raises_when_input_is_exhausted_without_a_valid_choice() -> None:
    console, _ = _console()

    with pytest.raises(RuntimeError):
        _prompt_action(console, iter([]), _combatant("Player"), _combatant("Bramble"), _ACTIONS)


def _generation(kind_queue: list[EncounterKind], stats: Stats, character: Character | None = None) -> Generation:
    return Generation(
        character=character or Character(current_hp=100, max_hp=100),
        stats=stats,
        actions=(ActionDefinition(kind=ActionKind.STRUGGLE),),
        rng=ScriptedEncounterRandom(kind_queue),
        starting_screen=0,
        matured_turfs=(),
    )


def test_play_battle_drives_a_win_to_completion_and_finishes_the_battle() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation([EncounterKind.ENEMY], stats=overwhelming)
    events = generation.advance()
    encounter = next(event for event in events if isinstance(event, EnemyEncountered))
    console, buffer = _console()

    play_battle(console, generation, encounter, iter(["1"] * 20))

    assert generation.spores_gained == BESTIARY[Strain.BRAMBLE].spore_award
    assert "wins the battle" in buffer.getvalue()


def test_play_battle_drives_a_loss_to_completion_and_ends_the_generation() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = Character(current_hp=5, max_hp=5)
    generation = _generation([EncounterKind.ENEMY], stats=fragile, character=character)
    events = generation.advance()
    encounter = next(event for event in events if isinstance(event, EnemyEncountered))
    console, buffer = _console()

    play_battle(console, generation, encounter, iter(["1"] * 20))

    assert generation.died is True
    assert character.current_hp <= 0
    assert "This generation has ended" in buffer.getvalue()
