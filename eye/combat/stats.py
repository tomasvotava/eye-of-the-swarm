from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from eye.combat.actions import ActionDefinition
    from eye.combat.effects import ActiveEffect, EffectName


class Stat(Enum):
    ATTACK = auto()
    DEFENSE = auto()
    RECOIL = auto()


class EffectSource(Protocol):
    """Port for whatever holds/queries active effect state (`eye.combat.effects.EffectRegistry`)."""

    def modifier(self, stat: Stat) -> float: ...
    def has(self, name: EffectName) -> bool: ...
    def apply(self, effect: ActiveEffect) -> None: ...


class _NoEffects:
    def modifier(self, stat: Stat) -> float:
        return 0.0

    def has(self, name: EffectName) -> bool:
        return False

    def apply(self, effect: ActiveEffect) -> None:
        pass


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
    effects: EffectSource = field(default_factory=_NoEffects)
    available_actions: Sequence[ActionDefinition] = ()

    def effective(self, stat: Stat) -> float:
        base = {
            Stat.ATTACK: self.base_stats.attack,
            Stat.DEFENSE: self.base_stats.defense,
            Stat.RECOIL: self.base_stats.recoil,
        }[stat]
        return base + self.effects.modifier(stat)
