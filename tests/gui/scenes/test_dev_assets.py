import json
from pathlib import Path

import pygame
import pytest

from eye.gui.assets import SpriteKey, build_art_atlas, build_placeholder_atlas
from eye.gui.scenes.dev_assets import KEY_ACTIONS, DevAssetViewerAction, DevAssetViewerScene


def _press(scene: DevAssetViewerScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


_FRAME_COLORS = [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)]


def _write_clip(directory: Path, name: str, frame_count: int = 2, frame_size: int = 4, fps: float = 8) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    sheet = pygame.Surface((frame_size * frame_count, frame_size))
    for index in range(frame_count):
        sheet.fill(
            _FRAME_COLORS[index % len(_FRAME_COLORS)], pygame.Rect(index * frame_size, 0, frame_size, frame_size)
        )
    pygame.image.save(sheet, directory / f"{name}.png")
    manifest = {"frame_width": frame_size, "frame_height": frame_size, "frame_count": frame_count, "fps": fps}
    (directory / f"{name}.json").write_text(json.dumps(manifest))


def _write_player_clips(assets_dir: Path, frame_count: int = 2, fps: float = 8) -> None:
    player_dir = assets_dir / SpriteKey.PLAYER.value
    _write_clip(player_dir, "idle", frame_count=frame_count, fps=fps)
    _write_clip(player_dir, "walk", frame_count=frame_count, fps=fps)


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


def _navigate_to(scene: DevAssetViewerScene, key: SpriteKey) -> None:
    for _ in range(list(SpriteKey).index(key)):
        _press(scene, pygame.K_RIGHT)
        scene.update(0.0)


def test_without_animation_data_the_player_key_still_draws_via_the_static_fallback() -> None:
    scene = DevAssetViewerScene(build_placeholder_atlas())
    _navigate_to(scene, SpriteKey.PLAYER)

    scene.draw(pygame.Surface((64, 64)))


def test_updating_advances_the_player_animation_frame(tmp_path: Path) -> None:
    _write_player_clips(tmp_path, frame_count=3, fps=10)
    scene = DevAssetViewerScene(build_art_atlas(tmp_path))
    _navigate_to(scene, SpriteKey.PLAYER)
    # A large surface keeps the centered sprite's sampled pixel well clear of the HUD text
    # drawn near the top-left corner.
    center = (400, 400)
    first_surface = pygame.Surface((800, 800))
    scene.draw(first_surface)
    first_color = first_surface.get_at(center)

    scene.update(0.1)  # exactly one frame at 10fps
    second_surface = pygame.Surface((800, 800))
    scene.draw(second_surface)

    assert second_surface.get_at(center) != first_color
