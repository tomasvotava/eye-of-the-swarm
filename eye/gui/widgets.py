"""Compound widget seam for buff/debuff and skill-tree-node display (ADR 0009). Both `BuffIcon`
and `SkillTreeLeaf` are `Protocol`s so an art epic can swap in a richer implementation (icon +
text + state styling) at each scene's factory call site without touching scene code.
`SpriteBuffIcon` (ADR 0011) is `CombatScene`'s production default; `TextBuffIcon` remains as a
plain-text fallback/test double. `TextSkillTreeLeaf` is still `SkillTreeLeaf`'s only
implementation -- its own art epic hasn't landed yet.
"""

from collections.abc import Mapping
from enum import Enum, auto
from typing import Protocol, assert_never

import pygame

from eye.combat.effects import EFFECT_POLARITY, EffectName, EffectPolarity
from eye.gui.assets import SpriteAtlas, SpriteKey
from eye.gui.fonts.fonts import GameFont, get_font
from eye.skilltree.tree import SkillNode

_FONT_SIZE = 16
_BUFF_COLOR: pygame.typing.ColorLike = "mediumseagreen"
_DEBUFF_COLOR: pygame.typing.ColorLike = "indianred"
_LOCKED_COLOR: pygame.typing.ColorLike = "dimgray"
_AVAILABLE_COLOR: pygame.typing.ColorLike = "gold"
_PURCHASED_COLOR: pygame.typing.ColorLike = "limegreen"


class BuffIcon(Protocol):
    def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None: ...


class NonEffectIcon(Enum):
    """An icon subject with no `EffectName` behind it to name it by."""

    RECOIL = auto()


# Everything a scene's icon factory can be asked to resolve, effect or not.
type IconSource = EffectName | NonEffectIcon


class SkillNodeState(Enum):
    LOCKED = auto()  # prerequisite tier missing, or too few spores
    AVAILABLE = auto()  # not yet purchased, but purchasable now
    PURCHASED = auto()


class SkillTreeLeaf(Protocol):
    def render(self, surface: pygame.Surface, rect: pygame.Rect, node: SkillNode, state: SkillNodeState) -> None: ...


def effect_label(effect: EffectName) -> str:
    return effect.name.replace("_", " ").title()


# PROJECT_BRIEF.md §9.7: a short, functional description of what each effect does, distinct from
# its flavor name (`effect_label`).
EFFECT_DESCRIPTIONS: Mapping[EffectName, str] = {
    EffectName.TOXICITY: "Lowers HP after every turn",
    EffectName.NOURISHED: "Heals a little each turn",
    EffectName.CLOUDED_JUDGEMENT: "Confuses the next action",
    EffectName.LIGNEOUS_PERIDERM: "Raises defense",
    EffectName.SPLINTERED: "Lowers defense",
    EffectName.SPIKY_SKIN: "Reflects some damage back at the attacker",
    EffectName.ADRENALINE: "Revives once on death with Fibrous effect",
    EffectName.FIBROUS: "Raises attack",
    EffectName.RUNT: "Lowers attack",
    EffectName.UPROOTED: "May grant an extra action",
    EffectName.WILTY: "May cause sudden death",
    EffectName.VEGETATIVE: "May skip the turn",
    EffectName.RESONANCE: "Primes the next battle's meter",
}


class TextBuffIcon:
    """Plain-text `BuffIcon` for an effect, coloured by its polarity. Effect-only on purpose: a
    non-effect subject has no polarity to colour by."""

    def __init__(self, effect: EffectName) -> None:
        self.effect = effect

    def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
        color = _BUFF_COLOR if EFFECT_POLARITY[self.effect] is EffectPolarity.BUFF else _DEBUFF_COLOR
        surface.blit(get_font(GameFont.ITHACA, _FONT_SIZE).render(effect_label(self.effect), True, color), pos)


def _sprite_key_for(source: IconSource) -> SpriteKey:
    match source:
        case EffectName.TOXICITY:
            return SpriteKey.EFFECT_TOXICITY
        case EffectName.NOURISHED:
            return SpriteKey.EFFECT_NOURISHED
        case EffectName.CLOUDED_JUDGEMENT:
            return SpriteKey.EFFECT_CLOUDED_JUDGEMENT
        case EffectName.LIGNEOUS_PERIDERM:
            return SpriteKey.EFFECT_LIGNEOUS_PERIDERM
        case EffectName.SPLINTERED:
            return SpriteKey.EFFECT_SPLINTERED
        case EffectName.SPIKY_SKIN:
            return SpriteKey.EFFECT_SPIKY_SKIN
        case EffectName.ADRENALINE:
            return SpriteKey.EFFECT_ADRENALINE
        case EffectName.FIBROUS:
            return SpriteKey.EFFECT_FIBROUS
        case EffectName.RUNT:
            return SpriteKey.EFFECT_RUNT
        case EffectName.UPROOTED:
            return SpriteKey.EFFECT_UPROOTED
        case EffectName.WILTY:
            return SpriteKey.EFFECT_WILTY
        case EffectName.VEGETATIVE:
            return SpriteKey.EFFECT_VEGETATIVE
        case EffectName.RESONANCE:
            return SpriteKey.EFFECT_RESONANCE
        case NonEffectIcon.RECOIL:
            return SpriteKey.ICON_RECOIL
        case _:
            assert_never(source)


class SpriteBuffIcon:
    """`BuffIcon` backed by real art (ADR 0011) -- `CombatScene`'s default `buff_icon_factory`."""

    def __init__(self, atlas: SpriteAtlas, source: IconSource) -> None:
        self._surface = atlas.get(_sprite_key_for(source))
        # A caller may render the same icon at more than one size (CombatScene's HUD row and
        # Announcement card differ) -- cached per size after first use, since an icon instance is
        # built once per subject and reused across frames (see CombatScene's default factory),
        # rather than rescaled on every render() call (eye/gui/animation.py's scale_sprite
        # docstring: nothing is gained by recomputing a fixed scale every frame).
        self._scaled: dict[int, pygame.Surface] = {}

    def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
        scaled = self._scaled.get(size)
        if scaled is None:
            scaled = pygame.transform.smoothscale(self._surface, (size, size))
            self._scaled[size] = scaled
        surface.blit(scaled, pos)


_STATE_COLORS: dict[SkillNodeState, pygame.typing.ColorLike] = {
    SkillNodeState.LOCKED: _LOCKED_COLOR,
    SkillNodeState.AVAILABLE: _AVAILABLE_COLOR,
    SkillNodeState.PURCHASED: _PURCHASED_COLOR,
}


class TextSkillTreeLeaf:
    def render(self, surface: pygame.Surface, rect: pygame.Rect, node: SkillNode, state: SkillNodeState) -> None:
        surface.blit(
            get_font(GameFont.ITHACA, _FONT_SIZE).render(f"{node.name} ({node.cost})", True, _STATE_COLORS[state]),
            rect.topleft,
        )
