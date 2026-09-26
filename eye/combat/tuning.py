"""Every magic number in the combat engine — buff magnitudes, durations, AI and damage
constants. Values are playtesting-driven placeholders (PROJECT_BRIEF.md §8), not final tuning.
"""

FIBROUS_ATTACK_MAGNITUDE = 4.0
RUNT_ATTACK_MAGNITUDE = -4.0
LIGNEOUS_PERIDERM_DEFENSE_MAGNITUDE = 4.0
SPLINTERED_DEFENSE_MAGNITUDE = -4.0

STRUGGLE_BASE_POWER = 5.0
SWARM_ATTACK_BASE_POWER = 20.0
CRIT_CHANCE = 0.1
CRIT_MULTIPLIER = 1.5
DAMAGE_SPREAD = 0.2  # each landed hit is scaled by a uniform draw in [1 - spread, 1 + spread]
PROXIMITY_FALLOFF_RANGE = 10.0  # distance_from_turf at which proximity-to-hive scaling (SS5.1) reaches zero

AI_DIFFICULTY_EASY_T = 0.6
AI_DIFFICULTY_MEDIUM_T = 0.35
AI_DIFFICULTY_HARD_T = 0.15
AI_LETHAL_SCORE_BONUS = 10_000.0  # large enough that any lethal action always outranks any non-lethal one

WILTY_TRIGGER_CHANCE = 0.1
VEGETATIVE_TRIGGER_CHANCE = 0.1
ADRENALINE_REVIVE_HP = 10
DEFAULT_BATTLE_EFFECT_DURATION_TURNS = 3
TOXICITY_DAMAGE_PER_TURN = 3
NOURISHED_HEAL_PER_TURN = 3
SPIKY_SKIN_REFLECT_RATIO = 0.5
HEAL_BEFORE_DAMAGE_TICKS = False  # v1 default: Toxicity resolves before Nourished each turn

STRUGGLE_SCALES_WITH_DISTANCE = False  # v1 default: Struggle is distance-independent, unlike SwarmAttack

UPROOTED_BASE_CHANCE = 0.15
UPROOTED_DECAY_FACTOR = 1.0  # v1: no decay; lower later if procs feel too frequent
MAX_EXTRA_ACTIONS_PER_TURN = 10  # defensive ceiling only, not intended to bind at sane tuning values

RESONANCE_METER_PREFILL_RATIO = 0.3
METER_FILL_EDGE_SCALE = 0.37  # player meter-fill scale just inside PROXIMITY_FALLOFF_RANGE, before the cliff to 0


def uprooted_chance(extra_action_index: int) -> float:
    return UPROOTED_BASE_CHANCE * (UPROOTED_DECAY_FACTOR**extra_action_index)


def distance_falloff_scale(distance_from_turf: float, falloff_range: float) -> float:
    return max(0.0, 1.0 - distance_from_turf / falloff_range)


def meter_fill_scale(distance_from_turf: float, falloff_range: float) -> float:
    """1.0 at the turf, linear down to METER_FILL_EDGE_SCALE just inside `falloff_range`, 0.0 at or beyond it."""
    if not distance_from_turf < falloff_range:
        return 0.0
    return 1.0 - (1.0 - METER_FILL_EDGE_SCALE) * distance_from_turf / falloff_range
