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


@pytest.mark.parametrize(
    ("field", "value", "expected_exception"),
    [
        ("frame_width", None, TypeError),
        ("frame_count", "bramble", ValueError),
        ("fps", [], TypeError),
        ("fps", False, TypeError),
    ],
)
def test_manifest_rejects_a_field_of_the_wrong_type_at_construction(
    field: str, value: object, expected_exception: type[Exception]
) -> None:
    fields: dict[str, object] = {"frame_width": 32, "frame_height": 32, "frame_count": 5, "fps": 8}
    fields[field] = value

    with pytest.raises(expected_exception):
        SpriteSheetManifest(**fields)  # type: ignore[arg-type]


def test_manifest_coerces_numeric_looking_fields_to_their_declared_type() -> None:
    manifest = SpriteSheetManifest(frame_width="32", frame_height="32", frame_count="5", fps="8")  # type: ignore[arg-type]

    assert manifest == SpriteSheetManifest(frame_width=32, frame_height=32, frame_count=5, fps=8)


def test_load_spritesheet_clip_slices_the_expected_frame_count_and_size() -> None:
    clip = load_spritesheet_clip(VALID_SHEET, VALID_MANIFEST)

    assert len(clip.frames) == 5
    assert all(frame.get_size() == (32, 32) for frame in clip.frames)


def test_load_spritesheet_clip_slices_frames_at_the_correct_positions() -> None:
    clip = load_spritesheet_clip(VALID_SHEET, VALID_MANIFEST)

    for frame, expected_color in zip(clip.frames, FRAME_COLORS, strict=True):
        assert tuple(frame.get_at((0, 0))) == expected_color


def test_load_spritesheet_clip_returns_the_per_frame_duration() -> None:
    clip = load_spritesheet_clip(VALID_SHEET, VALID_MANIFEST)

    assert clip.frame_duration_seconds == pytest.approx(1 / 8)


def test_load_spritesheet_clip_raises_on_a_manifest_that_does_not_fit_the_sheet_width() -> None:
    with pytest.raises(ValueError, match="does not match sheet width"):
        load_spritesheet_clip(VALID_SHEET, MISMATCHED_MANIFEST)
