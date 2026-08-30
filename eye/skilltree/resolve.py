"""Pure functions bridging SkillTree purchase state into Stats/effects/actions/exploration modifiers
(ADR 0003). Each `catalog` iterable is consumed exactly once per call; a single-use generator
passed to more than one resolver is exhausted after the first.
"""

import dataclasses
from collections.abc import Iterable, Sequence

from eye.combat.actions import ActionDefinition
from eye.combat.effects import EffectName
from eye.combat.stats import Stats
from eye.skilltree.state import SkillTree
from eye.skilltree.tree import ExplorationModifierDelta, SkillNode


def _purchased(tree: SkillTree, catalog: Iterable[SkillNode]) -> Iterable[SkillNode]:
    return (node for node in catalog if tree.is_purchased(node.id))


def resolved_stats(base: Stats, tree: SkillTree, catalog: Iterable[SkillNode]) -> Stats:
    nodes = list(_purchased(tree, catalog))
    return dataclasses.replace(
        base,
        max_hp=base.max_hp + sum(node.stats_delta.max_hp for node in nodes),
        attack=base.attack + sum(node.stats_delta.attack for node in nodes),
        defense=base.defense + sum(node.stats_delta.defense for node in nodes),
        recoil=base.recoil + sum(node.stats_delta.recoil for node in nodes),
        meter_capacity=base.meter_capacity + sum(node.stats_delta.meter_capacity for node in nodes),
        meter_fill_rate=base.meter_fill_rate + sum(node.stats_delta.meter_fill_rate for node in nodes),
    )


def resolved_lifespan_effects(tree: SkillTree, catalog: Iterable[SkillNode]) -> tuple[EffectName, ...]:
    effects = (effect for node in _purchased(tree, catalog) for effect in node.lifespan_effects)
    return tuple(dict.fromkeys(effects))


def resolved_actions(
    tree: SkillTree, catalog: Iterable[SkillNode], base_actions: Sequence[ActionDefinition]
) -> tuple[ActionDefinition, ...]:
    unlocked = (action for node in _purchased(tree, catalog) for action in node.unlocked_actions)
    return (*base_actions, *unlocked)


def resolved_exploration_modifiers(tree: SkillTree, catalog: Iterable[SkillNode]) -> ExplorationModifierDelta:
    neutral = ExplorationModifierDelta()
    seed_growth_rate_multiplier = neutral.seed_growth_rate_multiplier
    proximity_discount_bonus = neutral.proximity_discount_bonus
    for node in _purchased(tree, catalog):
        seed_growth_rate_multiplier *= node.exploration_modifier.seed_growth_rate_multiplier
        proximity_discount_bonus += node.exploration_modifier.proximity_discount_bonus
    return ExplorationModifierDelta(
        seed_growth_rate_multiplier=seed_growth_rate_multiplier, proximity_discount_bonus=proximity_discount_bonus
    )
