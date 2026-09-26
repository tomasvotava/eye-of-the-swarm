import io

from rich.console import Console

from eye.combat.actions import ActionKind
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName, EffectRegistry
from eye.combat.events import (
    ActionChosen,
    BattleEnded,
    Death,
    EffectApplied,
    HitLanded,
    MeterFilled,
    Wilted,
)
from eye.combat.stats import Combatant, Stats
from eye.exploration.encounters import Biome, ResourceKind, Strain
from eye.exploration.events import EnemyEncountered, ResourceGranted, SeedPlanted
from eye.session.events import SeedsMatured, SporesAwarded
from eye.tui import render

_STATS = Stats(max_hp=20, attack=5, defense=2, meter_capacity=10, meter_fill_rate=1)


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, width=120), buffer


def _combatant(**overrides: object) -> Combatant:
    defaults: dict[str, object] = {"name": "Player", "base_stats": _STATS, "current_hp": 20}
    defaults.update(overrides)
    return Combatant(**defaults)  # type: ignore[arg-type]


def test_events_renders_exploration_event_text() -> None:
    console, buffer = _console()

    render.events(console, [EnemyEncountered(strain=Strain.BRAMBLE, biome=Biome.BRAMBEROSITY)])

    assert "Bramble" in buffer.getvalue()


def test_events_renders_resource_granted_with_amount() -> None:
    console, buffer = _console()

    render.events(console, [ResourceGranted(kind=ResourceKind.SPORES, amount=7)])

    assert "7" in buffer.getvalue()


def test_events_renders_seed_planted_position() -> None:
    console, buffer = _console()

    render.events(console, [SeedPlanted(position=42)])

    assert "42" in buffer.getvalue()


def test_events_renders_action_chosen_with_action_name() -> None:
    console, buffer = _console()
    actor = _combatant()

    render.events(
        console, [ActionChosen(actor=actor, action=ActionKind.STRUGGLE, was_swapped_by_clouded_judgement=False)]
    )

    assert "Struggle" in buffer.getvalue()


def test_events_renders_hit_landed_with_damage_and_hp() -> None:
    console, buffer = _console()
    source, target = _combatant(name="Player"), _combatant(name="Bramble")

    render.events(
        console,
        [
            HitLanded(
                source=source,
                target=target,
                action=ActionKind.STRUGGLE,
                hit_index=0,
                hit_count=1,
                damage=5,
                target_hp_after=15,
                is_critical=False,
            )
        ],
    )

    output = buffer.getvalue()
    assert "5" in output
    assert "15" in output


def test_events_renders_multi_hit_index() -> None:
    console, buffer = _console()
    source, target = _combatant(), _combatant()

    render.events(
        console,
        [
            HitLanded(
                source=source,
                target=target,
                action=ActionKind.SWARM_ATTACK,
                hit_index=1,
                hit_count=3,
                damage=3,
                target_hp_after=10,
                is_critical=False,
            )
        ],
    )

    assert "2/3" in buffer.getvalue()


def test_events_renders_effect_applied_with_effect_name() -> None:
    console, buffer = _console()
    target = _combatant()

    render.events(
        console,
        [EffectApplied(target=target, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE, remaining_turns=3)],
    )

    assert "Fibrous" in buffer.getvalue()


def test_events_renders_death() -> None:
    console, buffer = _console()

    render.events(console, [Death(combatant=_combatant(name="Bramble"))])

    assert "Bramble" in buffer.getvalue()


def test_events_renders_wilted() -> None:
    console, buffer = _console()

    render.events(console, [Wilted(combatant=_combatant(name="Bramble"))])

    assert "Bramble wilts away." in buffer.getvalue()


def test_events_renders_battle_ended_with_winner_name() -> None:
    console, buffer = _console()

    render.events(console, [BattleEnded(winner=_combatant(name="Player"))])

    assert "Player" in buffer.getvalue()


def test_events_renders_battle_ended_with_no_winner() -> None:
    console, buffer = _console()

    render.events(console, [BattleEnded(winner=None)])

    assert buffer.getvalue()


def test_events_renders_seeds_matured_positions() -> None:
    console, buffer = _console()

    render.events(console, [SeedsMatured(positions=(3, 8))])

    output = buffer.getvalue()
    assert "3" in output
    assert "8" in output


def test_events_renders_spores_awarded() -> None:
    console, buffer = _console()

    render.events(console, [SporesAwarded(amount=4, spores_available=12)])

    output = buffer.getvalue()
    assert "4" in output
    assert "12" in output


def test_events_renders_meter_filled() -> None:
    console, buffer = _console()

    render.events(console, [MeterFilled(combatant=_combatant(), amount=2, meter_after=6)])

    assert "6" in buffer.getvalue()


def test_combatant_state_renders_hp_and_meter() -> None:
    console, buffer = _console()
    combatant = _combatant(current_hp=8, current_meter=3)

    render.combatant_state(console, combatant)

    output = buffer.getvalue()
    assert "8" in output
    assert "20" in output
    assert "3" in output


def test_combatant_state_renders_active_effects() -> None:
    console, buffer = _console()
    effects = EffectRegistry()
    effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, None))
    combatant = _combatant(effects=effects)

    render.combatant_state(console, combatant)

    assert "Fibrous" in buffer.getvalue()


def test_combatant_state_without_active_effects_omits_effects_line() -> None:
    console, buffer = _console()

    render.combatant_state(console, _combatant())

    assert "effect" not in buffer.getvalue().lower()
