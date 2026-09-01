import random
from collections.abc import Sequence
from typing import Protocol

from eye.combat.actions import ActionDefinition, resolve_hit
from eye.combat.effects import EffectName
from eye.combat.stats import Combatant
from eye.combat.tuning import AI_LETHAL_SCORE_BONUS


class ActionChooser(Protocol):
    def choose(
        self, actor: Combatant, opponent: Combatant, available: Sequence[ActionDefinition]
    ) -> ActionDefinition: ...


class ScriptedChooser:
    """Pre-queued action stand-in for the enemy side in tests, in place of GreedyAI's randomized
    choice -- the player no longer goes through any ActionChooser (see ADR 0008)."""

    def __init__(self, queue: Sequence[ActionDefinition]) -> None:
        self._queue = list(queue)

    def choose(self, actor: Combatant, opponent: Combatant, available: Sequence[ActionDefinition]) -> ActionDefinition:
        if not self._queue:
            raise IndexError("ScriptedChooser has no more queued actions")
        return self._queue.pop(0)


class GreedyAI:
    def __init__(self, t: float, rng: random.Random, distance_from_turf: float) -> None:
        self._t = t
        self._rng = rng
        self._distance_from_turf = distance_from_turf

    def choose(self, actor: Combatant, opponent: Combatant, available: Sequence[ActionDefinition]) -> ActionDefinition:
        ranked = sorted(available, key=lambda action: self._score(actor, opponent, action), reverse=True)
        if len(ranked) > 1 and actor.effects.has(EffectName.CLOUDED_JUDGEMENT):
            ranked = ranked[1:]
        weights = [self._t**k for k in range(len(ranked))]
        return self._rng.choices(ranked, weights=weights, k=1)[0]

    def _score(self, actor: Combatant, opponent: Combatant, action: ActionDefinition) -> float:
        damage_to_opponent, self_damage_taken, lethal = self._simulate(actor, opponent, action)
        # No current ActionDefinition grants immediate healing -- Nourished heals via
        # DotTicked/HealApplied ticks, not resolve_hit -- so self_heal_gained is always 0.
        lethal_bonus = AI_LETHAL_SCORE_BONUS if lethal and not opponent.effects.has(EffectName.ADRENALINE) else 0.0
        return damage_to_opponent - self_damage_taken + lethal_bonus

    def _simulate(self, actor: Combatant, opponent: Combatant, action: ActionDefinition) -> tuple[int, int, bool]:
        outcome = resolve_hit(actor, opponent, action, distance_from_turf=self._distance_from_turf)
        remaining_hp = opponent.current_hp
        total_damage = 0
        total_recoil = 0
        lethal = False
        for _ in range(action.hit_count):
            if remaining_hp <= 0:
                break
            total_damage += outcome.damage_to_defender
            total_recoil += outcome.recoil_to_attacker
            remaining_hp -= outcome.damage_to_defender
            if remaining_hp <= 0:
                lethal = True
                break
        return total_damage, total_recoil, lethal
