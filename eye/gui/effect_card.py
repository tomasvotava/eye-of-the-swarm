"""The effect card: a title, icon, description and subtitle stacked over a backdrop panel. It is
drawn into a column given as a centre-x and a width, so anchoring is the caller's decision, and
every scene sizes that column with `card_column_width`."""

from collections.abc import Sequence
from dataclasses import dataclass

import pygame
import pygame.typing

from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.widgets import BuffIcon

# Ceilings, not fixed sizes: _fitted_font drops below them when a label won't fit the column.
_TITLE_FONT_SIZE = 44
_DESCRIPTION_FONT_SIZE = 28
_SUBTITLE_FONT_SIZE = 14
# Floor for the shrink-to-fit search: below this the text fits its column but can't be read.
_MIN_FONT_SIZE = 10
# SIZE is the shipped effect-icon art's native pixel size (210x210); SCALE is the card's own knob.
# Neither feeds the card's typography, which is sized off its column.
_ICON_SIZE = 210
_ICON_SCALE = 0.72
_GAP = 4
_TEXT_COLOR: pygame.typing.ColorLike = "white"
# Inset from both edges of the column a card is typeset into, keeping it clear of its neighbour.
_COLUMN_MARGIN = 16
# Dims whatever a card lands on. Black, so it leaves no edge against the black background.
_BACKDROP_COLOR: pygame.typing.ColorLike = (0, 0, 0, 200)


def card_column_width(surface: pygame.Surface) -> int:
    """The width budget for a card on `surface`: half its width, less a margin at each edge. Half so
    a card comes out the same size in every scene, whether or not it shares the screen."""
    return surface.get_width() // 2 - _COLUMN_MARGIN * 2


def _fitted_font(texts: Sequence[str], max_font_size: int, max_width: int) -> pygame.font.Font:
    """The largest Ithaca font up to `max_font_size` rendering every one of `texts` within
    `max_width`, bottoming out at `_MIN_FONT_SIZE` even if that no longer fits."""
    for size in range(max_font_size, _MIN_FONT_SIZE, -1):
        font = get_font(GameFont.ITHACA, size)
        if all(font.size(text)[0] <= max_width for text in texts):
            return font
    return get_font(GameFont.ITHACA, min(max_font_size, _MIN_FONT_SIZE))


def _wrapped_lines(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """`text` greedily broken into lines that each render within `max_width`. A word wider than the
    budget overruns its own line; callers size the font against the words first."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and font.size(candidate)[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


@dataclass(frozen=True, slots=True)
class EffectCard:
    """An effect's flavor name, icon, short prose and qualifying subtitle: all four or none, never
    a partial combination."""

    title: str
    icon: BuffIcon
    description: str
    subtitle: str


def draw_effect_card(surface: pygame.Surface, card: EffectCard, *, center_x: int, column_width: int) -> None:
    """Draw `card` as one block over a backdrop panel, centered on `center_x` and on the surface's
    own vertical middle. `column_width` is the width budget every piece is typeset into."""
    # Card layout: title / icon box / description / subtitle. Every piece is typeset to the column
    # budget, not off the rest.
    title_surface = _fitted_font((card.title,), _TITLE_FONT_SIZE, column_width).render(card.title, True, _TEXT_COLOR)
    # Fitted against the individual words: wrapping handles the length.
    description_font = _fitted_font(card.description.split(), _DESCRIPTION_FONT_SIZE, column_width)
    description_surfaces = [
        description_font.render(line, True, _TEXT_COLOR)
        for line in _wrapped_lines(card.description, description_font, column_width)
    ]
    subtitle_surface = _fitted_font((card.subtitle,), _SUBTITLE_FONT_SIZE, column_width).render(
        card.subtitle, True, _TEXT_COLOR
    )
    icon_box_size = min(int(_ICON_SIZE * _ICON_SCALE), column_width)

    description_height = sum(line.height for line in description_surfaces)
    block_height = title_surface.height + icon_box_size + description_height + subtitle_surface.height + _GAP * 3
    block_width = max(
        title_surface.width, icon_box_size, subtitle_surface.width, *(line.width for line in description_surfaces)
    )
    top = surface.get_height() // 2 - block_height // 2

    backdrop = pygame.Rect(0, 0, block_width + _GAP * 2, block_height + _GAP * 2)
    backdrop.center = (center_x, top + block_height // 2)
    # Blitted from an SRCALPHA surface: pygame.draw would write the alpha instead of blending.
    panel = pygame.Surface(backdrop.size, pygame.SRCALPHA)
    panel.fill(_BACKDROP_COLOR)
    surface.blit(panel, backdrop.topleft)

    surface.blit(title_surface, (center_x - title_surface.width // 2, top))
    icon_rect = pygame.Rect(
        center_x - icon_box_size // 2, top + title_surface.height + _GAP, icon_box_size, icon_box_size
    )
    pygame.draw.rect(surface, _TEXT_COLOR, icon_rect, width=2)
    card.icon.render(surface, pygame.Vector2(icon_rect.topleft), icon_box_size)

    description_top = icon_rect.bottom + _GAP
    for line in description_surfaces:
        surface.blit(line, (center_x - line.width // 2, description_top))
        description_top += line.height
    surface.blit(subtitle_surface, (center_x - subtitle_surface.width // 2, description_top + _GAP))
