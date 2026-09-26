import random

import pytest

from eye.combat import actions as actions_module
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.ai import GreedyAI, ScriptedChooser
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName, EffectRegistry
from eye.combat.stats import Combatant, Stats
from eye.combat.tuning import PROXIMITY_FALLOFF_RANGE

_NEAR_ZERO_T = 1e-9


def _combatant(name: str, attack: int, defense: int, current_hp: int = 100, recoil: float = 0.0) -> Combatant:
    stats = Stats(max_hp=100, attack=attack, defense=defense, meter_capacity=100, meter_fill_rate=10, recoil=recoil)
    return Combatant(name=name, base_stats=stats, current_hp=current_hp, effects=EffectRegistry())


def test_scripted_chooser_returns_queued_actions_in_order() -> None:
    struggle = ActionDefinition(kind=ActionKind.STRUGGLE)
    swarm = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)
    chooser = ScriptedChooser([struggle, swarm])
    actor = _combatant("Sporeling", attack=10, defense=5)
    opponent = _combatant("Grub", attack=4, defense=3)

    assert chooser.choose(actor, opponent, [struggle, swarm]) is struggle
    assert chooser.choose(actor, opponent, [struggle, swarm]) is swarm


def test_scripted_chooser_raises_when_queue_exhausted() -> None:
    chooser = ScriptedChooser([])
    actor = _combatant("Sporeling", attack=10, defense=5)
    opponent = _combatant("Grub", attack=4, defense=3)

    with pytest.raises(IndexError):
        chooser.choose(actor, opponent, [])


def test_greedy_ai_picks_the_highest_scoring_action() -> None:
    actor = _combatant("Enemy", attack=10, defense=5)
    opponent = _combatant("Player", attack=4, defense=5, current_hp=100)
    struggle = ActionDefinition(kind=ActionKind.STRUGGLE)
    swarm = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)
    ai = GreedyAI(t=_NEAR_ZERO_T, rng=random.Random(0), distance_from_turf=0.0)

    assert ai.choose(actor, opponent, [struggle, swarm]) is swarm


def test_greedy_ai_prefers_a_lethal_action_via_the_k_bonus(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions_module, "STRUGGLE_SCALES_WITH_DISTANCE", False)
    actor = _combatant("Enemy", attack=10, defense=5, recoil=0.9)
    opponent = _combatant("Player", attack=4, defense=5, current_hp=9)
    struggle = ActionDefinition(kind=ActionKind.STRUGGLE)
    swarm = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)
    ai = GreedyAI(t=_NEAR_ZERO_T, rng=random.Random(0), distance_from_turf=PROXIMITY_FALLOFF_RANGE * 0.8)

    assert ai.choose(actor, opponent, [struggle, swarm]) is struggle


def test_greedy_ai_suppresses_the_k_bonus_when_opponent_holds_adrenaline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(actions_module, "STRUGGLE_SCALES_WITH_DISTANCE", False)
    actor = _combatant("Enemy", attack=10, defense=5, recoil=0.9)
    opponent = _combatant("Player", attack=4, defense=5, current_hp=9)
    opponent.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))
    struggle = ActionDefinition(kind=ActionKind.STRUGGLE)
    swarm = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)
    ai = GreedyAI(t=_NEAR_ZERO_T, rng=random.Random(0), distance_from_turf=PROXIMITY_FALLOFF_RANGE * 0.8)

    assert ai.choose(actor, opponent, [struggle, swarm]) is swarm


def test_greedy_ai_excludes_rank_zero_when_actor_holds_clouded_judgement() -> None:
    actor = _combatant("Enemy", attack=10, defense=5)
    actor.effects.apply(ActiveEffect(EffectName.CLOUDED_JUDGEMENT, EffectCategory.BATTLE, remaining_turns=None))
    opponent = _combatant("Player", attack=4, defense=5, current_hp=100)
    struggle = ActionDefinition(kind=ActionKind.STRUGGLE)
    swarm = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)
    ai = GreedyAI(t=_NEAR_ZERO_T, rng=random.Random(0), distance_from_turf=0.0)

    assert ai.choose(actor, opponent, [struggle, swarm]) is struggle


def test_greedy_ai_does_not_exclude_the_only_available_action_under_clouded_judgement() -> None:
    actor = _combatant("Enemy", attack=10, defense=5)
    actor.effects.apply(ActiveEffect(EffectName.CLOUDED_JUDGEMENT, EffectCategory.BATTLE, remaining_turns=None))
    opponent = _combatant("Player", attack=4, defense=5, current_hp=100)
    struggle = ActionDefinition(kind=ActionKind.STRUGGLE)
    ai = GreedyAI(t=_NEAR_ZERO_T, rng=random.Random(0), distance_from_turf=0.0)

    assert ai.choose(actor, opponent, [struggle]) is struggle


@pytest.mark.parametrize("t", [0.15, 0.35, 0.6])
def test_greedy_ai_sampling_matches_the_geometric_distribution(t: float) -> None:
    actor = _combatant("Enemy", attack=10, defense=5)
    opponent = _combatant("Player", attack=4, defense=5, current_hp=100)
    first = ActionDefinition(kind=ActionKind.STRUGGLE)
    second = ActionDefinition(kind=ActionKind.STRUGGLE)
    ai = GreedyAI(t=t, rng=random.Random(42), distance_from_turf=0.0)
    samples = 4000

    first_picks = sum(1 for _ in range(samples) if ai.choose(actor, opponent, [first, second]) is first)

    expected_ratio = 1 / (1 + t)
    assert abs(first_picks / samples - expected_ratio) < 0.05


class _CountingRandom(random.Random):
    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.draws = 0

    def random(self) -> float:
        self.draws += 1
        return super().random()


def test_greedy_ai_scoring_draws_nothing_beyond_its_weighted_pick() -> None:
    actor = _combatant("Enemy", attack=10, defense=5)
    opponent = _combatant("Player", attack=4, defense=5, current_hp=100)
    struggle = ActionDefinition(kind=ActionKind.STRUGGLE)
    swarm = ActionDefinition(kind=ActionKind.SWARM_ATTACK, requires_full_meter=True)
    rng = _CountingRandom(0)
    ai = GreedyAI(t=0.5, rng=rng, distance_from_turf=0.0)

    ai.choose(actor, opponent, [struggle, swarm])

    assert rng.draws == 1
