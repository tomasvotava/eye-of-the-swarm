import math
import random
from collections.abc import Sequence
from typing import assert_never

from eye.character import Character
from eye.exploration.encounters import (
    Biome,
    EffectPickupEncounter,
    EncounterGenerator,
    EnemyEncounter,
    NothingEncounter,
    ResourceKind,
    ResourcePickupEncounter,
)
from eye.exploration.events import (
    EffectGranted,
    EnemyEncountered,
    ExplorationEvent,
    NothingHappened,
    ResourceGranted,
    SeedGrew,
    SeedPlanted,
)
from eye.exploration.tuning import SEED_GROWTH_THRESHOLD, seed_growth_rate

_CURRENT_BIOME = Biome.BRAMBEROSITY  # v1's only Biome; selection isn't wired in yet (see encounters.py)


class ExplorationRun:
    def __init__(
        self,
        character: Character,
        rng: random.Random,
        starting_screen: int,
        matured_turfs: Sequence[int],
    ) -> None:
        self._character = character
        self._generator = EncounterGenerator(rng)
        self._current_screen = starting_screen
        self._matured_turfs = tuple(matured_turfs)
        self._pending_seeds: tuple[int, ...] = ()
        self._seed_meter = 0.0
        self._spores_gained = 0
        self._proximity_discount = 0.0

    def advance(self) -> list[ExplorationEvent]:
        events: list[ExplorationEvent] = []
        self._current_screen += 1
        events.append(self._grow_seed(seed_growth_rate(self.distance_to_nearest_seed)))

        encounter = self._generator.generate()
        match encounter:
            case EnemyEncounter(strain=strain):
                events.append(EnemyEncountered(strain=strain, biome=_CURRENT_BIOME))
            case EffectPickupEncounter(effect=effect):
                self._character.effects.apply(effect)
                events.append(EffectGranted(effect=effect.name))
            case ResourcePickupEncounter(resource=resource, magnitude=magnitude):
                seed_grew = self._apply_resource(resource, magnitude)
                events.append(ResourceGranted(kind=resource, amount=magnitude))
                if seed_grew is not None:
                    events.append(seed_grew)
            case NothingEncounter():
                events.append(NothingHappened())
            case _:
                assert_never(encounter)
        return events

    def plant_seed(self) -> list[ExplorationEvent]:
        if not self.is_seed_ready:
            raise RuntimeError("seed is not fully grown yet")
        self._pending_seeds = (*self._pending_seeds, self._current_screen)
        self._seed_meter = 0.0
        return [SeedPlanted(position=self._current_screen)]

    @property
    def is_seed_ready(self) -> bool:
        return self._seed_meter >= SEED_GROWTH_THRESHOLD

    @property
    def distance_to_nearest_seed(self) -> float:
        seed_positions = (*self._matured_turfs, *self._pending_seeds)
        if not seed_positions:
            return math.inf
        return float(self._current_screen - max(seed_positions))

    @property
    def distance_to_nearest_matured_turf(self) -> float:
        if not self._matured_turfs:
            return math.inf
        raw = self._current_screen - max(self._matured_turfs) - self._proximity_discount
        return max(0.0, raw)

    @property
    def pending_seeds(self) -> tuple[int, ...]:
        return self._pending_seeds

    @property
    def spores_gained(self) -> int:
        return self._spores_gained

    def _grow_seed(self, amount: float) -> SeedGrew:
        self._seed_meter += amount
        return SeedGrew(amount=amount, meter_after=self._seed_meter)

    def _apply_resource(self, resource: ResourceKind, magnitude: int) -> SeedGrew | None:
        match resource:
            case ResourceKind.HEAL:
                self._character.current_hp = min(self._character.max_hp, self._character.current_hp + magnitude)
                return None
            case ResourceKind.SPORES:
                self._spores_gained += magnitude
                return None
            case ResourceKind.SEED_GROWTH:
                return self._grow_seed(float(magnitude))
            case ResourceKind.DISTANCE_DISCOUNT:
                self._proximity_discount += magnitude
                return None
            case _:
                assert_never(resource)
