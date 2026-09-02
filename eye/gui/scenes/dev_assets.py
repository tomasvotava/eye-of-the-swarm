"""DevAssetViewerScene: a developer-only Scene that pages through every SpriteKey in a SpriteAtlas
with its name, so placeholder (and later, real) art can be inspected without stepping through the
generational loop (ADR 0009). Wired in behind a dev-only entry point in app.py -- it never appears
in the normal exploration -> combat -> skill-tree -> rebirth loop.
"""

from enum import Enum, auto

import pygame
import pygame.typing

from eye.gui.assets import SpriteAtlas, SpriteKey
from eye.gui.scene import SceneTransition

_FONT_SIZE = 20
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_MARGIN = 8
_SPRITE_SCALE = 8  # placeholder sprites are tiny; enlarge them for visibility while browsing

_KEYS: tuple[SpriteKey, ...] = tuple(SpriteKey)


class DevAssetViewerAction(Enum):
    NEXT = auto()
    PREVIOUS = auto()


# pygame key -> DevAssetViewerAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, DevAssetViewerAction] = {
    pygame.K_RIGHT: DevAssetViewerAction.NEXT,
    pygame.K_LEFT: DevAssetViewerAction.PREVIOUS,
}

_font: pygame.font.Font | None = None


def _get_font() -> pygame.font.Font:
    # Constructed lazily rather than at import time: pygame.font must already be initialized,
    # which module import order doesn't guarantee (mirrors eye.gui.widgets._get_font()).
    global _font
    if _font is None:
        _font = pygame.font.Font(None, _FONT_SIZE)
    return _font


class DevAssetViewerScene:
    def __init__(self, atlas: SpriteAtlas) -> None:
        self._atlas = atlas
        self._index = 0
        self._pending_action: DevAssetViewerAction | None = None

    @property
    def current_key(self) -> SpriteKey:
        return _KEYS[self._index]

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type != pygame.KEYDOWN:
            return
        action = KEY_ACTIONS.get(pygame_event.key)
        if action is not None:
            self._pending_action = action

    def update(self, dt: float) -> SceneTransition | None:
        if self._pending_action is None:
            return None
        action = self._pending_action
        self._pending_action = None
        delta = 1 if action is DevAssetViewerAction.NEXT else -1
        self._index = (self._index + delta) % len(_KEYS)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        key = self.current_key
        sprite = pygame.transform.scale_by(self._atlas.get(key), _SPRITE_SCALE)
        surface.blit(sprite, sprite.get_rect(center=surface.get_rect().center))
        self._draw_hud(surface, key)

    def _draw_hud(self, surface: pygame.Surface, key: SpriteKey) -> None:
        font = _get_font()
        lines = [
            f"{key.value}  ({self._index + 1}/{len(_KEYS)})",
            "Left/Right: previous/next sprite",
        ]
        for index, line in enumerate(lines):
            surface.blit(font.render(line, True, _TEXT_COLOR), (_MARGIN, _MARGIN + index * _FONT_SIZE))
