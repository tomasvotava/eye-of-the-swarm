"""Composition-root tuning constants -- playtesting-driven placeholders (PROJECT_BRIEF.md §8)."""

from eye.combat.tuning import AI_DIFFICULTY_MEDIUM_T

# single fixed difficulty; Strains are differentiated by their own StrainProfile stats
# (eye/bestiary.py), not by per-Strain AI greediness -- v1 has one Biome either way
ENEMY_AI_DIFFICULTY_T = AI_DIFFICULTY_MEDIUM_T
