from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.effects import EffectName
from eye.skilltree.tree import (
    Branch,
    ExplorationModifierDelta,
    SkillNode,
    SkillNodeId,
    StatsDelta,
    SubBranch,
)


def test_skill_node_id_with_equal_fields_compare_equal() -> None:
    first = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0)
    second = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0)

    assert first == second


def test_skill_node_id_is_hashable() -> None:
    node_id = SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=2)

    assert hash(node_id) == hash(SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=2))


def test_stats_delta_defaults_are_all_neutral() -> None:
    delta = StatsDelta()

    assert delta == StatsDelta(max_hp=0, attack=0, defense=0, recoil=0.0, meter_capacity=0, meter_fill_rate=0)


def test_exploration_modifier_delta_defaults_use_the_neutral_elements() -> None:
    delta = ExplorationModifierDelta()

    assert delta.seed_growth_rate_multiplier == 1.0
    assert delta.proximity_discount_bonus == 0.0


def test_skill_node_constructs_with_defaults() -> None:
    node_id = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.DEFENSE, tier=0)

    node = SkillNode(id=node_id, cost=10)

    assert node.id == node_id
    assert node.cost == 10
    assert node.name == ""
    assert node.stats_delta == StatsDelta()
    assert node.lifespan_effects == ()
    assert node.unlocked_actions == ()
    assert node.exploration_modifier == ExplorationModifierDelta()


def test_skill_nodes_with_the_same_id_and_cost_but_different_names_are_distinct() -> None:
    node_id = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.DEFENSE, tier=0)

    base = SkillNode(id=node_id, cost=10)
    named = SkillNode(id=node_id, cost=10, name="Ossified Shell")

    assert base != named


def test_skill_node_carries_multiple_lifespan_effects_and_unlocked_actions() -> None:
    node_id = SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.ATTACK, tier=1)
    action = ActionDefinition(kind=ActionKind.SWARM_ATTACK)

    node = SkillNode(
        id=node_id,
        cost=25,
        stats_delta=StatsDelta(attack=3),
        lifespan_effects=(EffectName.FIBROUS, EffectName.SPIKY_SKIN),
        unlocked_actions=(action,),
        exploration_modifier=ExplorationModifierDelta(seed_growth_rate_multiplier=1.1),
    )

    assert node.lifespan_effects == (EffectName.FIBROUS, EffectName.SPIKY_SKIN)
    assert node.unlocked_actions == (action,)
    assert node.exploration_modifier.seed_growth_rate_multiplier == 1.1


def test_skill_nodes_with_equal_fields_compare_equal() -> None:
    node_id = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.UTILITY, tier=0)

    assert SkillNode(id=node_id, cost=5) == SkillNode(id=node_id, cost=5)


def test_skill_node_description_defaults_to_empty_string() -> None:
    node = SkillNode(id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0), cost=1)

    assert node.description == ""
