from eye.gui.assets import SpriteKey
from eye.gui.props import resolve_prop_sampling
from eye.gui.tuning import (
    BIOME_DEAD_FOREST_THRESHOLD_SCREENS,
    BIOME_FOREST_THRESHOLD_SCREENS,
    PROP_BOUNDARY_BLEND_SCREENS,
    PROP_MAX_COUNT_PER_SCREEN,
)


def test_resolve_prop_sampling_is_at_max_count_at_the_start_of_a_biome() -> None:
    sampling = resolve_prop_sampling(0)  # turf starts at screen 0

    assert sampling == [(SpriteKey.BIOME_TURF, PROP_MAX_COUNT_PER_SCREEN)]


def test_resolve_prop_sampling_thins_to_min_count_just_before_a_boundary_outside_the_blend_window() -> None:
    # One screen before the boundary, but still outside the blend window (assumes
    # PROP_BOUNDARY_BLEND_SCREENS < BIOME_DEAD_FOREST_THRESHOLD_SCREENS - 1, true for the
    # placeholder values chosen in this plan: blend=3, threshold=5).
    distance = BIOME_DEAD_FOREST_THRESHOLD_SCREENS - PROP_BOUNDARY_BLEND_SCREENS - 1

    sampling = resolve_prop_sampling(distance)

    assert len(sampling) == 1
    assert sampling[0][0] is SpriteKey.BIOME_TURF


def test_resolve_prop_sampling_blends_in_the_next_biome_within_the_boundary_window() -> None:
    distance = BIOME_DEAD_FOREST_THRESHOLD_SCREENS - 1  # one screen before the boundary

    sampling = resolve_prop_sampling(distance)

    assert sampling[0][0] is SpriteKey.BIOME_TURF
    assert sampling[1][0] is SpriteKey.BIOME_DEAD_FOREST
    assert sampling[1][1] > 0


def test_resolve_prop_sampling_reaches_full_next_biome_count_exactly_at_the_boundary() -> None:
    sampling = resolve_prop_sampling(BIOME_DEAD_FOREST_THRESHOLD_SCREENS)

    assert sampling == [(SpriteKey.BIOME_DEAD_FOREST, PROP_MAX_COUNT_PER_SCREEN)]


def test_resolve_prop_sampling_stays_at_max_count_forever_in_the_terminal_biome() -> None:
    sampling = resolve_prop_sampling(BIOME_FOREST_THRESHOLD_SCREENS + 1000)

    assert sampling == [(SpriteKey.BIOME_FOREST, PROP_MAX_COUNT_PER_SCREEN)]
