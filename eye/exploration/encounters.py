import random
from dataclasses import dataclass
from enum import Enum, auto
from typing import assert_never

from eye.combat.effects import ActiveEffect, EffectCategory, EffectName
from eye.exploration.tuning import (
    ENCOUNTER_KIND_WEIGHT_EFFECT_PICKUP,
    ENCOUNTER_KIND_WEIGHT_ENEMY,
    ENCOUNTER_KIND_WEIGHT_NOTHING,
    ENCOUNTER_KIND_WEIGHT_RESOURCE_PICKUP,
    RESOURCE_DISTANCE_DISCOUNT_MAGNITUDE,
    RESOURCE_HEAL_MAGNITUDE,
    RESOURCE_SEED_GROWTH_MAGNITUDE,
    RESOURCE_SPORES_MAGNITUDE,
)


class EncounterKind(Enum):
    ENEMY = auto()
    EFFECT_PICKUP = auto()
    RESOURCE_PICKUP = auto()
    NOTHING = auto()


class Strain(Enum):
    BRAMBLE = auto()  # v1's single archetype; more join later without restructuring


class Biome(Enum):
    BRAMBEROSITY = auto()  # v1's single zone; segmentation (PROJECT_BRIEF.md §8) joins later


class ResourceKind(Enum):
    HEAL = auto()
    SPORES = auto()
    SEED_GROWTH = auto()
    DISTANCE_DISCOUNT = auto()


_ENCOUNTER_KIND_WEIGHTS: dict[EncounterKind, float] = {
    EncounterKind.ENEMY: ENCOUNTER_KIND_WEIGHT_ENEMY,
    EncounterKind.EFFECT_PICKUP: ENCOUNTER_KIND_WEIGHT_EFFECT_PICKUP,
    EncounterKind.RESOURCE_PICKUP: ENCOUNTER_KIND_WEIGHT_RESOURCE_PICKUP,
    EncounterKind.NOTHING: ENCOUNTER_KIND_WEIGHT_NOTHING,
}

_RESOURCE_MAGNITUDES: dict[ResourceKind, int] = {
    ResourceKind.HEAL: RESOURCE_HEAL_MAGNITUDE,
    ResourceKind.SPORES: RESOURCE_SPORES_MAGNITUDE,
    ResourceKind.SEED_GROWTH: RESOURCE_SEED_GROWTH_MAGNITUDE,
    ResourceKind.DISTANCE_DISCOUNT: RESOURCE_DISTANCE_DISCOUNT_MAGNITUDE,
}


@dataclass(frozen=True, slots=True)
class EnemyEncounter:
    strain: Strain


@dataclass(frozen=True, slots=True)
class EffectPickupEncounter:
    effect: ActiveEffect


@dataclass(frozen=True, slots=True)
class ResourcePickupEncounter:
    resource: ResourceKind
    magnitude: int


@dataclass(frozen=True, slots=True)
class NothingEncounter:
    pass


type Encounter = EnemyEncounter | EffectPickupEncounter | ResourcePickupEncounter | NothingEncounter


class EncounterGenerator:
    def __init__(self, rng: random.Random) -> None:
        self._rng = rng

    def generate(self) -> Encounter:
        kinds = list(_ENCOUNTER_KIND_WEIGHTS)
        weights = [_ENCOUNTER_KIND_WEIGHTS[kind] for kind in kinds]
        kind = self._rng.choices(kinds, weights=weights, k=1)[0]
        match kind:
            case EncounterKind.ENEMY:
                return EnemyEncounter(strain=self._rng.choice(list(Strain)))
            case EncounterKind.EFFECT_PICKUP:
                name = self._rng.choice(list(EffectName))
                return EffectPickupEncounter(effect=ActiveEffect(name, EffectCategory.LIFESPAN, remaining_turns=None))
            case EncounterKind.RESOURCE_PICKUP:
                resource = self._rng.choice(list(ResourceKind))
                return ResourcePickupEncounter(resource=resource, magnitude=_RESOURCE_MAGNITUDES[resource])
            case EncounterKind.NOTHING:
                return NothingEncounter()
            case _:
                assert_never(kind)
