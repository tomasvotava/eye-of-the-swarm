"""Every magic number in the combat engine — buff magnitudes, durations, AI and damage
constants. Values are playtesting-driven placeholders (PROJECT_BRIEF.md §8), not final tuning.
"""

FIBROUS_ATTACK_MAGNITUDE = 4.0
RUNT_ATTACK_MAGNITUDE = -4.0
LIGNEOUS_PERIDERM_DEFENSE_MAGNITUDE = 4.0
SPLINTERED_DEFENSE_MAGNITUDE = -4.0

STRUGGLE_BASE_POWER = 5.0
SWARM_ATTACK_BASE_POWER = 20.0
SWARM_ATTACK_FALLOFF_RANGE = 10.0  # distance_from_turf at which SwarmAttack power reaches zero
