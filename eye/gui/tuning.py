"""GUI-side pacing and feel constants for the screen-walk state machine (ADR 0012) and battle event
playback (ADR 0013) -- playtesting-driven placeholders (PROJECT_BRIEF.md §8), not final tuning.
"""

import pygame.typing

WALK_TO_EXIT_DURATION_SECONDS = 0.6
WALK_TO_ENCOUNTER_DURATION_SECONDS = 0.6

# Fractions of the draw surface's width -- resolved only at draw time, not by update(dt), so the
# walk timer never needs to know the surface size (ADR 0012's entry/encounter/exit x-positions).
ENTRY_X_FRACTION = 0.1
ENCOUNTER_X_FRACTION = 0.5
EXIT_X_FRACTION = 0.9

# Shared by the player and the encounter marker so they still meet at the same point when the walk
# arrives -- screen-center read as "floating," per playtesting feedback.
EXPLORATION_GROUND_Y_FRACTION = 0.8

# Category-scaled, not one shared factor: enemy matches CombatScene's own _COMBATANT_SCALE_FACTOR
# (fights at preview size); pickups shrink toward the player's own rendered height instead.
ENCOUNTER_ENEMY_SCALE_FACTOR = 3.0
ENCOUNTER_PICKUP_SCALE_FACTOR = 0.45

# Battle event playback (ADR 0013). Animation-driven phases derive their own duration from clip
# data instead -- these cover the phase kinds that have no clip to time against.
BATTLE_VALUE_TWEEN_SECONDS = 0.25
BATTLE_ANNOUNCEMENT_HOLD_SECONDS = 1.5
BATTLE_DEATH_POSE_HOLD_SECONDS = 1.0

# Strength is how far the HP bar's fill travels toward the role colour at the pulse's peak, 0-1.
# The role colours deliberately avoid every other colour in the same panel.
BATTLE_HIGHLIGHT_PULSE_PERIOD_SECONDS = 0.9
BATTLE_HIGHLIGHT_PULSE_STRENGTH = 0.55
BATTLE_ACTING_HIGHLIGHT_COLOR: pygame.typing.ColorLike = "deepskyblue"
BATTLE_RECEIVING_HIGHLIGHT_COLOR: pygame.typing.ColorLike = "orangered"

# The tint is multiplied into the sprite's pixels and then added: addition alone can only brighten,
# so on a light pixel every channel clips and the hue is lost. Strength is how much arrives at the
# instant of impact, 0-1, falling off linearly.
BATTLE_HIT_FLASH_DAMAGE_COLOR: pygame.typing.ColorLike = (255, 56, 96)  # rose, kept clear of orangered above
BATTLE_HIT_FLASH_HEALING_COLOR: pygame.typing.ColorLike = (56, 255, 96)
BATTLE_HIT_FLASH_STRENGTH = 0.85
BATTLE_HIT_FLASH_DURATION_SECONDS = 0.12

# The hop a HUD buff-row icon makes when its own effect ticks. The distance is the arc's peak in
# pixels, clamped by the scene to the row's clearance (_BUFF_ICON_HOP_CEILING); the duration is one
# whole up-and-down, kept inside the flinch clip carrying it.
BATTLE_BUFF_ICON_HOP_PIXELS = 4
BATTLE_BUFF_ICON_HOP_DURATION_SECONDS = 0.35

# Biome resolution (ADR 0016, PROJECT_BRIEF.md §9.3) -- distance_from_home, in screens, at which
# the GUI switches which Biome background/prop pool it draws. Never read by the domain; purely a
# GUI-side function of screen count. Playtesting-driven placeholders.
BIOME_DEAD_FOREST_THRESHOLD_SCREENS = 5
BIOME_FOREST_THRESHOLD_SCREENS = 15

# Prop placement (ADR 0016, PROJECT_BRIEF.md §9.3) -- distance-weighted scattered foreground
# dressing, thinning across a Biome's span and blending with the next Biome's pool near a
# boundary. Playtesting-driven placeholders.
PROP_MIN_COUNT_PER_SCREEN = 1
PROP_MAX_COUNT_PER_SCREEN = 4
PROP_BOUNDARY_BLEND_SCREENS = 3

# Prop rendering geometry (ADR 0016) -- where on screen a sampled prop can land and how large it
# draws, both playtesting-driven placeholders.
PROP_SCALE_FACTOR = 0.5
PROP_Y_BAND_MIN_FRACTION = 0.55
PROP_Y_BAND_MAX_FRACTION = 0.85

# How close a pixel must be (PixelArray.replace's normalized 0-1 distance) to a prop art file's
# own top-left corner pixel to be keyed transparent -- the shipped prop_*.png exports carry no
# alpha channel of their own, just a flat canvas color sampled from that corner. Placeholder until
# the art itself ships with real alpha.
PROP_BACKGROUND_KEY_DISTANCE = 0.06
