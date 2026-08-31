from dataclasses import dataclass

from eye.combat.events import BattleEvent
from eye.exploration.events import ExplorationEvent


@dataclass(frozen=True, slots=True)
class GenerationEnded:
    pass


type SessionEvent = ExplorationEvent | BattleEvent | GenerationEnded
