"""Distance-weighted prop-pool sampling for ExplorationScene (ADR 0016, PROJECT_BRIEF.md §9.3).
Decides which Biome pool(s) to sample from and how many props to draw from each; actual pixel
positioning is ExplorationScene's own concern, not this module's."""

import math

from eye.gui.assets import SpriteKey
from eye.gui.tuning import (
    BIOME_DEAD_FOREST_THRESHOLD_SCREENS,
    BIOME_FOREST_THRESHOLD_SCREENS,
    PROP_BOUNDARY_BLEND_SCREENS,
    PROP_MAX_COUNT_PER_SCREEN,
    PROP_MIN_COUNT_PER_SCREEN,
)


def _biome_span(distance_from_home: int) -> tuple[int, float, SpriteKey]:
    """The `[start, end)` screen range `distance_from_home` currently falls in, paired with that
    Biome's key. `end` is `math.inf` for the terminal Biome (forest has no next Biome to blend
    toward)."""
    if distance_from_home >= BIOME_FOREST_THRESHOLD_SCREENS:
        return (BIOME_FOREST_THRESHOLD_SCREENS, math.inf, SpriteKey.BIOME_FOREST)
    if distance_from_home >= BIOME_DEAD_FOREST_THRESHOLD_SCREENS:
        return (BIOME_DEAD_FOREST_THRESHOLD_SCREENS, float(BIOME_FOREST_THRESHOLD_SCREENS), SpriteKey.BIOME_DEAD_FOREST)
    return (0, float(BIOME_DEAD_FOREST_THRESHOLD_SCREENS), SpriteKey.BIOME_TURF)


def _next_biome_key(end: float) -> SpriteKey:
    if end == BIOME_DEAD_FOREST_THRESHOLD_SCREENS:
        return SpriteKey.BIOME_DEAD_FOREST
    return SpriteKey.BIOME_FOREST


def _thinned_count(distance_from_home: int, start: int, end: float) -> int:
    if math.isinf(end):
        return PROP_MAX_COUNT_PER_SCREEN
    span = end - start
    progress = (distance_from_home - start) / span
    return round(PROP_MAX_COUNT_PER_SCREEN - progress * (PROP_MAX_COUNT_PER_SCREEN - PROP_MIN_COUNT_PER_SCREEN))


def resolve_prop_sampling(distance_from_home: int) -> list[tuple[SpriteKey, int]]:
    start, end, key = _biome_span(distance_from_home)
    sampling = [(key, _thinned_count(distance_from_home, start, end))]

    if math.isinf(end):
        return sampling

    screens_to_boundary = end - distance_from_home
    if screens_to_boundary > PROP_BOUNDARY_BLEND_SCREENS:
        return sampling

    blend_progress = 1.0 - screens_to_boundary / PROP_BOUNDARY_BLEND_SCREENS
    blend_count = round(PROP_MAX_COUNT_PER_SCREEN * blend_progress)
    if blend_count > 0:
        sampling.append((_next_biome_key(end), blend_count))
    return sampling
