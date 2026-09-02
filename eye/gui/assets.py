"""Entity/background sprites for the GUI driver. `build_placeholder_atlas()` draws a solid-color
primitive per key — a placeholder per ADR 0009, grep-discoverable as exactly what a future art
epic replaces with `build_art_atlas(assets_dir)`, swapped in at its one call site without touching
scene code.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import pygame
import pygame.typing

PLACEHOLDER_SPRITE_SIZE = 32


class SpriteKey(StrEnum):
    PLAYER = "player"
    BRAMBLE = "bramble"
    SEED = "seed"
    TURF = "turf"
    BACKGROUND = "background"


class SpriteAtlas:
    def __init__(self, surfaces: Mapping[SpriteKey, pygame.Surface]) -> None:
        self._surfaces = surfaces

    def get(self, key: SpriteKey) -> pygame.Surface:
        return self._surfaces[key]


@dataclass(frozen=True, slots=True)
class _PlaceholderShape:
    color: pygame.typing.ColorLike
    is_circle: bool


_PLACEHOLDER_SHAPES: Mapping[SpriteKey, _PlaceholderShape] = {
    SpriteKey.PLAYER: _PlaceholderShape(color="dodgerblue", is_circle=True),
    SpriteKey.BRAMBLE: _PlaceholderShape(color="firebrick", is_circle=True),
    SpriteKey.SEED: _PlaceholderShape(color="gold", is_circle=True),
    SpriteKey.TURF: _PlaceholderShape(color="forestgreen", is_circle=False),
    SpriteKey.BACKGROUND: _PlaceholderShape(color="saddlebrown", is_circle=False),
}


def build_placeholder_atlas() -> SpriteAtlas:
    surfaces: dict[SpriteKey, pygame.Surface] = {}
    for key, shape in _PLACEHOLDER_SHAPES.items():
        surface = pygame.Surface((PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE), pygame.SRCALPHA)
        if shape.is_circle:
            radius = PLACEHOLDER_SPRITE_SIZE // 2
            pygame.draw.circle(surface, shape.color, (radius, radius), radius)
        else:
            surface.fill(shape.color)
        surfaces[key] = surface
    return SpriteAtlas(surfaces)
