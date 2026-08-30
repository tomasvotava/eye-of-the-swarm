"""Every magic number in the v1 skill-tree catalog — costs and per-node stat/exploration-modifier
magnitudes. Values are playtesting-driven placeholders (PROJECT_BRIEF.md §8), not final tuning.
Constants are named structurally by (branch, sub_branch, tier), not by a node's flavor name —
names are cosmetic and narratively flexible (PROJECT_BRIEF.md's terminology note), tuning is not.
"""

TIER_COSTS = (10, 20, 40)  # index by SkillNodeId.tier; uniform per tier across both branches

SELF_ATTACK_TIER0_ATTACK_DELTA = 2
SELF_ATTACK_TIER1_RECOIL_DELTA = -0.1  # Stats.recoil has no non-zero baseline yet (ADR 0002); placeholder only

SELF_DEFENSE_TIER0_DEFENSE_DELTA = 2
SELF_DEFENSE_TIER1_MAX_HP_DELTA = 15
SELF_DEFENSE_TIER2_DEFENSE_DELTA = 8
SELF_DEFENSE_TIER2_ATTACK_DELTA = -3

SELF_UTILITY_TIER0_SEED_GROWTH_MULTIPLIER = 1.1
SELF_UTILITY_TIER1_METER_FILL_RATE_DELTA = 2
SELF_UTILITY_TIER2_SEED_GROWTH_MULTIPLIER = 1.25

SWARM_ATTACK_TIER0_METER_FILL_RATE_DELTA = 1

SWARM_DEFENSE_TIER1_DEFENSE_DELTA = 3

SWARM_UTILITY_TIER0_PROXIMITY_DISCOUNT_BONUS = 1.0
SWARM_UTILITY_TIER2_SEED_GROWTH_MULTIPLIER = 1.2
SWARM_UTILITY_TIER2_PROXIMITY_DISCOUNT_BONUS = 2.0
