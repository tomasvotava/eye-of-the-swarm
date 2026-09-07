"""GUI-side pacing constants for the screen-walk state machine (ADR 0012) and battle event
playback (ADR 0013) -- playtesting-driven placeholders (PROJECT_BRIEF.md §8), not final tuning.
"""

WALK_TO_EXIT_DURATION_SECONDS = 0.6
WALK_TO_ENCOUNTER_DURATION_SECONDS = 0.6

# Fractions of the draw surface's width -- resolved only at draw time, not by update(dt), so the
# walk timer never needs to know the surface size (ADR 0012's entry/encounter/exit x-positions).
ENTRY_X_FRACTION = 0.1
ENCOUNTER_X_FRACTION = 0.5
EXIT_X_FRACTION = 0.9

# Battle event playback (ADR 0013). Animation-driven phases derive their own duration from clip
# data instead -- these two cover the phase kinds that have no clip to time against.
BATTLE_VALUE_TWEEN_SECONDS = 0.25
BATTLE_ANNOUNCEMENT_HOLD_SECONDS = 1.0
