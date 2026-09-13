"""Pure GUI-side Biome resolution by distance-from-home (ADR 0016). Never touches the domain's
placeholder `Biome` enum (`eye/exploration/encounters.py`) or `EnemyEncountered.biome`, both of
which stay exactly as unreliable as they are today. Shared by `ExplorationScene` and
`CombatScene`, which deliberately never import each other (see exploration.py's own
`_resolve_enemy_sprite_key` comment) -- this module is the seam both import instead.
"""

from eye.gui.assets import SpriteKey
from eye.gui.tuning import BIOME_DEAD_FOREST_THRESHOLD_SCREENS, BIOME_FOREST_THRESHOLD_SCREENS


def resolve_biome(distance_from_home: int) -> SpriteKey:
    if distance_from_home >= BIOME_FOREST_THRESHOLD_SCREENS:
        return SpriteKey.BIOME_FOREST
    if distance_from_home >= BIOME_DEAD_FOREST_THRESHOLD_SCREENS:
        return SpriteKey.BIOME_DEAD_FOREST
    return SpriteKey.BIOME_TURF
