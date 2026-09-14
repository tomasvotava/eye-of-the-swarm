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
    STRAIN_MIN_DISTANCE_BEATLE,
    STRAIN_MIN_DISTANCE_FLEA,
    STRAIN_MIN_DISTANCE_GOLEM,
    STRAIN_MIN_DISTANCE_PHIDIZVIK,
    STRAIN_MIN_DISTANCE_TUMBLEWEED,
)


class EncounterKind(Enum):
    ENEMY = auto()
    EFFECT_PICKUP = auto()
    RESOURCE_PICKUP = auto()
    NOTHING = auto()


class Strain(Enum):
    BRAMBLE = auto()  # test-fixture only -- kept out of ENCOUNTERABLE_STRAINS, never spawned live
    BEATLE = auto()
    FLEA = auto()
    GOLEM = auto()
    PHIDIZVIK = auto()
    TUMBLEWEED = auto()


# The distance_from_home (screens walked this generation, eye/exploration/run.py) below which a
# Strain never spawns -- keeps GOLEM/PHIDIZVIK, sized for deep exploration, out of a life's opening
# screens. Also doubles as the Strains EncounterGenerator actually spawns (ENCOUNTERABLE_STRAINS,
# below) -- one table, so the two can't drift out of sync with each other.
STRAIN_MIN_DISTANCE: dict[Strain, int] = {
    Strain.BEATLE: STRAIN_MIN_DISTANCE_BEATLE,
    Strain.FLEA: STRAIN_MIN_DISTANCE_FLEA,
    Strain.GOLEM: STRAIN_MIN_DISTANCE_GOLEM,
    Strain.PHIDIZVIK: STRAIN_MIN_DISTANCE_PHIDIZVIK,
    Strain.TUMBLEWEED: STRAIN_MIN_DISTANCE_TUMBLEWEED,
}

# Excludes BRAMBLE, which stays in the Strain enum/BESTIARY purely so existing fixtures/tests keep
# a stub archetype with no sprite art to exercise against.
ENCOUNTERABLE_STRAINS: tuple[Strain, ...] = tuple(STRAIN_MIN_DISTANCE)


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

    def generate(self, distance_from_home: int) -> Encounter:
        kinds = list(_ENCOUNTER_KIND_WEIGHTS)
        weights = [_ENCOUNTER_KIND_WEIGHTS[kind] for kind in kinds]
        kind = self._rng.choices(kinds, weights=weights, k=1)[0]
        match kind:
            case EncounterKind.ENEMY:
                available = tuple(
                    strain for strain in ENCOUNTERABLE_STRAINS if STRAIN_MIN_DISTANCE[strain] <= distance_from_home
                )
                return EnemyEncounter(strain=self._rng.choice(available))
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
