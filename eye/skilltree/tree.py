from dataclasses import dataclass
from enum import Enum, auto

from eye.combat.actions import ActionDefinition
from eye.combat.effects import EffectName


class Branch(Enum):
    SELF = auto()
    SWARM = auto()


class SubBranch(Enum):
    ATTACK = auto()
    DEFENSE = auto()
    UTILITY = auto()


@dataclass(frozen=True, slots=True)
class SkillNodeId:
    branch: Branch
    sub_branch: SubBranch
    tier: int  # 0-indexed; prerequisite is tier-1 in the same (branch, sub_branch), tier 0 has none


@dataclass(frozen=True, slots=True)
class StatsDelta:
    max_hp: int = 0
    attack: int = 0
    defense: int = 0
    recoil: float = 0.0
    meter_capacity: int = 0
    meter_fill_rate: int = 0


@dataclass(frozen=True, slots=True)
class ExplorationModifierDelta:
    seed_growth_rate_multiplier: float = 1.0  # neutral element 1.0; nodes combine multiplicatively
    proximity_discount_bonus: float = 0.0  # neutral element 0.0; nodes combine additively


@dataclass(frozen=True, slots=True)
class SkillNode:
    id: SkillNodeId
    cost: int
    name: str = ""
    stats_delta: StatsDelta = StatsDelta()
    lifespan_effects: tuple[EffectName, ...] = ()
    unlocked_actions: tuple[ActionDefinition, ...] = ()
    exploration_modifier: ExplorationModifierDelta = ExplorationModifierDelta()
