from collections.abc import Iterator

import pygame
import pytest


@pytest.fixture(scope="session", autouse=True)
def _headless_pygame_display() -> Iterator[None]:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
        pygame.display.init()
        pygame.font.init()
        yield
