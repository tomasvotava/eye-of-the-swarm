import pygame
import pytest

from eye.gui.scene import Scene
from eye.gui.scenes.title import TitleScene


class _StubScene:
    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> Scene | None:
        return None

    def draw(self, surface: pygame.Surface) -> None:
        pass


def _press(scene: TitleScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_update_returns_none_without_a_dismiss_key() -> None:
    next_scene = _StubScene()
    scene = TitleScene(next_scene)

    assert scene.update(0.016) is None


@pytest.mark.parametrize("key", [pygame.K_RETURN, pygame.K_a, pygame.K_SPACE])
def test_any_key_transitions_to_the_next_scene(key: int) -> None:
    next_scene = _StubScene()
    scene = TitleScene(next_scene)

    _press(scene, key)

    assert scene.update(0.016) is next_scene


def test_non_keydown_events_are_ignored() -> None:
    next_scene = _StubScene()
    scene = TitleScene(next_scene)

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_a))

    assert scene.update(0.016) is None


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    scene = TitleScene(_StubScene())

    scene.draw(pygame.Surface(surface_size))
