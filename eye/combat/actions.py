from dataclasses import dataclass
from enum import Enum, auto

from eye.combat.effects import EffectName
from eye.combat.stats import Combatant, Stat
from eye.combat.tuning import (
    PROXIMITY_FALLOFF_RANGE,
    STRUGGLE_BASE_POWER,
    STRUGGLE_SCALES_WITH_DISTANCE,
    SWARM_ATTACK_BASE_POWER,
    distance_falloff_scale,
)


class ActionKind(Enum):
    STRUGGLE = auto()
    SWARM_ATTACK = auto()


class EffectTarget(Enum):
    SELF = auto()
    OPPONENT = auto()


@dataclass(frozen=True, slots=True)
class InflictedEffect:
    effect: EffectName
    target: EffectTarget


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    kind: ActionKind
    name: str = ""
    hit_count: int = 1
    inflicts: tuple[InflictedEffect, ...] = ()
    requires_full_meter: bool = False


@dataclass(frozen=True, slots=True)
class HitOutcome:
    damage_to_defender: int
    recoil_to_attacker: int
    inflicted: tuple[tuple[EffectName, Combatant], ...]


def _damage_to_defender(
    attacker: Combatant,
    defender: Combatant,
    action: ActionDefinition,
    distance_from_turf: float,
    damage_multiplier: float,
) -> int:
    if action.kind is ActionKind.SWARM_ATTACK:
        base_power = SWARM_ATTACK_BASE_POWER
        scale = distance_falloff_scale(distance_from_turf, PROXIMITY_FALLOFF_RANGE)
    else:
        base_power = STRUGGLE_BASE_POWER
        scale = (
            distance_falloff_scale(distance_from_turf, PROXIMITY_FALLOFF_RANGE)
            if STRUGGLE_SCALES_WITH_DISTANCE
            else 1.0
        )
    power = max(0.0, base_power + attacker.effective(Stat.ATTACK))
    defense = max(0.0, defender.effective(Stat.DEFENSE))
    raw = 0.0 if power == 0 else power**2 / (power + defense)
    return max(1, round(raw * scale * damage_multiplier))


def _recoil_to_attacker(attacker: Combatant, action: ActionDefinition, damage_to_defender: int) -> int:
    if action.kind is not ActionKind.STRUGGLE:
        return 0
    return round(damage_to_defender * attacker.effective(Stat.RECOIL))


def _resolve_target(target: EffectTarget, attacker: Combatant, defender: Combatant) -> Combatant:
    return attacker if target is EffectTarget.SELF else defender


def resolve_hit(
    attacker: Combatant,
    defender: Combatant,
    action: ActionDefinition,
    *,
    distance_from_turf: float,
    damage_multiplier: float = 1.0,
) -> HitOutcome:
    """Resolve one hit deterministically; `damage_multiplier` scales the raw damage before
    rounding and the 1-damage floor, and recoil derives from the resulting damage."""
    damage = _damage_to_defender(attacker, defender, action, distance_from_turf, damage_multiplier)
    recoil = _recoil_to_attacker(attacker, action, damage)
    inflicted = tuple(
        (inflicted_effect.effect, _resolve_target(inflicted_effect.target, attacker, defender))
        for inflicted_effect in action.inflicts
    )
    return HitOutcome(damage_to_defender=damage, recoil_to_attacker=recoil, inflicted=inflicted)
