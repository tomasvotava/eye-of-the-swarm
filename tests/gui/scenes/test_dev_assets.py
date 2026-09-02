import pygame
import pytest

from eye.gui.assets import SpriteKey, build_placeholder_atlas
from eye.gui.scenes.dev_assets import KEY_ACTIONS, DevAssetViewerAction, DevAssetViewerScene


def _press(scene: DevAssetViewerScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_key_actions_maps_the_expected_controls() -> None:
    assert KEY_ACTIONS[pygame.K_RIGHT] is DevAssetViewerAction.NEXT
    assert KEY_ACTIONS[pygame.K_LEFT] is DevAssetViewerAction.PREVIOUS


def test_starts_on_the_first_sprite_key() -> None:
    scene = DevAssetViewerScene(build_placeholder_atlas())

    assert scene.current_key is next(iter(SpriteKey))


def test_next_advances_to_the_following_sprite_key() -> None:
    scene = DevAssetViewerScene(build_placeholder_atlas())
    keys = list(SpriteKey)

    _press(scene, pygame.K_RIGHT)
    scene.update(0.016)

    assert scene.current_key is keys[1]


def test_previous_wraps_around_from_the_first_sprite_key() -> None:
    scene = DevAssetViewerScene(build_placeholder_atlas())
    keys = list(SpriteKey)

    _press(scene, pygame.K_LEFT)
    scene.update(0.016)

    assert scene.current_key is keys[-1]


def test_next_wraps_around_from_the_last_sprite_key() -> None:
    scene = DevAssetViewerScene(build_placeholder_atlas())
    keys = list(SpriteKey)
    for _ in keys:
        _press(scene, pygame.K_RIGHT)
        scene.update(0.016)

    assert scene.current_key is keys[0]


def test_update_returns_none_and_never_transitions_away() -> None:
    scene = DevAssetViewerScene(build_placeholder_atlas())

    _press(scene, pygame.K_RIGHT)

    assert scene.update(0.016) is None


def test_update_is_a_no_op_without_a_pending_key() -> None:
    scene = DevAssetViewerScene(build_placeholder_atlas())

    assert scene.update(0.016) is None
    assert scene.current_key is next(iter(SpriteKey))


def test_unmapped_keys_are_ignored() -> None:
    scene = DevAssetViewerScene(build_placeholder_atlas())

    _press(scene, pygame.K_a)

    assert scene.update(0.016) is None
    assert scene.current_key is next(iter(SpriteKey))


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    scene = DevAssetViewerScene(build_placeholder_atlas())

    scene.draw(pygame.Surface(surface_size))
