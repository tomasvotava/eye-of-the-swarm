"""TitleScene: the game's very first screen, before `MenuScene` (ADR 0017 amendment) -- just the
game's name and a "press Enter" prompt. Takes `next_scene` rather than resolving one itself,
mirroring `CreditsScene`'s constructor pattern -- whatever constructs it decides what it hands off
to.
"""

import pygame
import pygame.typing

from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.scene import Scene

_TITLE_FONT_SIZE = 48
_FOOTER_FONT_SIZE = 16
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_TITLE_CENTER_Y_FRACTION = 0.45
_FOOTER_BOTTOM_MARGIN = 24

_TITLE = "The Eye of the Swarm"
_FOOTER = "Press Enter to continue"


class TitleScene:
    def __init__(self, next_scene: Scene) -> None:
        self._next_scene = next_scene
        self._dismissed = False

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        # Not "any key" (GOTCHAS.md) -- an OS/window-manager fullscreen toggle can deliver a
        # synthetic keydown, dismissing the title screen before the player ever meant to.
        if pygame_event.type == pygame.KEYDOWN and pygame_event.key == pygame.K_RETURN:
            self._dismissed = True

    def update(self, dt: float) -> Scene | None:
        return self._next_scene if self._dismissed else None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        title_font = get_font(GameFont.BUSE, _TITLE_FONT_SIZE)
        title = title_font.render(_TITLE, True, _TEXT_COLOR)
        surface.blit(
            title,
            (
                surface.get_width() // 2 - title.get_width() // 2,
                round(surface.get_height() * _TITLE_CENTER_Y_FRACTION) - title.get_height() // 2,
            ),
        )

        footer_font = get_font(GameFont.ITHACA, _FOOTER_FONT_SIZE)
        footer = footer_font.render(_FOOTER, True, _TEXT_COLOR)
        surface.blit(
            footer,
            (surface.get_width() // 2 - footer.get_width() // 2, surface.get_height() - _FOOTER_BOTTOM_MARGIN),
        )
