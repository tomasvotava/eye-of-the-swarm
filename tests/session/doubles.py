import random
from collections.abc import Sequence
from typing import TypeVar

from eye.combat.actions import ActionDefinition
from eye.combat.stats import Combatant
from eye.exploration.encounters import EncounterKind

_T = TypeVar("_T")


class ScriptedEncounterRandom(random.Random):
    """Deterministic random.Random stand-in for the encounter-kind draw only. Every scenario in
    this package gives each combat side exactly one available action, so the choices() calls
    GreedyAI makes during battle are already deterministic on a real Random -- only the
    encounter-kind pick (population of several weighted EncounterKind members) needs scripting.

    Dispatch is by population content (an EncounterKind population vs. GreedyAI's ActionDefinition
    population), not by whether the queue happens to be empty -- load-bearing, not just defensive:
    a kind_queue with items still pending for a later advance() must not have those items stolen
    by an in-between battle's own choices() calls. Raises once queued kinds run out, matching
    ScriptedChooser's (eye/combat/ai.py) raise-on-exhaustion precedent, rather than silently
    falling through to unseeded randomness for an encounter-kind draw."""

    def __init__(self, kind_queue: Sequence[EncounterKind]) -> None:
        super().__init__()
        self._kind_queue = list(kind_queue)

    def choices(  # type: ignore[override]
        self,
        population: Sequence[_T],
        weights: Sequence[float] | None = None,
        *,
        cum_weights: Sequence[float] | None = None,
        k: int = 1,
    ) -> list[_T]:
        if population and isinstance(population[0], EncounterKind):
            if not self._kind_queue:
                raise IndexError("ScriptedEncounterRandom has no more queued encounter kinds")
            kind = self._kind_queue.pop(0)
            return [kind]  # type: ignore[list-item]
        return super().choices(population, weights, cum_weights=cum_weights, k=k)


class FirstActionChooser:
    def choose(self, actor: Combatant, opponent: Combatant, available: Sequence[ActionDefinition]) -> ActionDefinition:
        return available[0]
