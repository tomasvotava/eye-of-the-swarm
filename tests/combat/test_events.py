import dataclasses

import pytest

from eye.combat.actions import ActionKind
from eye.combat.effects import EffectCategory, EffectName
from eye.combat.events import (
    ActionChosen,
    BattleEnded,
    Death,
    DotTicked,
    EffectApplied,
    EffectExpired,
    ExtraActionTriggered,
    HealApplied,
    HitLanded,
    HitReflected,
    MeterConsumed,
    MeterFilled,
    Revive,
    SelfDamageTaken,
    TurnSkipped,
)
from eye.combat.stats import Combatant, Stats


def _combatant(name: str) -> Combatant:
    stats = Stats(max_hp=100, attack=10, defense=5, meter_capacity=100, meter_fill_rate=10)
    return Combatant(name=name, base_stats=stats, current_hp=100)


def test_battle_events_are_frozen() -> None:
    combatant = _combatant("Sporeling")
    event = Death(combatant=combatant)

    with pytest.raises(dataclasses.FrozenInstanceError):
        event.combatant = combatant  # type: ignore[misc]


def test_battle_events_compare_by_value() -> None:
    combatant = _combatant("Sporeling")

    assert Death(combatant=combatant) == Death(combatant=combatant)


def test_death_carries_the_combatant() -> None:
    combatant = _combatant("Sporeling")

    event = Death(combatant=combatant)

    assert event.combatant is combatant


def test_revive_carries_combatant_and_revived_hp() -> None:
    combatant = _combatant("Sporeling")

    event = Revive(combatant=combatant, revived_hp=5)

    assert event.combatant is combatant
    assert event.revived_hp == 5


def test_turn_skipped_carries_the_combatant() -> None:
    combatant = _combatant("Sporeling")

    event = TurnSkipped(combatant=combatant)

    assert event.combatant is combatant


def test_action_chosen_notes_a_clouded_judgement_swap() -> None:
    actor = _combatant("Sporeling")

    event = ActionChosen(actor=actor, action=ActionKind.STRUGGLE, was_swapped_by_clouded_judgement=True)

    assert event.actor is actor
    assert event.action is ActionKind.STRUGGLE
    assert event.was_swapped_by_clouded_judgement is True


def test_hit_landed_carries_hit_progress_and_damage() -> None:
    source = _combatant("Sporeling")
    target = _combatant("Grub")

    event = HitLanded(
        source=source,
        target=target,
        action=ActionKind.STRUGGLE,
        hit_index=1,
        hit_count=3,
        damage=7,
        target_hp_after=93,
    )

    assert event.source is source
    assert event.target is target
    assert event.hit_index == 1
    assert event.hit_count == 3
    assert event.damage == 7
    assert event.target_hp_after == 93


def test_hit_reflected_carries_reflection_source_and_target() -> None:
    source = _combatant("Grub")
    target = _combatant("Sporeling")

    event = HitReflected(source=source, target=target, damage=3, target_hp_after=97)

    assert event.source is source
    assert event.target is target
    assert event.damage == 3
    assert event.target_hp_after == 97


def test_self_damage_taken_carries_combatant_and_hp_after() -> None:
    combatant = _combatant("Sporeling")

    event = SelfDamageTaken(combatant=combatant, damage=2, combatant_hp_after=98)

    assert event.combatant is combatant
    assert event.damage == 2
    assert event.combatant_hp_after == 98


def test_effect_applied_carries_effect_category_and_duration() -> None:
    target = _combatant("Grub")

    event = EffectApplied(target=target, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE, remaining_turns=3)

    assert event.target is target
    assert event.effect is EffectName.FIBROUS
    assert event.category is EffectCategory.BATTLE
    assert event.remaining_turns == 3


def test_effect_expired_carries_target_and_effect() -> None:
    target = _combatant("Grub")

    event = EffectExpired(target=target, effect=EffectName.TOXICITY)

    assert event.target is target
    assert event.effect is EffectName.TOXICITY


def test_dot_ticked_carries_damage_and_hp_after() -> None:
    target = _combatant("Grub")

    event = DotTicked(target=target, effect=EffectName.TOXICITY, damage=4, target_hp_after=90)

    assert event.target is target
    assert event.effect is EffectName.TOXICITY
    assert event.damage == 4
    assert event.target_hp_after == 90


def test_heal_applied_carries_amount_and_hp_after() -> None:
    target = _combatant("Grub")

    event = HealApplied(target=target, effect=EffectName.NOURISHED, amount=6, target_hp_after=96)

    assert event.target is target
    assert event.effect is EffectName.NOURISHED
    assert event.amount == 6
    assert event.target_hp_after == 96


def test_extra_action_triggered_carries_actor_and_index() -> None:
    actor = _combatant("Sporeling")

    event = ExtraActionTriggered(actor=actor, extra_action_index=1)

    assert event.actor is actor
    assert event.extra_action_index == 1


def test_meter_filled_carries_amount_and_meter_after() -> None:
    combatant = _combatant("Sporeling")

    event = MeterFilled(combatant=combatant, amount=10, meter_after=40)

    assert event.combatant is combatant
    assert event.amount == 10
    assert event.meter_after == 40


def test_meter_consumed_carries_meter_after() -> None:
    combatant = _combatant("Sporeling")

    event = MeterConsumed(combatant=combatant, meter_after=0)

    assert event.combatant is combatant
    assert event.meter_after == 0


def test_battle_ended_carries_the_winner() -> None:
    winner = _combatant("Sporeling")

    event = BattleEnded(winner=winner)

    assert event.winner is winner


def test_battle_ended_allows_no_winner() -> None:
    event = BattleEnded(winner=None)

    assert event.winner is None
