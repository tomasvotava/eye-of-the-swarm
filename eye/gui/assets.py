"""Entity/background sprites for the GUI driver. `build_placeholder_atlas()` draws a solid-color
primitive per key — a placeholder per ADR 0009, grep-discoverable as exactly what a future art
epic replaces with `build_art_atlas(assets_dir)`, swapped in at its one call site without touching
scene code.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pygame
import pygame.typing

from eye.gui.animation import AnimationClip
from eye.gui.spritesheet import load_spritesheet_clip

PLACEHOLDER_SPRITE_SIZE = 32
_STATIC_SPRITE_FILENAME = "sprite.png"


class SpriteKey(StrEnum):
    PLAYER = "player"
    BRAMBLE = "bramble"
    SEED = "seed"
    TURF = "turf"
    BACKGROUND = "background"
    # Fallback for a lookup that couldn't resolve a more specific key (e.g. a Strain with no
    # same-named sprite) -- the conventional "missing texture" placeholder, not tied to any one
    # entity, so callers have somewhere to fall back to instead of crashing.
    UNKNOWN = "unknown"


class SpriteAtlas:
    def __init__(
        self,
        surfaces: Mapping[SpriteKey, pygame.Surface],
        clips: Mapping[SpriteKey, Mapping[str, AnimationClip]] | None = None,
        variants: Mapping[SpriteKey, Mapping[str, pygame.Surface]] | None = None,
    ) -> None:
        self._surfaces = surfaces
        self._clips = clips or {}
        self._variants = variants or {}

    def get(self, key: SpriteKey) -> pygame.Surface:
        return self._surfaces[key]

    def has_animation_set(self, key: SpriteKey) -> bool:
        """Whether `key` has any loaded animation clips at all.

        Distinguishes "no animation data for this key" (fine — a caller falls back to `get`)
        from "some clips exist but a required state is missing", which `get_animation_set`
        still raises on rather than this method silently absorbing.
        """
        return key in self._clips

    def get_animation_set[TState: StrEnum](
        self, key: SpriteKey, state_type: type[TState]
    ) -> Mapping[TState, AnimationClip]:
        """Resolve `state_type`'s members against `key`'s loaded animation clips.

        Raises `ValueError` if any member has no matching clip on disk.
        """
        raw = self._clips.get(key, {})
        return _resolve_named_set(key, raw, state_type, label="states")

    def get_variant_set[TVariant: StrEnum](
        self, key: SpriteKey, variant_type: type[TVariant]
    ) -> Mapping[TVariant, pygame.Surface]:
        """Resolve `variant_type`'s members against `key`'s loaded static named variants.

        Raises `ValueError` if any member has no matching file on disk.
        """
        raw = self._variants.get(key, {})
        return _resolve_named_set(key, raw, variant_type, label="variants")


def _resolve_named_set[T, TEnum: StrEnum](
    key: SpriteKey, raw: Mapping[str, T], enum_type: type[TEnum], *, label: str
) -> Mapping[TEnum, T]:
    resolved: dict[TEnum, T] = {}
    missing: list[TEnum] = []
    for member in enum_type:
        if member.value in raw:
            resolved[member] = raw[member.value]
        else:
            missing.append(member)
    if missing:
        raise ValueError(f"{key!r}: missing sprite files for {label}: {missing}")
    return resolved


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
    SpriteKey.UNKNOWN: _PlaceholderShape(color="magenta", is_circle=False),
}


def _build_placeholder_surface(key: SpriteKey) -> pygame.Surface:
    shape = _PLACEHOLDER_SHAPES[key]
    surface = pygame.Surface((PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE), pygame.SRCALPHA)
    if shape.is_circle:
        radius = PLACEHOLDER_SPRITE_SIZE // 2
        pygame.draw.circle(surface, shape.color, (radius, radius), radius)
    else:
        surface.fill(shape.color)
    return surface


def build_placeholder_atlas() -> SpriteAtlas:
    surfaces = {key: _build_placeholder_surface(key) for key in _PLACEHOLDER_SHAPES}
    return SpriteAtlas(surfaces)


def build_art_atlas(assets_dir: Path) -> SpriteAtlas:
    """Build a `SpriteAtlas` from `eye/gui/sprites`-shaped directories under `assets_dir`.

    Resolved per `SpriteKey`, not all-or-nothing (ADR 0011): a missing `assets_dir / key.value`
    directory, or one with no `sprite.png`, falls back to today's placeholder shape; a
    `sprite.png` inside it loads as the key's static surface; every other `<name>.png` with a
    `<name>.json` sibling loads as an animation clip, and every other `<name>.png` without one
    loads as a static named variant.
    """
    surfaces: dict[SpriteKey, pygame.Surface] = {}
    clips: dict[SpriteKey, dict[str, AnimationClip]] = {}
    variants: dict[SpriteKey, dict[str, pygame.Surface]] = {}

    for key in SpriteKey:
        key_dir = assets_dir / key.value
        surfaces[key] = _build_placeholder_surface(key)
        if not key_dir.is_dir():
            continue

        static_sprite_path = key_dir / _STATIC_SPRITE_FILENAME
        if static_sprite_path.is_file():
            if static_sprite_path.with_suffix(".json").is_file():
                raise ValueError(
                    f"{key!r}: {_STATIC_SPRITE_FILENAME} must not have a .json manifest sibling — "
                    "an animated clip needs a non-'sprite' filename"
                )
            surfaces[key] = pygame.image.load(static_sprite_path).convert_alpha()

        key_clips: dict[str, AnimationClip] = {}
        key_variants: dict[str, pygame.Surface] = {}
        for png_path in sorted(key_dir.glob("*.png")):
            if png_path.name == _STATIC_SPRITE_FILENAME:
                continue
            manifest_path = png_path.with_suffix(".json")
            if manifest_path.is_file():
                sheet_clip = load_spritesheet_clip(png_path, manifest_path)
                key_clips[png_path.stem] = AnimationClip(
                    frames=sheet_clip.frames, frame_duration_seconds=sheet_clip.frame_duration_seconds
                )
            else:
                key_variants[png_path.stem] = pygame.image.load(png_path).convert_alpha()
        if key_clips:
            clips[key] = key_clips
        if key_variants:
            variants[key] = key_variants

    return SpriteAtlas(surfaces, clips, variants)
