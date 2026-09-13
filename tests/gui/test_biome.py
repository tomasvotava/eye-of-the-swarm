from eye.gui.assets import SpriteKey
from eye.gui.biome import resolve_biome
from eye.gui.tuning import BIOME_DEAD_FOREST_THRESHOLD_SCREENS, BIOME_FOREST_THRESHOLD_SCREENS


def test_resolve_biome_is_turf_at_zero_distance() -> None:
    assert resolve_biome(0) is SpriteKey.BIOME_TURF


def test_resolve_biome_is_turf_just_below_the_dead_forest_threshold() -> None:
    assert resolve_biome(BIOME_DEAD_FOREST_THRESHOLD_SCREENS - 1) is SpriteKey.BIOME_TURF


def test_resolve_biome_is_dead_forest_at_its_own_threshold() -> None:
    assert resolve_biome(BIOME_DEAD_FOREST_THRESHOLD_SCREENS) is SpriteKey.BIOME_DEAD_FOREST


def test_resolve_biome_is_dead_forest_just_below_the_forest_threshold() -> None:
    assert resolve_biome(BIOME_FOREST_THRESHOLD_SCREENS - 1) is SpriteKey.BIOME_DEAD_FOREST


def test_resolve_biome_is_forest_at_its_own_threshold_and_beyond() -> None:
    assert resolve_biome(BIOME_FOREST_THRESHOLD_SCREENS) is SpriteKey.BIOME_FOREST
    assert resolve_biome(BIOME_FOREST_THRESHOLD_SCREENS + 100) is SpriteKey.BIOME_FOREST
