"""Compound widget seam for buff/debuff and skill-tree-node display (ADR 0009). Both `BuffIcon`
and `SkillTreeLeaf` are `Protocol`s so a future art epic can swap in a richer implementation
(icon + text + state styling) at each scene's factory call site without touching scene code.
`TextBuffIcon`/`TextSkillTreeLeaf` are this epic's only implementations, drawing plain text.
"""

from typing import Protocol

import pygame

from eye.combat.effects import EFFECT_POLARITY, EffectName, EffectPolarity
from eye.skilltree.tree import SkillNode

_FONT_SIZE = 20
_BUFF_COLOR: pygame.typing.ColorLike = "mediumseagreen"
_DEBUFF_COLOR: pygame.typing.ColorLike = "indianred"
_LOCKED_COLOR: pygame.typing.ColorLike = "dimgray"
_UNLOCKED_COLOR: pygame.typing.ColorLike = "gold"

_font: pygame.font.Font | None = None


def _get_font() -> pygame.font.Font:
    # Constructed lazily rather than at import time: pygame.font must already be initialized,
    # which module import order doesn't guarantee. Cached after that so per-frame render() calls
    # reuse one Font instead of rebuilding it every call.
    global _font
    if _font is None:
        _font = pygame.font.Font(None, _FONT_SIZE)
    return _font


class BuffIcon(Protocol):
    def render(self, surface: pygame.Surface, pos: pygame.Vector2) -> None: ...


class SkillTreeLeaf(Protocol):
    def render(self, surface: pygame.Surface, rect: pygame.Rect, node: SkillNode, locked: bool) -> None: ...


def _effect_label(effect: EffectName) -> str:
    return effect.name.replace("_", " ").title()


class TextBuffIcon:
    def __init__(self, effect: EffectName) -> None:
        self.effect = effect

    def render(self, surface: pygame.Surface, pos: pygame.Vector2) -> None:
        color = _BUFF_COLOR if EFFECT_POLARITY[self.effect] is EffectPolarity.BUFF else _DEBUFF_COLOR
        surface.blit(_get_font().render(_effect_label(self.effect), True, color), pos)


class TextSkillTreeLeaf:
    def render(self, surface: pygame.Surface, rect: pygame.Rect, node: SkillNode, locked: bool) -> None:
        color = _LOCKED_COLOR if locked else _UNLOCKED_COLOR
        surface.blit(_get_font().render(f"{node.name} ({node.cost})", True, color), rect.topleft)
