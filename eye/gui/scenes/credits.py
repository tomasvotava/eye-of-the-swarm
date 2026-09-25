"""CreditsScene: a static, standalone screen naming the game's credits. It takes a `back_scene`
rather than resolving one itself, so whatever constructs it decides how it is reached and where it
goes back to.
"""

import pygame
import pygame.typing

from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.scene import Scene

_TITLE_FONT_SIZE = 32
_LINE_FONT_SIZE = 20
_FOOTER_FONT_SIZE = 16
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_LINE_GAP = 12
_TITLE_TOP_FRACTION = 0.2
_FOOTER_BOTTOM_MARGIN = 24

_LINES = (
    "Tomas Votava — Developer",
    "Jan Kloboucnik — Character Designer",
    "Tomas Votava — Music and Sound effects",
    "Renata Hlavova — Lore and Story",
    "Remaining assets generated using Midjourney, Claude, and Mistral",
)
_FOOTER = "Enter or Escape: back"
# Not "any key" (GOTCHAS.md) -- an OS/window-manager fullscreen toggle can deliver a synthetic
# keydown. Escape matches SettingsScene's own back key, the other screen reached from the menu.
_DISMISS_KEYS = frozenset({pygame.K_RETURN, pygame.K_ESCAPE})


class CreditsScene:
    def __init__(self, back_scene: Scene) -> None:
        self._back_scene = back_scene
        self._dismissed = False

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type == pygame.KEYDOWN and pygame_event.key in _DISMISS_KEYS:
            self._dismissed = True

    def update(self, dt: float) -> Scene | None:
        return self._back_scene if self._dismissed else None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        title_font = get_font(GameFont.ITHACA, _TITLE_FONT_SIZE)
        title = title_font.render("Credits", True, _TEXT_COLOR)
        surface.blit(
            title,
            (surface.get_width() // 2 - title.get_width() // 2, round(surface.get_height() * _TITLE_TOP_FRACTION)),
        )

        line_font = get_font(GameFont.ITHACA, _LINE_FONT_SIZE)
        top = round(surface.get_height() * _TITLE_TOP_FRACTION) + title.get_height() + _LINE_GAP * 2
        for line in _LINES:
            rendered = line_font.render(line, True, _TEXT_COLOR)
            surface.blit(rendered, (surface.get_width() // 2 - rendered.get_width() // 2, top))
            top += rendered.get_height() + _LINE_GAP

        footer_font = get_font(GameFont.ITHACA, _FOOTER_FONT_SIZE)
        footer = footer_font.render(_FOOTER, True, _TEXT_COLOR)
        surface.blit(
            footer,
            (surface.get_width() // 2 - footer.get_width() // 2, surface.get_height() - _FOOTER_BOTTOM_MARGIN),
        )
