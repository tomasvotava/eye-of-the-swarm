from eye.combat.actions import ActionKind, EffectTarget, InflictedEffect
from eye.combat.effects import EffectName
from eye.skilltree.catalog import CATALOG
from eye.skilltree.tree import Branch, SkillNodeId, SubBranch
from eye.skilltree.tuning import TIER_COSTS


def test_catalog_has_exactly_one_node_per_branch_sub_branch_tier_triple() -> None:
    expected_ids = {
        SkillNodeId(branch=branch, sub_branch=sub_branch, tier=tier)
        for branch in Branch
        for sub_branch in SubBranch
        for tier in range(3)
    }

    assert set(CATALOG.keys()) == expected_ids


def test_catalog_has_no_duplicate_skill_node_ids() -> None:
    assert len(CATALOG) == 18


def test_every_nodes_id_key_matches_its_own_id_field() -> None:
    for node_id, node in CATALOG.items():
        assert node.id == node_id


def test_every_nodes_cost_matches_its_tiers_cost() -> None:
    for node_id, node in CATALOG.items():
        assert node.cost == TIER_COSTS[node_id.tier]


def test_every_node_has_a_flavor_name() -> None:
    for node in CATALOG.values():
        assert node.name != ""


def test_barbed_struggle_unlocks_a_second_struggle_action_that_inflicts_runt_on_opponent() -> None:
    node = CATALOG[SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=2)]

    assert node.name == "Barbed Struggle"
    assert len(node.unlocked_actions) == 1
    action = node.unlocked_actions[0]
    assert action.kind is ActionKind.STRUGGLE
    assert action.inflicts == (InflictedEffect(effect=EffectName.RUNT, target=EffectTarget.OPPONENT),)


def test_coordinated_strike_unlocks_a_second_swarm_attack_action_with_hit_count_two() -> None:
    node = CATALOG[SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.ATTACK, tier=2)]

    assert node.name == "Coordinated Strike"
    assert len(node.unlocked_actions) == 1
    action = node.unlocked_actions[0]
    assert action.kind is ActionKind.SWARM_ATTACK
    assert action.hit_count == 2
    assert action.requires_full_meter is True


def test_ossified_shell_raises_defense_and_lowers_attack_in_one_delta() -> None:
    node = CATALOG[SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.DEFENSE, tier=2)]

    assert node.name == "Ossified Shell"
    assert node.stats_delta.defense > 0
    assert node.stats_delta.attack < 0


def test_swarm_defense_tier_zero_grants_ligneous_periderm_lifespan_effect() -> None:
    node = CATALOG[SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.DEFENSE, tier=0)]

    assert node.lifespan_effects == (EffectName.LIGNEOUS_PERIDERM,)


def test_swarm_utility_tier_zero_grants_proximity_discount_bonus() -> None:
    node = CATALOG[SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=0)]

    assert node.exploration_modifier.proximity_discount_bonus == 1.0


def test_swarm_utility_capstone_grants_both_seed_growth_and_proximity_discount() -> None:
    node = CATALOG[SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=2)]

    assert node.exploration_modifier.seed_growth_rate_multiplier == 1.2
    assert node.exploration_modifier.proximity_discount_bonus == 2.0


def test_self_utility_tiers_apply_multipliers_in_ascending_order() -> None:
    tier0 = CATALOG[SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.UTILITY, tier=0)]
    tier2 = CATALOG[SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.UTILITY, tier=2)]

    assert tier0.exploration_modifier.seed_growth_rate_multiplier == 1.1
    assert tier2.exploration_modifier.seed_growth_rate_multiplier == 1.25


def test_every_catalog_entry_has_a_non_empty_description() -> None:
    for node in CATALOG.values():
        assert node.description, f"{node.id} has no description"
