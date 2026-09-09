import pygame
import pygame.typing

from eye.combat.effects import EffectName
from eye.gui.effect_card import (
    _DESCRIPTION_FONT_SIZE,
    _GAP,
    _ICON_SCALE,
    _ICON_SIZE,
    _SUBTITLE_FONT_SIZE,
    _TITLE_FONT_SIZE,
    EffectCard,
    _fitted_font,
    _wrapped_lines,
    draw_effect_card,
)
from eye.gui.widgets import BuffIcon, TextBuffIcon

# A colour the card never paints, so colorkeying it leaves exactly the drawn pixels. Not black:
# the card's own backdrop panel is translucent black.
_UNDRAWN: pygame.typing.ColorLike = "navy"
_SURFACE_SIZE = (800, 600)
_TITLE = "Runt"
_DESCRIPTION = "Lowers attack"
_SUBTITLE = "Player — 3 turns"
_FOOTER = "(press any key to close)"


def _card(icon: BuffIcon) -> EffectCard:
    return EffectCard(title=_TITLE, icon=icon, description=_DESCRIPTION, subtitle=_SUBTITLE)


def _drawn_rect(*, center_x: int, column_width: int, footer: str | None = None) -> pygame.Rect:
    surface = pygame.Surface(_SURFACE_SIZE)
    surface.fill(_UNDRAWN)
    draw_effect_card(
        surface, _card(TextBuffIcon(EffectName.RUNT)), center_x=center_x, column_width=column_width, footer=footer
    )
    surface.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only what was drawn
    return surface.get_bounding_rect()


def test_the_icon_fills_the_icon_box_stacked_under_the_title_at_the_given_center() -> None:
    render_calls: list[tuple[pygame.Vector2, int]] = []

    class _SpyIcon:
        def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
            render_calls.append((pos, size))

    surface = pygame.Surface(_SURFACE_SIZE)

    # The wide column leaves the icon box at its tuned size; the narrow one clamps it.
    for center_x, column_width in ((200, 360), (610, 90)):
        render_calls.clear()

        draw_effect_card(surface, _card(_SpyIcon()), center_x=center_x, column_width=column_width)

        icon_box_size = min(int(_ICON_SIZE * _ICON_SCALE), column_width)
        title_height = _fitted_font((_TITLE,), _TITLE_FONT_SIZE, column_width).render(_TITLE, True, "white").height
        description_font = _fitted_font(_DESCRIPTION.split(), _DESCRIPTION_FONT_SIZE, column_width)
        description_height = sum(
            description_font.render(line, True, "white").height
            for line in _wrapped_lines(_DESCRIPTION, description_font, column_width)
        )
        subtitle_height = (
            _fitted_font((_SUBTITLE,), _SUBTITLE_FONT_SIZE, column_width).render(_SUBTITLE, True, "white").height
        )
        block_height = title_height + icon_box_size + description_height + subtitle_height + _GAP * 3
        top = surface.get_height() // 2 - block_height // 2

        assert len(render_calls) == 1
        pos, size = render_calls[0]
        assert pos == pygame.Vector2(center_x - icon_box_size // 2, top + title_height + _GAP)
        assert size == icon_box_size


def test_the_drawn_block_is_centered_on_the_given_center_x_within_the_given_column_width() -> None:
    # Real pixels, so the backdrop panel and every rendered line count towards the extent.
    wide = _drawn_rect(center_x=200, column_width=360)
    narrow = _drawn_rect(center_x=610, column_width=90)

    assert wide.size != (0, 0)  # an empty rect would satisfy every check below
    assert wide.centerx == 200
    assert narrow.centerx == 610
    assert narrow.width <= 90 + _GAP * 2  # the panel's own inset is all that may exceed the budget
    assert narrow.width < wide.width  # the budget clamps the block rather than being ignored


def test_a_footer_adds_a_line_inside_the_panel_and_is_absent_without_one() -> None:
    without = _drawn_rect(center_x=400, column_width=360)
    with_footer = _drawn_rect(center_x=400, column_width=360, footer=_FOOTER)

    assert with_footer.height > without.height
    assert with_footer.centerx == 400  # the extra line stays centred with the rest of the block


def test_a_long_footer_is_typeset_into_the_column_like_every_other_line() -> None:
    narrow = _drawn_rect(center_x=400, column_width=90, footer=_FOOTER)

    assert narrow.width <= 90 + _GAP * 2  # the panel's own inset is all that may exceed the budget
