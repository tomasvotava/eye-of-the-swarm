"""Compound widget seam for buff/debuff and skill-tree-node display (ADR 0009). Both `BuffIcon`
and `SkillTreeLeaf` are `Protocol`s so a future art epic can swap in a richer implementation
(icon + text + state styling) at each scene's factory call site without touching scene code.
`TextBuffIcon`/`TextSkillTreeLeaf` are this epic's only implementations, drawing plain text.
"""

from enum import Enum, auto
from typing import Protocol

import pygame

from eye.combat.effects import EFFECT_POLARITY, EffectName, EffectPolarity
from eye.gui.fonts.fonts import GameFont, get_font
from eye.skilltree.tree import SkillNode

_FONT_SIZE = 16
_BUFF_COLOR: pygame.typing.ColorLike = "mediumseagreen"
_DEBUFF_COLOR: pygame.typing.ColorLike = "indianred"
_LOCKED_COLOR: pygame.typing.ColorLike = "dimgray"
_AVAILABLE_COLOR: pygame.typing.ColorLike = "gold"
_PURCHASED_COLOR: pygame.typing.ColorLike = "limegreen"


class BuffIcon(Protocol):
    def render(self, surface: pygame.Surface, pos: pygame.Vector2) -> None: ...


class SkillNodeState(Enum):
    LOCKED = auto()  # prerequisite tier missing, or too few spores
    AVAILABLE = auto()  # not yet purchased, but purchasable now
    PURCHASED = auto()


class SkillTreeLeaf(Protocol):
    def render(self, surface: pygame.Surface, rect: pygame.Rect, node: SkillNode, state: SkillNodeState) -> None: ...


def _effect_label(effect: EffectName) -> str:
    return effect.name.replace("_", " ").title()


class TextBuffIcon:
    def __init__(self, effect: EffectName) -> None:
        self.effect = effect

    def render(self, surface: pygame.Surface, pos: pygame.Vector2) -> None:
        color = _BUFF_COLOR if EFFECT_POLARITY[self.effect] is EffectPolarity.BUFF else _DEBUFF_COLOR
        surface.blit(get_font(GameFont.ITHACA, _FONT_SIZE).render(_effect_label(self.effect), True, color), pos)


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
