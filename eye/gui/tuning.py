"""GUI-side pacing constants for the screen-walk state machine (ADR 0012) and the battle-event
reveal queue (ADR 0013) -- playtesting-driven placeholders (PROJECT_BRIEF.md §8), not final tuning.
"""

WALK_TO_EXIT_DURATION_SECONDS = 0.6
WALK_TO_ENCOUNTER_DURATION_SECONDS = 0.6

# Fractions of the draw surface's width -- resolved only at draw time, not by update(dt), so the
# walk timer never needs to know the surface size (ADR 0012's entry/encounter/exit x-positions).
ENTRY_X_FRACTION = 0.1
ENCOUNTER_X_FRACTION = 0.5
EXIT_X_FRACTION = 0.9

# How long a revealed battle event stays the only thing shown before the next one appears
# (CombatScene's reveal queue, ADR 0013). The queue's first event per batch reveals immediately;
# this gates every event after that.
BATTLE_EVENT_REVEAL_INTERVAL_SECONDS = 0.5
