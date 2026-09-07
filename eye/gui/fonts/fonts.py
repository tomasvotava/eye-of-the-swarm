from enum import Enum
from pathlib import Path

import pygame

type FontSpec = tuple[GameFont, int]

_FONT_ASSETS_DIR = Path(__file__).parent

_FONT_CACHE: dict[FontSpec, pygame.font.Font] = {}


class GameFont(tuple[str, str], Enum):
    BUSE = ("buse", "buse.otf")
    ITHACA = ("ithaca", "Ithaca.ttf")


def _get_font_path(font: GameFont) -> Path:
    dir_name, file_name = font
    if not (font_path := (_FONT_ASSETS_DIR / dir_name / file_name)).exists():
        raise FileNotFoundError(f"no font file found in {font_path.as_posix()}.")
    return font_path


def get_font(font: GameFont, font_size: int) -> pygame.font.Font:
    font_spec: FontSpec = (font, font_size)
    if font_spec not in _FONT_CACHE:
        font_path = _get_font_path(font)
        font_asset = pygame.font.Font(font_path, font_size)
        _FONT_CACHE[font_spec] = font_asset
    return _FONT_CACHE[font_spec]
