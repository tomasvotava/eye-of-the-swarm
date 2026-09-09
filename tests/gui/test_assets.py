import json
from enum import StrEnum
from pathlib import Path

import pygame
import pytest

from eye.gui.animation import AnimationClip
from eye.gui.assets import (
    PLACEHOLDER_SPRITE_SIZE,
    IconVariant,
    SpriteAtlas,
    SpriteKey,
    build_art_atlas,
    build_placeholder_atlas,
)


def _write_static_sprite(directory: Path, name: str = "sprite", size: tuple[int, int] = (4, 4)) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pygame.image.save(pygame.Surface(size), directory / f"{name}.png")


def _write_clip(directory: Path, name: str, frame_count: int = 2, frame_size: int = 4, fps: float = 8) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pygame.image.save(pygame.Surface((frame_size * frame_count, frame_size)), directory / f"{name}.png")
    manifest = {"frame_width": frame_size, "frame_height": frame_size, "frame_count": frame_count, "fps": fps}
    (directory / f"{name}.json").write_text(json.dumps(manifest))


_SHIPPED_SPRITES_DIR = Path("eye/gui/sprites")
_SHIPPED_ICON_KEYS = (
    SpriteKey.ICON_HEALTH,
    SpriteKey.ICON_SPORES,
    SpriteKey.ICON_SEED_GROWTH,
    SpriteKey.ICON_DISTANCE_DISCOUNT,
    SpriteKey.ICON_RECOIL,
    SpriteKey.EFFECT_RESONANCE,
)
_SHIPPED_ICON_KEYS_WITH_VARIANTS = (SpriteKey.ICON_HEALTH, SpriteKey.ICON_SPORES, SpriteKey.EFFECT_RESONANCE)


class _BrambleState(StrEnum):
    IDLE = "idle"


class _SeedVariant(StrEnum):
    ACTIVE = "active"


def test_build_placeholder_atlas_has_a_surface_for_every_sprite_key() -> None:
    atlas = build_placeholder_atlas()

    for key in SpriteKey:
        surface = atlas.get(key)
        assert isinstance(surface, pygame.Surface)
        assert surface.get_size() == (PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE)


def test_build_placeholder_atlas_creates_a_distinct_surface_per_key() -> None:
    atlas = build_placeholder_atlas()

    surfaces = [atlas.get(key) for key in SpriteKey]

    assert len({id(surface) for surface in surfaces}) == len(surfaces)


def test_sprite_atlas_get_returns_the_wrapped_surface() -> None:
    surface = pygame.Surface((4, 4))
    atlas = SpriteAtlas({SpriteKey.PLAYER: surface})

    assert atlas.get(SpriteKey.PLAYER) is surface


def test_build_art_atlas_falls_back_to_the_placeholder_for_a_missing_directory(tmp_path: Path) -> None:
    atlas = build_art_atlas(tmp_path)

    assert atlas.get(SpriteKey.TURF).get_size() == (PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE)


def test_build_art_atlas_loads_a_static_sprite_when_present(tmp_path: Path) -> None:
    _write_static_sprite(tmp_path / SpriteKey.PLAYER.value, size=(4, 4))

    atlas = build_art_atlas(tmp_path)

    assert atlas.get(SpriteKey.PLAYER).get_size() == (4, 4)


def test_build_art_atlas_falls_back_to_the_placeholder_when_the_directory_has_no_static_sprite(
    tmp_path: Path,
) -> None:
    _write_clip(tmp_path / SpriteKey.BRAMBLE.value, "idle")

    atlas = build_art_atlas(tmp_path)

    assert atlas.get(SpriteKey.BRAMBLE).get_size() == (PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE)


def test_build_art_atlas_loads_an_effect_sprite_at_its_native_size(tmp_path: Path) -> None:
    # Real effect-icon art ships at 210x210 -- build_art_atlas loads it at its native size (any
    # resizing to a render target happens at render time, per SpriteBuffIcon).
    _write_static_sprite(tmp_path / SpriteKey.EFFECT_FIBROUS.value, size=(210, 210))

    atlas = build_art_atlas(tmp_path)

    assert atlas.get(SpriteKey.EFFECT_FIBROUS).get_size() == (210, 210)


def test_build_art_atlas_falls_back_to_the_placeholder_for_every_key_when_no_art_is_on_disk(tmp_path: Path) -> None:
    # build_art_atlas walks SpriteKey, so a key with no _PLACEHOLDER_SHAPES entry is a KeyError at
    # startup, not a fallback.
    atlas = build_art_atlas(tmp_path)

    for key in SpriteKey:
        assert atlas.get(key).get_size() == (PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE)


def test_build_art_atlas_resolves_a_clip_pair_via_get_animation_set(tmp_path: Path) -> None:
    _write_clip(tmp_path / SpriteKey.BRAMBLE.value, "idle", frame_count=3, fps=8)

    atlas = build_art_atlas(tmp_path)
    clips = atlas.get_animation_set(SpriteKey.BRAMBLE, _BrambleState)

    clip = clips[_BrambleState.IDLE]
    assert isinstance(clip, AnimationClip)
    assert len(clip.frames) == 3
    assert clip.frame_duration_seconds == pytest.approx(1 / 8)


def test_build_art_atlas_resolves_a_named_variant_via_get_variant_set(tmp_path: Path) -> None:
    directory = tmp_path / SpriteKey.SEED.value
    directory.mkdir()
    pygame.image.save(pygame.Surface((4, 4)), directory / "active.png")

    atlas = build_art_atlas(tmp_path)
    variants = atlas.get_variant_set(SpriteKey.SEED, _SeedVariant)

    assert variants[_SeedVariant.ACTIVE].get_size() == (4, 4)


def test_get_animation_set_raises_when_a_state_has_no_matching_file(tmp_path: Path) -> None:
    atlas = build_art_atlas(tmp_path)

    with pytest.raises(ValueError, match=r"states.*IDLE"):
        atlas.get_animation_set(SpriteKey.BRAMBLE, _BrambleState)


def test_get_variant_set_raises_when_a_variant_has_no_matching_file(tmp_path: Path) -> None:
    atlas = build_art_atlas(tmp_path)

    with pytest.raises(ValueError, match=r"variants.*ACTIVE"):
        atlas.get_variant_set(SpriteKey.SEED, _SeedVariant)


def test_build_art_atlas_rejects_a_static_sprite_with_a_manifest_sibling(tmp_path: Path) -> None:
    _write_clip(tmp_path / SpriteKey.PLAYER.value, "sprite")

    with pytest.raises(ValueError, match=r"sprite\.png.*must not have a \.json manifest sibling"):
        build_art_atlas(tmp_path)


def test_has_animation_set_is_false_for_a_key_with_no_clips() -> None:
    atlas = build_placeholder_atlas()

    assert atlas.has_animation_set(SpriteKey.PLAYER) is False


def test_has_animation_set_is_true_once_the_key_has_a_clip(tmp_path: Path) -> None:
    _write_clip(tmp_path / SpriteKey.BRAMBLE.value, "idle")

    atlas = build_art_atlas(tmp_path)

    assert atlas.has_animation_set(SpriteKey.BRAMBLE) is True


def test_has_variant_set_is_false_for_a_key_with_no_variants() -> None:
    atlas = build_placeholder_atlas()

    assert atlas.has_variant_set(SpriteKey.ICON_HEALTH) is False


def test_has_variant_set_is_true_once_the_key_has_a_variant(tmp_path: Path) -> None:
    _write_static_sprite(tmp_path / SpriteKey.SEED.value, "active")

    atlas = build_art_atlas(tmp_path)

    assert atlas.has_variant_set(SpriteKey.SEED) is True


@pytest.mark.parametrize("key", _SHIPPED_ICON_KEYS)
def test_build_art_atlas_resolves_a_shipped_icon_key_to_real_art(key: SpriteKey) -> None:
    atlas = build_art_atlas(_SHIPPED_SPRITES_DIR)

    assert atlas.get(key).get_size() != (PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE)


@pytest.mark.parametrize("key", _SHIPPED_ICON_KEYS_WITH_VARIANTS)
def test_build_art_atlas_resolves_every_icon_variant_of_a_shipped_icon_key(key: SpriteKey) -> None:
    atlas = build_art_atlas(_SHIPPED_SPRITES_DIR)

    variants = atlas.get_variant_set(key, IconVariant)

    assert variants[IconVariant.BORDERLESS] is not atlas.get(key)
    assert variants[IconVariant.BORDERLESS].get_size() != (PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE)
