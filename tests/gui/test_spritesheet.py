from pathlib import Path

import pytest

from eye.gui.spritesheet import SpriteSheetManifest, load_manifest, load_spritesheet_clip

FIXTURES = Path(__file__).parent / "fixtures" / "spritesheets"
VALID_SHEET = FIXTURES / "valid" / "sheet.png"
VALID_MANIFEST = FIXTURES / "valid" / "manifest.json"
MISMATCHED_MANIFEST = FIXTURES / "mismatched" / "manifest.json"

FRAME_COLORS = [
    (255, 0, 0, 255),
    (0, 255, 0, 255),
    (0, 0, 255, 255),
    (255, 255, 0, 255),
    (255, 0, 255, 255),
]


def test_load_manifest_parses_all_fields() -> None:
    manifest = load_manifest(VALID_MANIFEST)

    assert manifest == SpriteSheetManifest(frame_width=32, frame_height=32, frame_count=5, fps=8)


def test_load_spritesheet_clip_slices_the_expected_frame_count_and_size() -> None:
    frames, _ = load_spritesheet_clip(VALID_SHEET, VALID_MANIFEST)

    assert len(frames) == 5
    assert all(frame.get_size() == (32, 32) for frame in frames)


def test_load_spritesheet_clip_slices_frames_at_the_correct_positions() -> None:
    frames, _ = load_spritesheet_clip(VALID_SHEET, VALID_MANIFEST)

    for frame, expected_color in zip(frames, FRAME_COLORS, strict=True):
        assert tuple(frame.get_at((0, 0))) == expected_color


def test_load_spritesheet_clip_returns_the_per_frame_duration() -> None:
    _, duration = load_spritesheet_clip(VALID_SHEET, VALID_MANIFEST)

    assert duration == pytest.approx(1 / 8)


def test_load_spritesheet_clip_raises_on_a_manifest_that_does_not_fit_the_sheet_width() -> None:
    with pytest.raises(ValueError, match="does not match sheet width"):
        load_spritesheet_clip(VALID_SHEET, MISMATCHED_MANIFEST)
