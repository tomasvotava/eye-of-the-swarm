"""The buff/debuff inspector overlay (PROJECT_BRIEF.md §9.7): every effect currently on screen, each
as its icon, flavor name and functional description, over a dimmed screen. Scenes decide when it is
up and which effects it lists; this module only draws it and names its keys."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

import pygame

from eye.combat.effects import EffectName
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.widgets import EFFECT_DESCRIPTIONS, BuffIcon, effect_label

if TYPE_CHECKING:
    import pygame.typing

LEGEND_KEY = pygame.K_l
LEGEND_CLOSE_KEYS = frozenset({LEGEND_KEY, pygame.K_ESCAPE})
LEGEND_HINT = "L: effects"

_TITLE = "Effects"
_EMPTY = "No active effects."
_FOOTER = "L or Escape: close"
_TITLE_FONT_SIZE = 28
_ROW_FONT_SIZE = 16
_FOOTER_FONT_SIZE = 14
_ICON_SIZE = 20
_ROW_HEIGHT = 26
_COLUMN_GAP = 12
_TITLE_TOP_MARGIN = 24
_FOOTER_BOTTOM_MARGIN = 24
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_BACKDROP_COLOR: pygame.typing.ColorLike = (0, 0, 0, 220)


def legend_effects(effects: Iterable[EffectName]) -> tuple[EffectName, ...]:
    """`effects` once each, in `EffectName` order: the order every buff row on screen uses."""
    present = set(effects)
    return tuple(effect for effect in EffectName if effect in present)


def draw_effect_legend(
    surface: pygame.Surface, effects: Iterable[EffectName], icon_for: Callable[[EffectName], BuffIcon]
) -> None:
    backdrop = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    backdrop.fill(_BACKDROP_COLOR)
    surface.blit(backdrop, (0, 0))

    center_x = surface.get_width() // 2
    title = get_font(GameFont.ITHACA, _TITLE_FONT_SIZE).render(_TITLE, True, _TEXT_COLOR)
    surface.blit(title, title.get_rect(midtop=(center_x, _TITLE_TOP_MARGIN)))
    rows_top = _TITLE_TOP_MARGIN + title.get_height() + _COLUMN_GAP

    font = get_font(GameFont.ITHACA, _ROW_FONT_SIZE)
    shown = legend_effects(effects)
    if not shown:
        empty = font.render(_EMPTY, True, _TEXT_COLOR)
        surface.blit(empty, empty.get_rect(midtop=(center_x, rows_top)))
    else:
        _draw_rows(surface, shown, icon_for, font, rows_top)

    footer = get_font(GameFont.ITHACA, _FOOTER_FONT_SIZE).render(_FOOTER, True, _TEXT_COLOR)
    surface.blit(footer, footer.get_rect(midbottom=(center_x, surface.get_height() - _FOOTER_BOTTOM_MARGIN)))


def _draw_rows(
    surface: pygame.Surface,
    effects: tuple[EffectName, ...],
    icon_for: Callable[[EffectName], BuffIcon],
    font: pygame.font.Font,
    top: int,
) -> None:
    # Name and description are separate columns, so descriptions line up whatever the name length.
    label_width = max(font.size(effect_label(effect))[0] for effect in effects)
    description_width = max(font.size(EFFECT_DESCRIPTIONS[effect])[0] for effect in effects)
    block_width = _ICON_SIZE + _COLUMN_GAP + label_width + _COLUMN_GAP + description_width
    left = surface.get_width() // 2 - block_width // 2
    for index, effect in enumerate(effects):
        row_top = top + index * _ROW_HEIGHT
        icon_for(effect).render(surface, pygame.Vector2(left, row_top), _ICON_SIZE)
        text_y = row_top + (_ICON_SIZE - font.get_height()) // 2
        label_left = left + _ICON_SIZE + _COLUMN_GAP
        surface.blit(font.render(effect_label(effect), True, _TEXT_COLOR), (label_left, text_y))
        description = font.render(EFFECT_DESCRIPTIONS[effect], True, _TEXT_COLOR)
        surface.blit(description, (label_left + label_width + _COLUMN_GAP, text_y))
