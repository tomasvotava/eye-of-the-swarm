import random
from collections.abc import Sequence
from typing import TypeVar

from eye.combat.actions import ActionDefinition
from eye.exploration.encounters import EncounterKind, Strain
from eye.exploration.events import EnemyEncountered
from eye.session.events import SessionEvent
from eye.session.generation import Generation
from tests.combat.support import unfold

_T = TypeVar("_T")


def _pick_first_action(available: Sequence[ActionDefinition]) -> ActionDefinition:
    return available[0]


def advance_flat(generation: Generation) -> list[SessionEvent]:
    """Advance one screen; if it surfaces an enemy, drive that battle to completion picking the
    first available action for every player swing, then finish it -- a fixed choice, mirroring
    this package's other deterministic test doubles."""
    events: list[SessionEvent] = list(generation.advance())
    encounter = next((event for event in events if isinstance(event, EnemyEncountered)), None)
    if encounter is not None:
        battle = generation.start_battle(encounter)
        events.extend(battle.start())
        events.extend(unfold(battle, _pick_first_action))
        events.extend(generation.finish_battle(battle))
    return events


class ScriptedEncounterRandom(random.Random):
    """Deterministic random.Random stand-in for the encounter-kind and (optionally) Strain draws.
    GreedyAI's own choices() calls during battle (picking among an actor's available actions) are
    left to a real, fixed-seed random.Random -- scripting those isn't needed by any scenario in
    this package today.

    Dispatch is by population content (an EncounterKind/Strain population vs. GreedyAI's
    ActionDefinition population), not by whether a queue happens to be empty -- load-bearing, not
    just defensive: a queue with items still pending for a later draw must not have those items
    stolen by an in-between battle's own choices() calls. Both queues raise once exhausted,
    matching ScriptedChooser's (eye/combat/ai.py) raise-on-exhaustion precedent, rather than
    silently falling through to unscripted randomness for a draw the caller meant to control.

    strain_queue is optional: most scenarios don't care which of ENCOUNTERABLE_STRAINS they face
    and can leave it unscripted (falls through to the seeded real random.Random). A scenario that
    needs a specific matchup -- e.g. one winnable by an unmodified base-stat player -- passes the
    Strains it wants by name instead of hand-picking a seed that happens to produce them."""

    def __init__(self, kind_queue: Sequence[EncounterKind], strain_queue: Sequence[Strain] = (), seed: int = 0) -> None:
        super().__init__(seed)
        self._kind_queue = list(kind_queue)
        self._strain_queue = list(strain_queue)
        # Unlike kind_queue (every EncounterKind draw is always scripted), a Strain draw is only
        # scripted when the caller actually opted in -- an empty strain_queue means "don't care,
        # use the seeded real random.Random", not "raise on the first draw".
        self._strain_scripting_enabled = bool(strain_queue)

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

    def choice(self, seq: Sequence[_T]) -> _T:  # type: ignore[override]
        if self._strain_scripting_enabled and seq and isinstance(seq[0], Strain):
            if not self._strain_queue:
                raise IndexError("ScriptedEncounterRandom has no more queued Strains")
            return self._strain_queue.pop(0)  # type: ignore[return-value]
        return super().choice(seq)
