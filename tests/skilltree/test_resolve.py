from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.effects import EffectName
from eye.combat.stats import Stats
from eye.skilltree.resolve import (
    resolved_actions,
    resolved_exploration_modifiers,
    resolved_lifespan_effects,
    resolved_stats,
)
from eye.skilltree.state import SkillTree
from eye.skilltree.tree import Branch, ExplorationModifierDelta, SkillNode, SkillNodeId, StatsDelta, SubBranch

_BASE_STATS = Stats(max_hp=100, attack=10, defense=5, meter_capacity=100, meter_fill_rate=10)


def _node(
    tier: int,
    sub_branch: SubBranch = SubBranch.ATTACK,
    branch: Branch = Branch.SELF,
    cost: int = 10,
    stats_delta: StatsDelta | None = None,
    lifespan_effects: tuple[EffectName, ...] = (),
    unlocked_actions: tuple[ActionDefinition, ...] = (),
    exploration_modifier: ExplorationModifierDelta | None = None,
) -> SkillNode:
    return SkillNode(
        id=SkillNodeId(branch=branch, sub_branch=sub_branch, tier=tier),
        cost=cost,
        stats_delta=stats_delta if stats_delta is not None else StatsDelta(),
        lifespan_effects=lifespan_effects,
        unlocked_actions=unlocked_actions,
        exploration_modifier=exploration_modifier if exploration_modifier is not None else ExplorationModifierDelta(),
    )


def _tree_with_purchases(*node_ids: SkillNodeId) -> SkillTree:
    tree = SkillTree(spores_available=10_000)
    for node_id in node_ids:
        tree.purchase(SkillNode(id=node_id, cost=0))
    return tree


def test_resolved_stats_is_a_noop_on_an_empty_tree() -> None:
    node = _node(tier=0, stats_delta=StatsDelta(attack=3))
    tree = SkillTree()

    assert resolved_stats(_BASE_STATS, tree, (node,)) == _BASE_STATS


def test_resolved_stats_sums_a_single_purchased_nodes_delta() -> None:
    node = _node(tier=0, stats_delta=StatsDelta(attack=3, defense=2))
    tree = _tree_with_purchases(node.id)

    result = resolved_stats(_BASE_STATS, tree, (node,))

    assert result == Stats(max_hp=100, attack=13, defense=7, meter_capacity=100, meter_fill_rate=10)


def test_resolved_stats_sums_multiple_purchased_nodes_deltas() -> None:
    first = _node(tier=0, sub_branch=SubBranch.ATTACK, stats_delta=StatsDelta(attack=3))
    second = _node(tier=0, sub_branch=SubBranch.DEFENSE, stats_delta=StatsDelta(defense=4, max_hp=15))
    tree = _tree_with_purchases(first.id, second.id)

    result = resolved_stats(_BASE_STATS, tree, (first, second))

    assert result == Stats(max_hp=115, attack=13, defense=9, meter_capacity=100, meter_fill_rate=10)


def test_resolved_stats_ignores_unpurchased_nodes() -> None:
    purchased = _node(tier=0, sub_branch=SubBranch.ATTACK, stats_delta=StatsDelta(attack=3))
    unpurchased = _node(tier=0, sub_branch=SubBranch.DEFENSE, stats_delta=StatsDelta(defense=99))
    tree = _tree_with_purchases(purchased.id)

    result = resolved_stats(_BASE_STATS, tree, (purchased, unpurchased))

    assert result.defense == _BASE_STATS.defense


def test_resolved_lifespan_effects_is_empty_for_an_empty_tree() -> None:
    node = _node(tier=0, lifespan_effects=(EffectName.FIBROUS,))
    tree = SkillTree()

    assert resolved_lifespan_effects(tree, (node,)) == ()


def test_resolved_lifespan_effects_returns_a_single_purchased_nodes_effects() -> None:
    node = _node(tier=0, lifespan_effects=(EffectName.FIBROUS, EffectName.SPIKY_SKIN))
    tree = _tree_with_purchases(node.id)

    assert resolved_lifespan_effects(tree, (node,)) == (EffectName.FIBROUS, EffectName.SPIKY_SKIN)


def test_resolved_lifespan_effects_dedupes_an_effect_granted_by_multiple_nodes() -> None:
    first = _node(tier=0, sub_branch=SubBranch.ATTACK, lifespan_effects=(EffectName.FIBROUS,))
    second = _node(tier=0, sub_branch=SubBranch.DEFENSE, lifespan_effects=(EffectName.FIBROUS, EffectName.NOURISHED))
    tree = _tree_with_purchases(first.id, second.id)

    result = resolved_lifespan_effects(tree, (first, second))

    assert result == (EffectName.FIBROUS, EffectName.NOURISHED)


def test_a_purchased_node_with_no_lifespan_effects_contributes_nothing() -> None:
    node = _node(tier=0)
    tree = _tree_with_purchases(node.id)

    assert resolved_lifespan_effects(tree, (node,)) == ()


def test_resolved_actions_is_just_base_actions_for_an_empty_tree() -> None:
    base_action = ActionDefinition(kind=ActionKind.STRUGGLE)
    node = _node(tier=0, unlocked_actions=(ActionDefinition(kind=ActionKind.STRUGGLE, name="Extra"),))
    tree = SkillTree()

    assert resolved_actions(tree, (node,), (base_action,)) == (base_action,)


def test_resolved_actions_appends_purchased_nodes_unlocked_actions_in_catalog_order() -> None:
    base_action = ActionDefinition(kind=ActionKind.STRUGGLE)
    first = _node(
        tier=0,
        sub_branch=SubBranch.ATTACK,
        unlocked_actions=(ActionDefinition(kind=ActionKind.STRUGGLE, name="First"),),
    )
    second = _node(
        tier=0,
        sub_branch=SubBranch.DEFENSE,
        unlocked_actions=(ActionDefinition(kind=ActionKind.SWARM_ATTACK, name="Second"),),
    )
    tree = _tree_with_purchases(first.id, second.id)

    result = resolved_actions(tree, (first, second), (base_action,))

    assert result == (base_action, first.unlocked_actions[0], second.unlocked_actions[0])


def test_a_purchased_node_with_no_unlocked_actions_contributes_nothing() -> None:
    base_action = ActionDefinition(kind=ActionKind.STRUGGLE)
    node = _node(tier=0)
    tree = _tree_with_purchases(node.id)

    assert resolved_actions(tree, (node,), (base_action,)) == (base_action,)


def test_resolved_exploration_modifiers_is_neutral_for_an_empty_tree() -> None:
    node = _node(tier=0, exploration_modifier=ExplorationModifierDelta(seed_growth_rate_multiplier=1.5))
    tree = SkillTree()

    assert resolved_exploration_modifiers(tree, (node,)) == ExplorationModifierDelta()


def test_resolved_exploration_modifiers_multiplies_seed_growth_and_sums_proximity_discount() -> None:
    first = _node(
        tier=0,
        sub_branch=SubBranch.ATTACK,
        exploration_modifier=ExplorationModifierDelta(seed_growth_rate_multiplier=1.1, proximity_discount_bonus=1.0),
    )
    second = _node(
        tier=0,
        sub_branch=SubBranch.DEFENSE,
        exploration_modifier=ExplorationModifierDelta(seed_growth_rate_multiplier=1.2, proximity_discount_bonus=2.0),
    )
    tree = _tree_with_purchases(first.id, second.id)

    result = resolved_exploration_modifiers(tree, (first, second))

    assert result.seed_growth_rate_multiplier == 1.1 * 1.2
    assert result.proximity_discount_bonus == 3.0
