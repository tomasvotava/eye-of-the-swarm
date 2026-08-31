from dataclasses import dataclass

from eye.combat.events import BattleEvent
from eye.exploration.events import ExplorationEvent


@dataclass(frozen=True, slots=True)
class GenerationEnded:
    pass


@dataclass(frozen=True, slots=True)
class SeedsMatured:
    positions: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SporesAwarded:
    amount: int
    spores_available: int


type SessionEvent = ExplorationEvent | BattleEvent | GenerationEnded | SeedsMatured | SporesAwarded
