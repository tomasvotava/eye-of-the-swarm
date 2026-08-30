from dataclasses import dataclass
from enum import Enum, auto

from eye.combat.stats import Stat
from eye.combat.tuning import (
    FIBROUS_ATTACK_MAGNITUDE,
    LIGNEOUS_PERIDERM_DEFENSE_MAGNITUDE,
    RUNT_ATTACK_MAGNITUDE,
    SPLINTERED_DEFENSE_MAGNITUDE,
)


class EffectCategory(Enum):
    LIFESPAN = auto()
    BATTLE = auto()


class EffectName(Enum):
    TOXICITY = auto()
    NOURISHED = auto()
    CLOUDED_JUDGEMENT = auto()
    LIGNEOUS_PERIDERM = auto()
    SPLINTERED = auto()
    SPIKY_SKIN = auto()
    ADRENALINE = auto()
    FIBROUS = auto()
    RUNT = auto()
    UPROOTED = auto()
    WILTY = auto()
    VEGETATIVE = auto()


# Trigger-type effects (Toxicity, Nourished, Spiky Skin, Adrenaline, Clouded Judgement,
# Uprooted, Wilty, Vegetative) carry no entry here — Battle checks them via has().
_STAT_MODIFIERS: dict[EffectName, tuple[Stat, float]] = {
    EffectName.FIBROUS: (Stat.ATTACK, FIBROUS_ATTACK_MAGNITUDE),
    EffectName.RUNT: (Stat.ATTACK, RUNT_ATTACK_MAGNITUDE),
    EffectName.LIGNEOUS_PERIDERM: (Stat.DEFENSE, LIGNEOUS_PERIDERM_DEFENSE_MAGNITUDE),
    EffectName.SPLINTERED: (Stat.DEFENSE, SPLINTERED_DEFENSE_MAGNITUDE),
}


@dataclass(slots=True)
class ActiveEffect:
    name: EffectName
    category: EffectCategory
    remaining_turns: int | None  # None = until battle ends / generation ends


class EffectRegistry:
    def __init__(self) -> None:
        self._active: dict[tuple[EffectCategory, EffectName], ActiveEffect] = {}

    def apply(self, effect: ActiveEffect) -> None:
        self._active[effect.category, effect.name] = effect

    def modifier(self, stat: Stat) -> float:
        total = 0.0
        for effect in self._active.values():
            modified_stat, magnitude = _STAT_MODIFIERS.get(effect.name, (None, 0.0))
            if modified_stat is stat:
                total += magnitude
        return total

    def has(self, name: EffectName, category: EffectCategory | None = None) -> bool:
        if category is not None:
            return (category, name) in self._active
        return any(key_name == name for _, key_name in self._active)

    def tick_battle_effects(self) -> list[EffectName]:
        expired: list[EffectName] = []
        for key, effect in list(self._active.items()):
            if effect.category is not EffectCategory.BATTLE or effect.remaining_turns is None:
                continue
            effect.remaining_turns -= 1
            if effect.remaining_turns <= 0:
                del self._active[key]
                expired.append(effect.name)
        return expired

    def clear_battle_effects(self) -> None:
        for key in [key for key in self._active if key[0] is EffectCategory.BATTLE]:
            del self._active[key]
