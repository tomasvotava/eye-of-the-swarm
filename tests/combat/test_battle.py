import math
import random
from collections.abc import Sequence

import pytest

from eye.combat import battle as battle_module
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.ai import ScriptedChooser
from eye.combat.battle import (
    ActionAvailability,
    Battle,
    PlayerTurnConcluded,
    PlayerTurnNeedsAction,
    TurnPhase,
)
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName, EffectRegistry
from eye.combat.events import (
    ActionChosen,
    BattleEnded,
    BattleEvent,
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
from eye.combat.tuning import MAX_EXTRA_ACTIONS_PER_TURN, RESONANCE_METER_PREFILL_RATIO
from tests.combat.support import unfold


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


def _play_round(battle: Battle, player_action: ActionDefinition) -> list[BattleEvent]:
    """Drive exactly one round assuming the player's turn needs no more than one swing."""
    events: list[BattleEvent] = []
    query = battle.query_player_turn()
    if isinstance(query, PlayerTurnNeedsAction):
        events.extend(query.pre_turn_events)
        events.extend(battle.resolve_player_turn(player_action))
    else:
        events.extend(query.events)
    if not battle.is_over:
        events.extend(battle.resolve_enemy_turn())
    return events


def test_basic_round_with_no_active_effects() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, STRUGGLE_ACTION)

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
        _ScriptedRandom([0.0, 0.9]),  # wilty triggers (< 0.1); uprooted does not (>= 0.15, not held anyway)
        0.0,
    )

    events = _play_round(battle, STRUGGLE_ACTION)

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
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, cluster_action)

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
    uprooted_rolls = [0.0] * MAX_EXTRA_ACTIONS_PER_TURN  # every offered roll succeeds; none are offered past the cap
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom(uprooted_rolls), 0.0)

    events: list[BattleEvent] = []
    for _ in range(MAX_EXTRA_ACTIONS_PER_TURN + 1):
        query = battle.query_player_turn()
        assert isinstance(query, PlayerTurnNeedsAction)
        events.extend(battle.resolve_player_turn(STRUGGLE_ACTION))
    assert battle.turn_phase == TurnPhase.AWAITING_ENEMY_TURN
    events.extend(battle.resolve_enemy_turn())

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
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, long_action)

    action_chosen = next(event for event in events if isinstance(event, ActionChosen) and event.actor is player)
    hit_events = [event for event in events if isinstance(event, HitLanded) and event.source is player]
    assert action_chosen.was_swapped_by_clouded_judgement is True
    assert len(hit_events) == 1  # short_action (index 0), not the resolved long_action


def test_clouded_judgement_does_not_trigger_battle_side_substitution_for_the_enemy() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    enemy.effects.apply(ActiveEffect(EffectName.CLOUDED_JUDGEMENT, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, STRUGGLE_ACTION)

    action_chosen = next(event for event in events if isinstance(event, ActionChosen) and event.actor is enemy)
    assert action_chosen.was_swapped_by_clouded_judgement is False


def test_vegetative_skip_still_ticks_dot_and_hot_but_skips_meter_fill() -> None:
    player = _combatant("Player", current_hp=50)
    enemy = _combatant("Enemy")
    player.effects.apply(ActiveEffect(EffectName.VEGETATIVE, EffectCategory.BATTLE, remaining_turns=None))
    player.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([0.0]), 0.0)

    events = _play_round(battle, STRUGGLE_ACTION)

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
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([0.0]), 0.0)

    events = _play_round(battle, STRUGGLE_ACTION)

    assert Death(combatant=enemy) in events
    assert events[-1] == BattleEnded(winner=player)
    assert not any(isinstance(event, ActionChosen) and event.actor is enemy for event in events)


def test_spiky_skin_reflects_partial_damage_to_the_attacker() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    enemy.effects.apply(ActiveEffect(EffectName.SPIKY_SKIN, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, STRUGGLE_ACTION)

    reflected = next(event for event in events if isinstance(event, HitReflected))
    assert reflected == HitReflected(source=enemy, target=player, damage=5, target_hp_after=95)


def test_recoil_damages_the_attacker_via_self_damage_taken() -> None:
    player = _combatant("Player", recoil=0.5)
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, STRUGGLE_ACTION)

    self_damage = next(event for event in events if isinstance(event, SelfDamageTaken))
    assert self_damage == SelfDamageTaken(combatant=player, damage=5, combatant_hp_after=95)


def test_nourished_heals_after_toxicity_ticks_in_the_same_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(battle_module, "HEAL_BEFORE_DAMAGE_TICKS", False)
    player = _combatant("Player", current_hp=50)
    enemy = _combatant("Enemy")
    player.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=3))
    player.effects.apply(ActiveEffect(EffectName.NOURISHED, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, STRUGGLE_ACTION)

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
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    _play_round(battle, STRUGGLE_ACTION)

    assert player.current_hp <= 0


def test_lethal_toxicity_is_survived_when_heal_precedes_damage_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(battle_module, "HEAL_BEFORE_DAMAGE_TICKS", True)
    player = _combatant("Player", current_hp=3)
    enemy = _combatant("Enemy", attack=0)
    player.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=3))
    player.effects.apply(ActiveEffect(EffectName.NOURISHED, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    _play_round(battle, STRUGGLE_ACTION)

    assert player.current_hp == 3


def test_requires_full_meter_action_consumes_the_meter() -> None:
    player = _combatant("Player", current_meter=100, available_actions=(SWARM_ACTION,))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, SWARM_ACTION)

    consumed = next(event for event in events if isinstance(event, MeterConsumed))
    assert consumed == MeterConsumed(combatant=player, meter_after=0)
    filled = next(event for event in events if isinstance(event, MeterFilled) and event.combatant is player)
    assert filled == MeterFilled(combatant=player, amount=10, meter_after=10)


@pytest.mark.parametrize(
    ("distance_from_turf", "expected_player_fill"),
    [(0.0, 100), (2.0, 87), (9.0, 43), (10.0, 0), (math.inf, 0)],
)
def test_player_meter_fill_follows_the_floored_proximity_falloff_while_enemy_fills_flat(
    distance_from_turf: float, expected_player_fill: int
) -> None:
    player = _combatant("Player", meter_fill_rate=100)
    enemy = _combatant("Enemy", meter_fill_rate=100)
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), distance_from_turf)

    events = _play_round(battle, STRUGGLE_ACTION)

    fills = {event.combatant.name: event.amount for event in events if isinstance(event, MeterFilled)}
    assert fills == {"Player": expected_player_fill, "Enemy": 100}


def test_winner_is_none_while_battle_is_ongoing() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    assert battle.winner is None
    assert not battle.is_over


def test_player_and_enemy_properties_expose_the_constructed_combatants() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    assert battle.player is player
    assert battle.enemy is enemy


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
        _ScriptedRandom([0.0, 0.9]),
        0.0,
    )

    _play_round(battle, STRUGGLE_ACTION)

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
        _ScriptedRandom([0.0, 0.9]),
        0.0,
    )

    _play_round(battle, STRUGGLE_ACTION)

    assert enemy.current_hp == 1
    assert enemy.effects.has(EffectName.ADRENALINE, category=EffectCategory.LIFESPAN) is False


def test_battle_ending_clears_indefinite_battle_effects_and_emits_effect_expired() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy", current_hp=1)
    enemy.effects.apply(ActiveEffect(EffectName.RUNT, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, STRUGGLE_ACTION)

    assert EffectExpired(target=enemy, effect=EffectName.RUNT, category=EffectCategory.BATTLE) in events
    assert enemy.effects.has(EffectName.RUNT, category=EffectCategory.BATTLE) is False


def test_a_timed_out_battle_effect_emits_a_battle_scoped_effect_expired() -> None:
    player = _combatant("Player")
    player.effects.apply(ActiveEffect(EffectName.RUNT, EffectCategory.BATTLE, remaining_turns=1))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    events = _play_round(battle, STRUGGLE_ACTION)

    assert EffectExpired(target=player, effect=EffectName.RUNT, category=EffectCategory.BATTLE) in events


def test_action_availability_reports_every_action_including_unavailable_ones() -> None:
    player = _combatant("Player", current_meter=0, available_actions=(STRUGGLE_ACTION, SWARM_ACTION))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    assert battle.action_availability(player) == [
        ActionAvailability(action=STRUGGLE_ACTION, is_available=True),
        ActionAvailability(action=SWARM_ACTION, is_available=False),
    ]


def test_action_availability_marks_full_meter_action_available_once_meter_is_full() -> None:
    player = _combatant("Player", current_meter=100, available_actions=(STRUGGLE_ACTION, SWARM_ACTION))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    assert battle.action_availability(player) == [
        ActionAvailability(action=STRUGGLE_ACTION, is_available=True),
        ActionAvailability(action=SWARM_ACTION, is_available=True),
    ]


def test_start_is_a_no_op_when_neither_combatant_holds_resonance() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    events = battle.start()

    assert events == []
    assert player.current_meter == 0
    assert enemy.current_meter == 0


def test_start_prefills_the_meter_for_a_combatant_holding_lifespan_resonance() -> None:
    player = _combatant("Player", current_meter=0, meter_capacity=100)
    player.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, remaining_turns=None))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    events = battle.start()

    expected_amount = round(100 * RESONANCE_METER_PREFILL_RATIO)
    assert player.current_meter == expected_amount
    assert events == [
        MeterFilled(combatant=player, amount=expected_amount, meter_after=expected_amount),
        EffectExpired(target=player, effect=EffectName.RESONANCE, category=EffectCategory.LIFESPAN),
    ]


def test_start_clamps_the_prefill_to_meter_capacity() -> None:
    player = _combatant("Player", current_meter=90, meter_capacity=100)
    player.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, remaining_turns=None))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    events = battle.start()

    assert player.current_meter == 100
    assert events == [
        MeterFilled(combatant=player, amount=round(100 * RESONANCE_METER_PREFILL_RATIO), meter_after=100),
        EffectExpired(target=player, effect=EffectName.RESONANCE, category=EffectCategory.LIFESPAN),
    ]


def test_start_consumes_resonance_so_a_second_call_is_a_no_op() -> None:
    player = _combatant("Player", current_meter=0, meter_capacity=100)
    player.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, remaining_turns=None))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)
    battle.start()

    events = battle.start()

    assert events == []
    assert player.effects.has(EffectName.RESONANCE) is False


def test_start_only_checks_lifespan_category() -> None:
    player = _combatant("Player", current_meter=0, meter_capacity=100)
    player.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.BATTLE, remaining_turns=3))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    events = battle.start()

    assert events == []
    assert player.current_meter == 0
    assert player.effects.has(EffectName.RESONANCE, category=EffectCategory.BATTLE) is True


def test_start_prefills_both_combatants_independently() -> None:
    player = _combatant("Player", current_meter=0, meter_capacity=100)
    player.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, remaining_turns=None))
    enemy = _combatant("Enemy", current_meter=0, meter_capacity=100)
    enemy.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, remaining_turns=None))
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    events = battle.start()

    expected_amount = round(100 * RESONANCE_METER_PREFILL_RATIO)
    assert player.current_meter == expected_amount
    assert enemy.current_meter == expected_amount
    assert events == [
        MeterFilled(combatant=player, amount=expected_amount, meter_after=expected_amount),
        EffectExpired(target=player, effect=EffectName.RESONANCE, category=EffectCategory.LIFESPAN),
        MeterFilled(combatant=enemy, amount=expected_amount, meter_after=expected_amount),
        EffectExpired(target=enemy, effect=EffectName.RESONANCE, category=EffectCategory.LIFESPAN),
    ]


def test_turn_phase_transitions_across_a_plain_round() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    phase_before_query = battle.turn_phase
    assert phase_before_query == TurnPhase.AWAITING_QUERY

    query = battle.query_player_turn()
    assert isinstance(query, PlayerTurnNeedsAction)
    phase_awaiting_action = battle.turn_phase
    assert phase_awaiting_action == TurnPhase.AWAITING_PLAYER_ACTION

    battle.resolve_player_turn(STRUGGLE_ACTION)
    phase_awaiting_enemy = battle.turn_phase
    assert phase_awaiting_enemy == TurnPhase.AWAITING_ENEMY_TURN

    battle.resolve_enemy_turn()
    phase_after_round = battle.turn_phase
    assert phase_after_round == TurnPhase.AWAITING_QUERY


def test_turn_phase_is_finished_once_the_battle_ends() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy", current_hp=1)
    battle = Battle(player, enemy, ScriptedChooser([STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0)

    battle.query_player_turn()
    battle.resolve_player_turn(STRUGGLE_ACTION)

    assert battle.is_over
    assert battle.turn_phase == TurnPhase.FINISHED


def test_query_player_turn_raises_once_the_battle_is_over() -> None:
    player = _combatant("Player", current_hp=0)
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    with pytest.raises(RuntimeError):
        battle.query_player_turn()


def test_resolve_player_turn_raises_without_a_pending_query() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    with pytest.raises(RuntimeError):
        battle.resolve_player_turn(STRUGGLE_ACTION)


def test_resolve_player_turn_raises_for_an_unavailable_action() -> None:
    player = _combatant("Player", current_meter=0, available_actions=(STRUGGLE_ACTION, SWARM_ACTION))
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)
    battle.query_player_turn()

    with pytest.raises(ValueError, match="not among"):
        battle.resolve_player_turn(SWARM_ACTION)


def test_resolve_enemy_turn_raises_once_the_battle_is_over() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy", current_hp=0)
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)

    with pytest.raises(RuntimeError):
        battle.resolve_enemy_turn()


def test_resolve_enemy_turn_raises_with_a_pending_player_query() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)
    battle.query_player_turn()

    with pytest.raises(RuntimeError):
        battle.resolve_enemy_turn()


def test_resolve_enemy_turn_raises_mid_uprooted_chain() -> None:
    player = _combatant("Player", attack=0)
    enemy = _combatant("Enemy")
    player.effects.apply(ActiveEffect(EffectName.UPROOTED, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([0.0]), 0.0)
    battle.query_player_turn()
    battle.resolve_player_turn(STRUGGLE_ACTION)  # procs the chain (roll 0.0 < uprooted_chance(0))
    assert battle.turn_phase == TurnPhase.AWAITING_QUERY  # chain continuation, not the enemy's turn yet

    with pytest.raises(RuntimeError):
        battle.resolve_enemy_turn()


def test_uprooted_chain_interrupted_by_the_battle_ending_mid_chain() -> None:
    lethal_action = ActionDefinition(kind=ActionKind.STRUGGLE, hit_count=1)
    player = _combatant("Player", available_actions=(lethal_action,))
    enemy = _combatant("Enemy", current_hp=10)
    player.effects.apply(ActiveEffect(EffectName.UPROOTED, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)  # no roll should ever happen

    battle.query_player_turn()
    events = battle.resolve_player_turn(lethal_action)  # kills the enemy outright; no Uprooted roll reached

    assert battle.is_over
    assert battle.turn_phase == TurnPhase.FINISHED
    assert events[-1] == BattleEnded(winner=player)
    assert not any(isinstance(event, ExtraActionTriggered) for event in events)


def test_vegetative_skip_cascading_into_lethal_toxicity_and_adrenaline_revive_still_concludes() -> None:
    player = _combatant("Player", current_hp=3)
    enemy = _combatant("Enemy")
    player.effects.apply(ActiveEffect(EffectName.VEGETATIVE, EffectCategory.BATTLE, remaining_turns=None))
    player.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=3))
    player.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([0.0]), 0.0)

    query = battle.query_player_turn()

    assert isinstance(query, PlayerTurnConcluded)
    assert TurnSkipped(combatant=player) in query.events
    assert Death(combatant=player) in query.events
    assert Revive(combatant=player, revived_hp=1) in query.events
    assert player.current_hp == 1
    assert not battle.is_over
    assert battle.turn_phase == TurnPhase.AWAITING_ENEMY_TURN


def test_player_wilty_without_adrenaline_ends_the_battle_via_query() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    player.effects.apply(ActiveEffect(EffectName.WILTY, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([0.0]), 0.0)

    query = battle.query_player_turn()

    assert isinstance(query, PlayerTurnConcluded)
    assert query.events[-1] == BattleEnded(winner=enemy)
    assert battle.is_over
    assert battle.turn_phase == TurnPhase.FINISHED


def test_query_player_turn_raises_after_the_player_turn_already_concluded_via_resolve() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([]), 0.0)
    battle.query_player_turn()
    battle.resolve_player_turn(STRUGGLE_ACTION)
    assert battle.turn_phase == TurnPhase.AWAITING_ENEMY_TURN

    with pytest.raises(RuntimeError):
        battle.query_player_turn()


def test_query_player_turn_raises_after_the_player_turn_already_concluded_via_pre_turn_checks() -> None:
    player = _combatant("Player")
    enemy = _combatant("Enemy")
    player.effects.apply(ActiveEffect(EffectName.VEGETATIVE, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom([0.0]), 0.0)
    query = battle.query_player_turn()
    assert isinstance(query, PlayerTurnConcluded)
    assert battle.turn_phase == TurnPhase.AWAITING_ENEMY_TURN

    with pytest.raises(RuntimeError):
        battle.query_player_turn()


def test_unfold_drives_an_uprooted_chain_one_swing_at_a_time() -> None:
    total_swings = MAX_EXTRA_ACTIONS_PER_TURN + 1
    player = _combatant("Player")
    enemy = _combatant("Enemy", current_hp=10 * total_swings)  # dies exactly on the chain's last swing
    player.effects.apply(ActiveEffect(EffectName.UPROOTED, EffectCategory.BATTLE, remaining_turns=None))
    uprooted_rolls = [0.0] * MAX_EXTRA_ACTIONS_PER_TURN  # every offered roll succeeds; none offered past the cap
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom(uprooted_rolls), 0.0)

    picks_remaining = total_swings

    def pick_action(available: Sequence[ActionDefinition]) -> ActionDefinition:
        nonlocal picks_remaining
        picks_remaining -= 1
        if picks_remaining < 0:
            raise AssertionError("unfold() called the picker more times than the chain has swings")
        return STRUGGLE_ACTION

    events = unfold(battle, pick_action)

    assert battle.is_over is True
    assert picks_remaining == 0
    player_action_events = [event for event in events if isinstance(event, ActionChosen) and event.actor is player]
    assert len(player_action_events) == total_swings
    assert events[-1] == BattleEnded(winner=player)
