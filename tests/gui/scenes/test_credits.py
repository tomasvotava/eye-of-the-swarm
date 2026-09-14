import pygame
import pytest

from eye.gui.scene import Scene
from eye.gui.scenes.credits import CreditsScene


class _StubScene:
    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> Scene | None:
        return None

    def draw(self, surface: pygame.Surface) -> None:
        pass


def _press(scene: CreditsScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_update_returns_none_without_a_dismiss_key() -> None:
    back_scene = _StubScene()
    scene = CreditsScene(back_scene)

    assert scene.update(0.016) is None


@pytest.mark.parametrize("key", [pygame.K_RETURN, pygame.K_ESCAPE])
def test_enter_or_escape_dismisses_back_to_the_given_scene(key: int) -> None:
    back_scene = _StubScene()
    scene = CreditsScene(back_scene)

    _press(scene, key)

    assert scene.update(0.016) is back_scene


@pytest.mark.parametrize("key", [pygame.K_a, pygame.K_SPACE, pygame.K_F11])
def test_other_keys_leave_the_credits_up(key: int) -> None:
    # A fullscreen toggle's synthetic keydown must not bounce the player out of the screen they
    # just opened -- the same leniency bug TitleScene had.
    back_scene = _StubScene()
    scene = CreditsScene(back_scene)

    _press(scene, key)

    assert scene.update(0.016) is None


def test_non_keydown_events_are_ignored() -> None:
    back_scene = _StubScene()
    scene = CreditsScene(back_scene)

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_a))

    assert scene.update(0.016) is None


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    scene = CreditsScene(_StubScene())

    scene.draw(pygame.Surface(surface_size))
