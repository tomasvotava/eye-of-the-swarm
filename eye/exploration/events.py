from dataclasses import dataclass

from eye.combat.effects import EffectName
from eye.exploration.encounters import Biome, ResourceKind, Strain


@dataclass(frozen=True, slots=True)
class EnemyEncountered:
    strain: Strain
    biome: Biome


@dataclass(frozen=True, slots=True)
class EffectGranted:
    effect: EffectName


@dataclass(frozen=True, slots=True)
class ResourceGranted:
    kind: ResourceKind
    amount: int


@dataclass(frozen=True, slots=True)
class NothingHappened:
    pass


@dataclass(frozen=True, slots=True)
class SeedGrew:
    amount: float
    meter_after: float


@dataclass(frozen=True, slots=True)
class SeedPlanted:
    position: int


type ExplorationEvent = EnemyEncountered | EffectGranted | ResourceGranted | NothingHappened | SeedGrew | SeedPlanted
