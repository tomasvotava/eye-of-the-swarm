"""Manifest schema and grid-slicing for uniform-grid spritesheets. Per ADR 0011: a spritesheet is
one clip, single row, left-to-right, sliced at load time -- no pre-cutting, no Pillow dependency.
"""

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


def load_manifest(manifest_path: Path) -> SpriteSheetManifest:
    data = json.loads(manifest_path.read_text())
    return SpriteSheetManifest(
        frame_width=data["frame_width"],
        frame_height=data["frame_height"],
        frame_count=data["frame_count"],
        fps=data["fps"],
    )


def load_spritesheet_clip(sheet_path: Path, manifest_path: Path) -> tuple[tuple[pygame.Surface, ...], float]:
    """Load and grid-slice a spritesheet per its manifest.

    Returns the sliced frames (single row, left-to-right) and the per-frame duration (1 / fps).
    """
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
    return frames, 1 / manifest.fps
