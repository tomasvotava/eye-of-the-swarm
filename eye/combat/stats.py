from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol


class Stat(Enum):
    ATTACK = auto()
    DEFENSE = auto()
    RECOIL = auto()


class ModifierSource(Protocol):
    """Port for whatever supplies active stat modifiers (`eye.combat.effects.EffectRegistry`)."""

    def modifier(self, stat: Stat) -> float: ...


class _NoModifiers:
    def modifier(self, stat: Stat) -> float:
        return 0.0


@dataclass(frozen=True, slots=True)
class Stats:
    max_hp: int
    attack: int
    defense: int
    meter_capacity: int
    meter_fill_rate: int
    recoil: float = 0.0


@dataclass(slots=True)
class Combatant:
    name: str
    base_stats: Stats
    current_hp: int
    current_meter: int = 0
    is_player: bool = False
    effects: ModifierSource = field(default_factory=_NoModifiers)
    available_actions: Sequence[object] = ()  # TODO(#7): eye.combat.actions.ActionDefinition

    def effective(self, stat: Stat) -> float:
        base = {
            Stat.ATTACK: self.base_stats.attack,
            Stat.DEFENSE: self.base_stats.defense,
            Stat.RECOIL: self.base_stats.recoil,
        }[stat]
        return base + self.effects.modifier(stat)
