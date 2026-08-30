import random
from collections.abc import Sequence

import pytest

from eye.combat import battle as battle_module
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.ai import ScriptedChooser
from eye.combat.battle import ActionAvailability, Battle
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName, EffectRegistry
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
from eye.combat.tuning import MAX_EXTRA_ACTIONS_PER_TURN


class _ScriptedRandom(random.Random):
    """Deterministic random.Random stand-in: pops one value per random() call, choice() picks index 0."""

    def __init__(self, random_values: Sequence[float]) -> None:
        super().__init__()
        self._values = list(random_values)

    def random(self) -> float:
        return self._values.pop(0)

    def choice(self, seq: Sequence[ActionDefinition]) -> ActionDefinition:  # type: ignore[override]
        # Narrower than random.Random.choice's generic signature -- this double is only ever
        # handed Sequence[ActionDefinition] by Battle, so the narrowing is intentional.
        return seq[0]


STRUGGLE_ACTION = ActionDefinition(kind=ActionKind.STRUGGLE)
SWARM_ACTION = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)


def _combatant(
    name: str,
    attack: int = 10,
    defense: int = 5,
    current_hp: int = 100,
    max_hp: int = 100,
    recoil: float = 0.0,
    current_meter: int = 0,
    meter_capacity: int = 100,
    meter_fill_rate: int = 10,
    available_actions: Sequence[ActionDefinition] = (STRUGGLE_ACTION,),
) -> Combatant:
    stats = Stats(
        max_hp=max_hp,
        attack=attack,
        defense=defense,
        meter_capacity=meter_capacity,
        meter_fill_rate=meter_fill_rate,
        recoil=recoil,
    )
    return Combatant(
        name=name,
        base_stats=stats,
        current_hp=current_hp,
        current_meter=current_meter,
        effects=EffectRegistry(),
        available_actions=available_actions,
    )


def test_basic_round_with_no_active_effects() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(
        player, enemy, ScriptedChooser([STRUGGLE_ACTION]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    events = battle.take_round()

    assert events == [
        ActionChosen(actor=player, action=ActionKind.STRUGGLE, was_swapped_by_clouded_judgement=False),
        HitLanded(
            source=player,
            target=enemy,
            action=ActionKind.STRUGGLE,
            hit_index=0,
            hit_count=1,
            damage=10,
            target_hp_after=90,
        ),
        MeterFilled(combatant=player, amount=10, meter_after=10),
        ActionChosen(actor=enemy, action=ActionKind.STRUGGLE, was_swapped_by_clouded_judgement=False),
        HitLanded(
            source=enemy,
            target=player,
            action=ActionKind.STRUGGLE,
            hit_index=0,
            hit_count=1,
            damage=10,
            target_hp_after=90,
        ),
        MeterFilled(combatant=enemy, amount=10, meter_after=10),
    ]
    assert not battle.is_over


def test_wilty_adrenaline_chain_continues_as_an_extra_turn() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    enemy.effects.apply(ActiveEffect(EffectName.WILTY, EffectCategory.BATTLE, remaining_turns=None))
    enemy.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(
        player,
        enemy,
        ScriptedChooser([STRUGGLE_ACTION]),
        ScriptedChooser([STRUGGLE_ACTION]),
        _ScriptedRandom([0.0, 0.9]),  # wilty triggers (< 0.1); uprooted does not (>= 0.15, not held anyway)
        0.0,
    )

    events = battle.take_round()

    assert events == [
        ActionChosen(actor=player, action=ActionKind.STRUGGLE, was_swapped_by_clouded_judgement=False),
        HitLanded(
            source=player,
            target=enemy,
            action=ActionKind.STRUGGLE,
            hit_index=0,
            hit_count=1,
            damage=10,
            target_hp_after=90,
        ),
        MeterFilled(combatant=player, amount=10, meter_after=10),
        Death(combatant=enemy),
        Revive(combatant=enemy, revived_hp=1),
        EffectApplied(target=enemy, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE, remaining_turns=3),
        ActionChosen(actor=enemy, action=ActionKind.STRUGGLE, was_swapped_by_clouded_judgement=False),
        HitLanded(
            source=enemy,
            target=player,
            action=ActionKind.STRUGGLE,
            hit_index=0,
            hit_count=1,
            damage=14,
            target_hp_after=86,
        ),
        MeterFilled(combatant=enemy, amount=10, meter_after=10),
    ]
    assert enemy.current_hp == 1
    assert not enemy.effects.has(EffectName.ADRENALINE)


def test_cluster_hit_stops_early_on_death_and_short_circuits_the_round() -> None:
    cluster_action = ActionDefinition(kind=ActionKind.STRUGGLE, hit_count=3)
    player = _combatant("Player", available_actions=(cluster_action,))
    enemy = _combatant("Enemy", current_hp=15)
    battle = Battle(
        player, enemy, ScriptedChooser([cluster_action]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    events = battle.take_round()

    assert events == [
        ActionChosen(actor=player, action=ActionKind.STRUGGLE, was_swapped_by_clouded_judgement=False),
        HitLanded(
            source=player,
            target=enemy,
            action=ActionKind.STRUGGLE,
            hit_index=0,
            hit_count=3,
            damage=10,
            target_hp_after=5,
        ),
        HitLanded(
            source=player,
            target=enemy,
            action=ActionKind.STRUGGLE,
            hit_index=1,
            hit_count=3,
            damage=10,
            target_hp_after=-5,
        ),
        Death(combatant=enemy),
        BattleEnded(winner=player),
    ]
    assert battle.is_over
    assert battle.winner is player


def test_uprooted_chains_extra_actions_up_to_the_hard_cap() -> None:
    player = _combatant("Player", attack=0)  # 0 damage keeps enemy hp irrelevant to this scenario
    enemy = _combatant("Enemy")
    player.effects.apply(ActiveEffect(EffectName.UPROOTED, EffectCategory.BATTLE, remaining_turns=None))
    action_queue = [STRUGGLE_ACTION] * (MAX_EXTRA_ACTIONS_PER_TURN + 1)
    uprooted_rolls = [0.0] * MAX_EXTRA_ACTIONS_PER_TURN  # every offered roll succeeds; none are offered past the cap
    battle = Battle(
        player,
        enemy,
        ScriptedChooser(action_queue),
        ScriptedChooser([STRUGGLE_ACTION]),
        _ScriptedRandom(uprooted_rolls),
        0.0,
    )

    events = battle.take_round()

    extra_action_events = [event for event in events if isinstance(event, ExtraActionTriggered)]
    player_action_events = [event for event in events if isinstance(event, ActionChosen) and event.actor is player]
    assert [event.extra_action_index for event in extra_action_events] == list(range(MAX_EXTRA_ACTIONS_PER_TURN))
    assert len(player_action_events) == MAX_EXTRA_ACTIONS_PER_TURN + 1


def test_clouded_judgement_substitutes_the_players_chosen_action() -> None:
    short_action = ActionDefinition(kind=ActionKind.STRUGGLE, hit_count=1)
    long_action = ActionDefinition(kind=ActionKind.STRUGGLE, hit_count=3)
    player = _combatant("Player", available_actions=(short_action, long_action))
    enemy = _combatant("Enemy", current_hp=1000)
    player.effects.apply(ActiveEffect(EffectName.CLOUDED_JUDGEMENT, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(
        player, enemy, ScriptedChooser([long_action]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    events = battle.take_round()

    action_chosen = next(event for event in events if isinstance(event, ActionChosen) and event.actor is player)
    hit_events = [event for event in events if isinstance(event, HitLanded) and event.source is player]
    assert action_chosen.was_swapped_by_clouded_judgement is True
    assert len(hit_events) == 1  # short_action (index 0), not the chooser's queued long_action


def test_clouded_judgement_does_not_trigger_battle_side_substitution_for_the_enemy() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    enemy.effects.apply(ActiveEffect(EffectName.CLOUDED_JUDGEMENT, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(
        player, enemy, ScriptedChooser([STRUGGLE_ACTION]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    events = battle.take_round()

    action_chosen = next(event for event in events if isinstance(event, ActionChosen) and event.actor is enemy)
    assert action_chosen.was_swapped_by_clouded_judgement is False


def test_vegetative_skip_still_ticks_dot_and_hot_but_skips_meter_fill() -> None:
    player = _combatant("Player", current_hp=50)
    enemy = _combatant("Enemy")
    player.effects.apply(ActiveEffect(EffectName.VEGETATIVE, EffectCategory.BATTLE, remaining_turns=None))
    player.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(
        player,
        enemy,
        ScriptedChooser([STRUGGLE_ACTION]),
        ScriptedChooser([STRUGGLE_ACTION]),
        _ScriptedRandom([0.0]),
        0.0,
    )

    events = battle.take_round()

    player_events = list(events)[:2]
    assert player_events == [
        TurnSkipped(combatant=player),
        DotTicked(target=player, effect=EffectName.TOXICITY, damage=3, target_hp_after=47),
    ]
    assert not any(isinstance(event, MeterFilled) and event.combatant is player for event in events)
    assert player.current_meter == 0


def test_wilty_without_adrenaline_ends_the_turn_immediately() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    enemy.effects.apply(ActiveEffect(EffectName.WILTY, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(
        player,
        enemy,
        ScriptedChooser([STRUGGLE_ACTION]),
        ScriptedChooser([STRUGGLE_ACTION]),
        _ScriptedRandom([0.0]),
        0.0,
    )

    events = battle.take_round()

    assert Death(combatant=enemy) in events
    assert events[-1] == BattleEnded(winner=player)
    assert not any(isinstance(event, ActionChosen) and event.actor is enemy for event in events)


def test_spiky_skin_reflects_partial_damage_to_the_attacker() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    enemy.effects.apply(ActiveEffect(EffectName.SPIKY_SKIN, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(
        player, enemy, ScriptedChooser([STRUGGLE_ACTION]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    events = battle.take_round()

    reflected = next(event for event in events if isinstance(event, HitReflected))
    assert reflected == HitReflected(source=enemy, target=player, damage=5, target_hp_after=95)


def test_recoil_damages_the_attacker_via_self_damage_taken() -> None:
    player = _combatant("Player", recoil=0.5)
    enemy = _combatant("Enemy")
    battle = Battle(
        player, enemy, ScriptedChooser([STRUGGLE_ACTION]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    events = battle.take_round()

    self_damage = next(event for event in events if isinstance(event, SelfDamageTaken))
    assert self_damage == SelfDamageTaken(combatant=player, damage=5, combatant_hp_after=95)


def test_nourished_heals_after_toxicity_ticks_in_the_same_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(battle_module, "HEAL_BEFORE_DAMAGE_TICKS", False)
    player = _combatant("Player", current_hp=50)
    enemy = _combatant("Enemy")
    player.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=3))
    player.effects.apply(ActiveEffect(EffectName.NOURISHED, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(
        player, enemy, ScriptedChooser([STRUGGLE_ACTION]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    events = battle.take_round()

    dot = next(event for event in events if isinstance(event, DotTicked))
    hot = next(event for event in events if isinstance(event, HealApplied))
    assert dot == DotTicked(target=player, effect=EffectName.TOXICITY, damage=3, target_hp_after=47)
    assert hot == HealApplied(target=player, effect=EffectName.NOURISHED, amount=3, target_hp_after=50)


def test_lethal_toxicity_kills_when_heal_does_not_precede_damage_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(battle_module, "HEAL_BEFORE_DAMAGE_TICKS", False)
    player = _combatant("Player", current_hp=3)
    enemy = _combatant("Enemy", attack=0)
    player.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=3))
    player.effects.apply(ActiveEffect(EffectName.NOURISHED, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(
        player, enemy, ScriptedChooser([STRUGGLE_ACTION]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    battle.take_round()

    assert player.current_hp <= 0


def test_lethal_toxicity_is_survived_when_heal_precedes_damage_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(battle_module, "HEAL_BEFORE_DAMAGE_TICKS", True)
    player = _combatant("Player", current_hp=3)
    enemy = _combatant("Enemy", attack=0)
    player.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=3))
    player.effects.apply(ActiveEffect(EffectName.NOURISHED, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(
        player, enemy, ScriptedChooser([STRUGGLE_ACTION]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    battle.take_round()

    assert player.current_hp == 3


def test_requires_full_meter_action_consumes_the_meter() -> None:
    player = _combatant("Player", current_meter=100, available_actions=(SWARM_ACTION,))
    enemy = _combatant("Enemy")
    battle = Battle(
        player, enemy, ScriptedChooser([SWARM_ACTION]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    events = battle.take_round()

    consumed = next(event for event in events if isinstance(event, MeterConsumed))
    assert consumed == MeterConsumed(combatant=player, meter_after=0)
    filled = next(event for event in events if isinstance(event, MeterFilled) and event.combatant is player)
    assert filled == MeterFilled(combatant=player, amount=10, meter_after=10)


def test_take_round_on_an_already_finished_battle_returns_no_events() -> None:
    player = _combatant("Player", current_hp=0)
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    assert battle.take_round() == []


def test_winner_is_none_while_battle_is_ongoing() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    assert battle.winner is None
    assert not battle.is_over


def test_revive_consumes_only_the_battle_category_adrenaline_when_both_are_active() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    enemy.effects.apply(ActiveEffect(EffectName.WILTY, EffectCategory.BATTLE, remaining_turns=None))
    enemy.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.LIFESPAN, remaining_turns=None))
    enemy.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(
        player,
        enemy,
        ScriptedChooser([STRUGGLE_ACTION]),
        ScriptedChooser([STRUGGLE_ACTION]),
        _ScriptedRandom([0.0, 0.9]),
        0.0,
    )

    battle.take_round()

    assert enemy.effects.has(EffectName.ADRENALINE, category=EffectCategory.BATTLE) is False
    assert enemy.effects.has(EffectName.ADRENALINE, category=EffectCategory.LIFESPAN) is True


def test_revive_consumes_lifespan_adrenaline_when_no_battle_instance_is_active() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    enemy.effects.apply(ActiveEffect(EffectName.WILTY, EffectCategory.BATTLE, remaining_turns=None))
    enemy.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.LIFESPAN, remaining_turns=None))
    battle = Battle(
        player,
        enemy,
        ScriptedChooser([STRUGGLE_ACTION]),
        ScriptedChooser([STRUGGLE_ACTION]),
        _ScriptedRandom([0.0, 0.9]),
        0.0,
    )

    battle.take_round()

    assert enemy.current_hp == 1
    assert enemy.effects.has(EffectName.ADRENALINE, category=EffectCategory.LIFESPAN) is False


def test_battle_ending_clears_indefinite_battle_effects_and_emits_effect_expired() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy", current_hp=1)
    enemy.effects.apply(ActiveEffect(EffectName.RUNT, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(
        player, enemy, ScriptedChooser([STRUGGLE_ACTION]), ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0
    )

    events = battle.take_round()

    assert EffectExpired(target=enemy, effect=EffectName.RUNT) in events
    assert enemy.effects.has(EffectName.RUNT, category=EffectCategory.BATTLE) is False


def test_action_availability_reports_every_action_including_unavailable_ones() -> None:
    player = _combatant("Player", current_meter=0, available_actions=(STRUGGLE_ACTION, SWARM_ACTION))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    assert battle.action_availability(player) == [
        ActionAvailability(action=STRUGGLE_ACTION, is_available=True),
        ActionAvailability(action=SWARM_ACTION, is_available=False),
    ]


def test_action_availability_marks_full_meter_action_available_once_meter_is_full() -> None:
    player = _combatant("Player", current_meter=100, available_actions=(STRUGGLE_ACTION, SWARM_ACTION))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    assert battle.action_availability(player) == [
        ActionAvailability(action=STRUGGLE_ACTION, is_available=True),
        ActionAvailability(action=SWARM_ACTION, is_available=True),
    ]
