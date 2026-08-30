import pytest

from eye.combat import actions as actions_module
from eye.combat.actions import ActionDefinition, ActionKind, EffectTarget, InflictedEffect, resolve_hit
from eye.combat.effects import EffectName
from eye.combat.stats import Combatant, Stats
from eye.combat.tuning import PROXIMITY_FALLOFF_RANGE, STRUGGLE_BASE_POWER, SWARM_ATTACK_BASE_POWER


def _combatant(name: str, attack: int, defense: int, recoil: float = 0.0) -> Combatant:
    stats = Stats(max_hp=100, attack=attack, defense=defense, meter_capacity=100, meter_fill_rate=10, recoil=recoil)
    return Combatant(name=name, base_stats=stats, current_hp=100)


def test_struggle_damage_uses_base_power_plus_attack_minus_defense() -> None:
    attacker = _combatant("Sporeling", attack=10, defense=3)
    defender = _combatant("Grub", attack=4, defense=3)
    action = ActionDefinition(kind=ActionKind.STRUGGLE)

    outcome = resolve_hit(attacker, defender, action, distance_from_turf=0.0)

    assert outcome.damage_to_defender == round(STRUGGLE_BASE_POWER + 10 - 3)


def test_struggle_recoil_scales_with_attacker_recoil_stat() -> None:
    attacker = _combatant("Sporeling", attack=10, defense=3, recoil=0.5)
    defender = _combatant("Grub", attack=4, defense=3)
    action = ActionDefinition(kind=ActionKind.STRUGGLE)

    outcome = resolve_hit(attacker, defender, action, distance_from_turf=0.0)

    assert outcome.recoil_to_attacker == round(outcome.damage_to_defender * 0.5)


def test_struggle_recoil_is_zero_when_attacker_recoil_is_zero() -> None:
    attacker = _combatant("Grub", attack=10, defense=3, recoil=0.0)
    defender = _combatant("Sporeling", attack=4, defense=3)
    action = ActionDefinition(kind=ActionKind.STRUGGLE)

    outcome = resolve_hit(attacker, defender, action, distance_from_turf=0.0)

    assert outcome.recoil_to_attacker == 0


def test_swarm_attack_never_produces_recoil_regardless_of_attacker_recoil_stat() -> None:
    attacker = _combatant("Sporeling", attack=10, defense=3, recoil=0.9)
    defender = _combatant("Grub", attack=4, defense=3)
    action = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)

    outcome = resolve_hit(attacker, defender, action, distance_from_turf=0.0)

    assert outcome.recoil_to_attacker == 0


def test_swarm_attack_damage_falls_off_linearly_with_distance() -> None:
    attacker = _combatant("Sporeling", attack=10, defense=3)
    defender = _combatant("Grub", attack=4, defense=5)
    action = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)

    outcome = resolve_hit(attacker, defender, action, distance_from_turf=PROXIMITY_FALLOFF_RANGE / 2)

    base_damage = SWARM_ATTACK_BASE_POWER + 10 - 5
    assert outcome.damage_to_defender == round(base_damage * 0.5)


def test_swarm_attack_damage_is_zero_at_or_beyond_falloff_range() -> None:
    attacker = _combatant("Sporeling", attack=10, defense=3)
    defender = _combatant("Grub", attack=4, defense=5)
    action = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)

    outcome = resolve_hit(attacker, defender, action, distance_from_turf=PROXIMITY_FALLOFF_RANGE * 2)

    assert outcome.damage_to_defender == 0


def test_struggle_damage_is_distance_independent_by_default() -> None:
    attacker = _combatant("Sporeling", attack=10, defense=3)
    defender = _combatant("Grub", attack=4, defense=3)
    action = ActionDefinition(kind=ActionKind.STRUGGLE)

    close = resolve_hit(attacker, defender, action, distance_from_turf=0.0)
    far = resolve_hit(attacker, defender, action, distance_from_turf=PROXIMITY_FALLOFF_RANGE * 2)

    assert close.damage_to_defender == far.damage_to_defender


def test_struggle_damage_falls_off_with_distance_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions_module, "STRUGGLE_SCALES_WITH_DISTANCE", True)
    attacker = _combatant("Sporeling", attack=10, defense=3)
    defender = _combatant("Grub", attack=4, defense=3)
    action = ActionDefinition(kind=ActionKind.STRUGGLE)

    outcome = resolve_hit(attacker, defender, action, distance_from_turf=PROXIMITY_FALLOFF_RANGE / 2)

    base_damage = STRUGGLE_BASE_POWER + 10 - 3
    assert outcome.damage_to_defender == round(base_damage * 0.5)


def test_damage_floors_at_zero_when_defense_overwhelms_attack() -> None:
    attacker = _combatant("Sporeling", attack=1, defense=1)
    defender = _combatant("Grub", attack=1, defense=1000)
    action = ActionDefinition(kind=ActionKind.STRUGGLE)

    outcome = resolve_hit(attacker, defender, action, distance_from_turf=0.0)

    assert outcome.damage_to_defender == 0


def test_resolve_hit_is_deterministic_for_unchanged_inputs() -> None:
    attacker = _combatant("Sporeling", attack=10, defense=3, recoil=0.5)
    defender = _combatant("Grub", attack=4, defense=3)
    action = ActionDefinition(kind=ActionKind.STRUGGLE)

    first = resolve_hit(attacker, defender, action, distance_from_turf=0.0)
    second = resolve_hit(attacker, defender, action, distance_from_turf=0.0)

    assert first == second


def test_inflicted_effect_resolves_self_and_opponent_to_concrete_combatants() -> None:
    attacker = _combatant("Sporeling", attack=10, defense=3)
    defender = _combatant("Grub", attack=4, defense=3)
    action = ActionDefinition(
        kind=ActionKind.STRUGGLE,
        inflicts=(
            InflictedEffect(EffectName.WILTY, EffectTarget.SELF),
            InflictedEffect(EffectName.ADRENALINE, EffectTarget.OPPONENT),
        ),
    )

    outcome = resolve_hit(attacker, defender, action, distance_from_turf=0.0)

    assert outcome.inflicted == (
        (EffectName.WILTY, attacker),
        (EffectName.ADRENALINE, defender),
    )
