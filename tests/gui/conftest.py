import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest


@pytest.fixture(autouse=True)
def _pygame_display() -> None:
    pygame.display.init()
