from dataclasses import dataclass, field

from eye.combat.effects import EffectRegistry


@dataclass(slots=True)
class Character:
    current_hp: int
    max_hp: int
    effects: EffectRegistry = field(default_factory=EffectRegistry)
