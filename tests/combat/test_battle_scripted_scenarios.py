import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pytest

from eye.combat.actions import ActionDefinition, ActionKind, EffectTarget, InflictedEffect
from eye.combat.ai import GreedyAI, ScriptedChooser
from eye.combat.battle import Battle
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName, EffectRegistry
from eye.combat.events import (
    ActionChosen,
    BattleEnded,
    BattleEvent,
    Death,
    EffectApplied,
    EffectExpired,
    ExtraActionTriggered,
    HitLanded,
    HitReflected,
    Revive,
    TurnSkipped,
    Wilted,
)
from eye.combat.stats import Combatant, Stats
from eye.combat.tuning import ADRENALINE_REVIVE_HP, MAX_EXTRA_ACTIONS_PER_TURN
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
ADRENALINE_ON_HIT = ActionDefinition(
    kind=ActionKind.STRUGGLE,
    name="Barbed Struggle",
    inflicts=(InflictedEffect(EffectName.ADRENALINE, EffectTarget.OPPONENT),),
)
WEAK_ACTION = ActionDefinition(kind=ActionKind.STRUGGLE, name="Weak Struggle", hit_count=1)
STRONG_ACTION = ActionDefinition(kind=ActionKind.STRUGGLE, name="Strong Struggle", hit_count=3)


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


@dataclass(frozen=True, slots=True)
class _Scenario:
    battle: Battle
    pick_action: Callable[[Sequence[ActionDefinition]], ActionDefinition]
    check: Callable[[Battle, list[BattleEvent]], None]


def _build_adrenaline_inflicted_mid_battle_then_revives() -> _Scenario:
    """Adrenaline granted via `resolve_hit`'s `inflicts` (not pre-seeded) survives past the round
    that applied it and still triggers a revive on a later, otherwise-lethal hit."""
    player = _combatant("Player", attack=15, defense=5, available_actions=(ADRENALINE_ON_HIT, STRUGGLE_ACTION))
    enemy = _combatant("Enemy", attack=0, defense=5, current_hp=20)
    battle = Battle(
        player, enemy, ScriptedChooser([STRUGGLE_ACTION, STRUGGLE_ACTION]), _ScriptedRandom([]), 0.0, damage_spread=0.0
    )

    swings = 0

    def pick_action(available: Sequence[ActionDefinition]) -> ActionDefinition:
        nonlocal swings
        action = ADRENALINE_ON_HIT if swings == 0 else STRUGGLE_ACTION
        swings += 1
        return action

    def check(battle: Battle, events: list[BattleEvent]) -> None:
        assert battle.winner is player
        assert [e for e in events if isinstance(e, Revive)] == [
            Revive(combatant=enemy, revived_hp=ADRENALINE_REVIVE_HP)
        ]
        adrenaline_applied = [e for e in events if isinstance(e, EffectApplied) and e.effect is EffectName.ADRENALINE]
        assert len(adrenaline_applied) == 1
        assert adrenaline_applied[0].target is enemy
        assert enemy.effects.has(EffectName.ADRENALINE) is False
        assert EffectExpired(target=enemy, effect=EffectName.ADRENALINE, category=EffectCategory.BATTLE) in events

    return _Scenario(battle=battle, pick_action=pick_action, check=check)


def _build_player_wilty_revive_clears_wilty_then_real_death() -> _Scenario:
    """Player holds Wilty+Adrenaline from the start; the forced Wilty roll kills and revives them,
    the revive clears Wilty so it never rolls again, and the enemy's hits then kill for real."""
    player = _combatant("Player", attack=15, defense=5, available_actions=(STRUGGLE_ACTION,))
    player.effects.apply(ActiveEffect(EffectName.WILTY, EffectCategory.BATTLE, remaining_turns=None))
    player.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))
    enemy = _combatant("Enemy", attack=6, defense=5, current_hp=1000)  # two hits kill a revived player
    battle = Battle(
        player,
        enemy,
        ScriptedChooser([STRUGGLE_ACTION, STRUGGLE_ACTION]),
        _ScriptedRandom([0.0]),  # the only Wilty roll; a second one would exhaust the script
        0.0,
        damage_spread=0.0,
    )

    def pick_action(available: Sequence[ActionDefinition]) -> ActionDefinition:
        return STRUGGLE_ACTION

    def check(battle: Battle, events: list[BattleEvent]) -> None:
        assert battle.winner is enemy
        assert events[-1] == BattleEnded(winner=enemy)
        deaths = [e for e in events if isinstance(e, Death) and e.combatant is player]
        assert len(deaths) == 2  # the Wilty death that revives, then the enemy's killing hit
        assert [e for e in events if isinstance(e, Wilted)] == [Wilted(combatant=player)]
        assert events[events.index(Wilted(combatant=player)) + 1] == Death(combatant=player)
        assert [e for e in events if isinstance(e, Revive)] == [
            Revive(combatant=player, revived_hp=ADRENALINE_REVIVE_HP)
        ]
        assert EffectExpired(target=player, effect=EffectName.WILTY, category=EffectCategory.BATTLE) in events
        assert EffectExpired(target=player, effect=EffectName.ADRENALINE, category=EffectCategory.BATTLE) in events
        assert player.effects.has(EffectName.ADRENALINE) is False

    return _Scenario(battle=battle, pick_action=pick_action, check=check)


def _build_uprooted_chain_reaches_cap_under_clouded_judgement() -> _Scenario:
    """An Uprooted chain runs all the way to MAX_EXTRA_ACTIONS_PER_TURN while Clouded Judgement is
    simultaneously active, swapping the player's requested action away on every single swing."""
    player = _combatant("Player", attack=15, defense=5, available_actions=(WEAK_ACTION, STRONG_ACTION))
    player.effects.apply(ActiveEffect(EffectName.UPROOTED, EffectCategory.BATTLE, remaining_turns=None))
    player.effects.apply(ActiveEffect(EffectName.CLOUDED_JUDGEMENT, EffectCategory.BATTLE, remaining_turns=None))
    enemy = _combatant("Enemy", attack=0, defense=10, current_hp=143)  # dies exactly on the chain's 11th swing
    uprooted_rolls = [0.0] * MAX_EXTRA_ACTIONS_PER_TURN  # every offered chain roll succeeds
    battle = Battle(player, enemy, ScriptedChooser([]), _ScriptedRandom(uprooted_rolls), 0.0, damage_spread=0.0)

    def pick_action(available: Sequence[ActionDefinition]) -> ActionDefinition:
        return STRONG_ACTION  # always requested, but Clouded Judgement swaps it away every swing

    def check(battle: Battle, events: list[BattleEvent]) -> None:
        assert battle.winner is player
        extra_actions = [e for e in events if isinstance(e, ExtraActionTriggered)]
        assert [e.extra_action_index for e in extra_actions] == list(range(MAX_EXTRA_ACTIONS_PER_TURN))
        player_actions = [e for e in events if isinstance(e, ActionChosen) and e.actor is player]
        assert len(player_actions) == MAX_EXTRA_ACTIONS_PER_TURN + 1
        assert all(action.was_swapped_by_clouded_judgement for action in player_actions)
        player_hits = [e for e in events if isinstance(e, HitLanded) and e.source is player]
        assert len(player_hits) == MAX_EXTRA_ACTIONS_PER_TURN + 1
        assert all(hit.hit_count == 1 for hit in player_hits)  # WEAK_ACTION, never the requested STRONG_ACTION

    return _Scenario(battle=battle, pick_action=pick_action, check=check)


def _build_vegetative_skip_does_not_spuriously_trigger_spiky_skin() -> _Scenario:
    """A Vegetative-skipped turn lands no hit, so it must not trigger the enemy's Spiky Skin
    reflect -- only a real swing in a later round should."""
    player = _combatant("Player", attack=15, defense=50, available_actions=(STRUGGLE_ACTION,))
    player.effects.apply(ActiveEffect(EffectName.VEGETATIVE, EffectCategory.BATTLE, remaining_turns=None))
    enemy = _combatant("Enemy", attack=0, defense=10, current_hp=13)  # dies exactly on the round-2 hit
    enemy.effects.apply(ActiveEffect(EffectName.SPIKY_SKIN, EffectCategory.BATTLE, remaining_turns=3))
    battle = Battle(
        player,
        enemy,
        ScriptedChooser([STRUGGLE_ACTION]),
        _ScriptedRandom([0.0, 0.5]),  # round 1: Vegetative fires; round 2: it doesn't
        0.0,
        damage_spread=0.0,
    )

    def pick_action(available: Sequence[ActionDefinition]) -> ActionDefinition:
        return STRUGGLE_ACTION

    def check(battle: Battle, events: list[BattleEvent]) -> None:
        assert battle.winner is player
        assert TurnSkipped(combatant=player) in events
        player_hits = [e for e in events if isinstance(e, HitLanded) and e.source is player]
        assert len(player_hits) == 1  # only the round-2 swing -- round 1's skipped turn landed nothing
        assert [e for e in events if isinstance(e, HitReflected)] == [
            HitReflected(source=enemy, target=player, damage=7, target_hp_after=92)  # after round 1's floor-of-1 hit
        ]

    return _Scenario(battle=battle, pick_action=pick_action, check=check)


def _build_both_sides_hold_wilty_and_adrenaline_simultaneously() -> _Scenario:
    """Wilty+Adrenaline is not side-specific -- both combatants holding both at once should each
    independently cascade through their own death->revive, in the same round."""
    player = _combatant("Player", attack=10, defense=1000, available_actions=(STRUGGLE_ACTION,))
    player.effects.apply(ActiveEffect(EffectName.WILTY, EffectCategory.BATTLE, remaining_turns=None))
    player.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))
    enemy = _combatant("Enemy", attack=5, defense=5, current_hp=1000)
    enemy.effects.apply(ActiveEffect(EffectName.WILTY, EffectCategory.BATTLE, remaining_turns=None))
    enemy.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))
    battle = Battle(
        player,
        enemy,
        ScriptedChooser([STRUGGLE_ACTION]),
        _ScriptedRandom([0.0, 0.0]),  # round 1: both sides' Wilty fires; each revive clears it
        0.0,
        damage_spread=0.0,
    )

    def pick_action(available: Sequence[ActionDefinition]) -> ActionDefinition:
        return STRUGGLE_ACTION

    def check(battle: Battle, events: list[BattleEvent]) -> None:
        assert battle.winner is player  # the revived enemy's 10 HP falls to the player's round-2 hit
        revives = [e for e in events if isinstance(e, Revive)]
        assert sorted(revive.combatant.name for revive in revives) == ["Enemy", "Player"]
        deaths = [e for e in events if isinstance(e, Death)]
        assert len(deaths) == 3  # each side's Wilty death, then the enemy's real one
        assert len([e for e in events if isinstance(e, Wilted)]) == 2
        for combatant in (player, enemy):
            assert events[events.index(Wilted(combatant=combatant)) + 1] == Death(combatant=combatant)
            assert EffectExpired(target=combatant, effect=EffectName.WILTY, category=EffectCategory.BATTLE) in events
            assert (
                EffectExpired(target=combatant, effect=EffectName.ADRENALINE, category=EffectCategory.BATTLE) in events
            )
        assert player.effects.has(EffectName.ADRENALINE) is False
        assert enemy.effects.has(EffectName.ADRENALINE) is False

    return _Scenario(battle=battle, pick_action=pick_action, check=check)


def _build_greedy_ai_enemy_drives_a_full_battle_to_completion() -> _Scenario:
    """The query/resolve loop composes correctly with the production `GreedyAI` chooser (every
    other scenario here uses `ScriptedChooser`), sharing one rng instance the way the real
    composition root wires it (`Generation.start_battle`)."""
    player = _combatant("Player", attack=15, defense=5, current_hp=30, available_actions=(STRUGGLE_ACTION,))
    enemy = _combatant("Enemy", attack=15, defense=5, current_hp=30, available_actions=(STRUGGLE_ACTION,))
    rng = _ScriptedRandom([0.5])  # consumed by GreedyAI's single-candidate weighted pick, round 1 only
    enemy_chooser = GreedyAI(t=0.5, rng=rng, distance_from_turf=0.0)
    battle = Battle(player, enemy, enemy_chooser, rng, 0.0, damage_spread=0.0)

    def pick_action(available: Sequence[ActionDefinition]) -> ActionDefinition:
        return STRUGGLE_ACTION

    def check(battle: Battle, events: list[BattleEvent]) -> None:
        assert battle.winner is player
        assert [e for e in events if isinstance(e, ActionChosen) and e.actor is enemy] == [
            ActionChosen(actor=enemy, action=ActionKind.STRUGGLE, was_swapped_by_clouded_judgement=False)
        ]
        player_hits = [e for e in events if isinstance(e, HitLanded) and e.source is player]
        assert len(player_hits) == 2  # kills the enemy on round 2, before its second turn

    return _Scenario(battle=battle, pick_action=pick_action, check=check)


SCENARIOS: dict[str, Callable[[], _Scenario]] = {
    "adrenaline_inflicted_mid_battle_then_revives": _build_adrenaline_inflicted_mid_battle_then_revives,
    "player_wilty_revive_clears_wilty_then_real_death": _build_player_wilty_revive_clears_wilty_then_real_death,
    "uprooted_chain_reaches_cap_under_clouded_judgement": _build_uprooted_chain_reaches_cap_under_clouded_judgement,
    "vegetative_skip_does_not_spuriously_trigger_spiky_skin": (
        _build_vegetative_skip_does_not_spuriously_trigger_spiky_skin
    ),
    "both_sides_hold_wilty_and_adrenaline_simultaneously": _build_both_sides_hold_wilty_and_adrenaline_simultaneously,
    "greedy_ai_enemy_drives_a_full_battle_to_completion": _build_greedy_ai_enemy_drives_a_full_battle_to_completion,
}


@pytest.mark.parametrize("build", SCENARIOS.values(), ids=SCENARIOS.keys())
def test_scripted_full_battle_scenario(build: Callable[[], _Scenario]) -> None:
    """Drives a full battle to completion via `unfold()` for each scripted scenario. `unfold()`
    itself asserts turn_phase/is_over/winner consistency after every query/resolve call (see
    `tests/combat/support.py`), and any misuse RuntimeError/ValueError from `Battle` would
    propagate here as a test failure -- so a clean run of this suite already proves the state
    machine never raises or desyncs, on top of the scenario-specific assertions below.
    """
    scenario = build()

    events = unfold(scenario.battle, scenario.pick_action)

    assert scenario.battle.is_over
    scenario.check(scenario.battle, events)
