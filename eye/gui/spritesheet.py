"""Manifest schema and grid-slicing for uniform-grid spritesheets (ADR 0011)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pygame


@dataclass(frozen=True, slots=True)
class SpriteSheetManifest:
    frame_width: int
    frame_height: int
    frame_count: int
    fps: float

    def __post_init__(self) -> None:
        # Manifests are parsed from untyped JSON -- coerce here so a malformed field (a null, a
        # string, a bool) fails right at parse time with a clear TypeError/ValueError, instead of
        # surfacing later as an unrelated-looking arithmetic or pygame error during slicing. bool
        # is excluded explicitly: it's an int subclass, so int()/float() would otherwise accept
        # it silently (e.g. fps=false -> 0.0) instead of failing fast like any other bad type.
        for field_name in ("frame_width", "frame_height", "frame_count", "fps"):
            value = getattr(self, field_name)
            if isinstance(value, bool):
                raise TypeError(f"{field_name} must not be a bool, got {value!r}")
        object.__setattr__(self, "frame_width", int(self.frame_width))
        object.__setattr__(self, "frame_height", int(self.frame_height))
        object.__setattr__(self, "frame_count", int(self.frame_count))
        object.__setattr__(self, "fps", float(self.fps))


@dataclass(frozen=True, slots=True)
class SpriteSheetClip:
    frames: tuple[pygame.Surface, ...]
    frame_duration_seconds: float


def load_manifest(manifest_path: Path) -> SpriteSheetManifest:
    data = json.loads(manifest_path.read_text())
    return SpriteSheetManifest(
        frame_width=data["frame_width"],
        frame_height=data["frame_height"],
        frame_count=data["frame_count"],
        fps=data["fps"],
    )


def load_spritesheet_clip(sheet_path: Path, manifest_path: Path) -> SpriteSheetClip:
    """Load and grid-slice a spritesheet per its manifest (single row, left-to-right)."""
    manifest = load_manifest(manifest_path)
    sheet = pygame.image.load(sheet_path).convert_alpha()
    expected_width = manifest.frame_width * manifest.frame_count
    if sheet.get_width() != expected_width:
        raise ValueError(
            f"{sheet_path}: manifest frame_width*frame_count ({expected_width}) does not "
            f"match sheet width ({sheet.get_width()})"
        )
    frames = tuple(
        sheet.subsurface((i * manifest.frame_width, 0, manifest.frame_width, manifest.frame_height))
        for i in range(manifest.frame_count)
    )
    return SpriteSheetClip(frames=frames, frame_duration_seconds=1 / manifest.fps)
