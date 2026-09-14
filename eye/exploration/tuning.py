"""Every magic number in the exploration engine — encounter-kind weights, resource pickup
magnitudes, and per-Strain distance gates. Values are playtesting-driven placeholders
(PROJECT_BRIEF.md §8), not final tuning.
"""

ENCOUNTER_KIND_WEIGHT_ENEMY = 1.0
ENCOUNTER_KIND_WEIGHT_EFFECT_PICKUP = 1.0
ENCOUNTER_KIND_WEIGHT_RESOURCE_PICKUP = 1.0
ENCOUNTER_KIND_WEIGHT_NOTHING = 1.0

RESOURCE_HEAL_MAGNITUDE = 10
RESOURCE_SPORES_MAGNITUDE = 5
RESOURCE_SEED_GROWTH_MAGNITUDE = 10
RESOURCE_DISTANCE_DISCOUNT_MAGNITUDE = 1

# distance_from_home below which a Strain never spawns (eye/exploration/encounters.py assembles
# these into STRAIN_MIN_DISTANCE) -- keeps a fresh generation's earliest screens from rolling a
# Strain sized for much deeper exploration.
STRAIN_MIN_DISTANCE_TUMBLEWEED = 0
STRAIN_MIN_DISTANCE_BEATLE = 0
STRAIN_MIN_DISTANCE_FLEA = 2
STRAIN_MIN_DISTANCE_PHIDIZVIK = 5
STRAIN_MIN_DISTANCE_GOLEM = 8

SEED_GROWTH_THRESHOLD = 100.0
SEED_GROWTH_BASE_RATE = 5.0
SEED_GROWTH_DISTANCE_FACTOR = 2.0
SEED_GROWTH_RATE_CAP = 25.0


def seed_growth_rate(distance: float) -> float:
    return min(SEED_GROWTH_RATE_CAP, SEED_GROWTH_BASE_RATE + SEED_GROWTH_DISTANCE_FACTOR * distance)
