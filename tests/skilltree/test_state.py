import pytest

from eye.skilltree.events import NodePurchased
from eye.skilltree.state import SkillTree
from eye.skilltree.tree import Branch, SkillNode, SkillNodeId, SubBranch


def _node(tier: int, cost: int, sub_branch: SubBranch = SubBranch.ATTACK) -> SkillNode:
    return SkillNode(id=SkillNodeId(branch=Branch.SELF, sub_branch=sub_branch, tier=tier), cost=cost)


def test_tier_zero_node_can_be_purchased_with_no_prerequisite() -> None:
    tree = SkillTree(spores_available=10)

    assert tree.can_purchase(_node(tier=0, cost=10)) is True


def test_tier_one_node_cannot_be_purchased_when_its_prerequisite_is_unpurchased() -> None:
    tree = SkillTree(spores_available=100)

    assert tree.can_purchase(_node(tier=1, cost=10)) is False


def test_tier_one_node_can_be_purchased_once_its_prerequisite_is_purchased() -> None:
    tree = SkillTree(spores_available=100)
    tree.purchase(_node(tier=0, cost=10))

    assert tree.can_purchase(_node(tier=1, cost=10)) is True


def test_already_purchased_node_cannot_be_purchased_again() -> None:
    tree = SkillTree(spores_available=100)
    node = _node(tier=0, cost=10)
    tree.purchase(node)

    assert tree.can_purchase(node) is False


def test_node_cannot_be_purchased_with_insufficient_spores() -> None:
    tree = SkillTree(spores_available=5)

    assert tree.can_purchase(_node(tier=0, cost=10)) is False


def test_purchase_at_exact_balance_leaves_zero_spores_available() -> None:
    tree = SkillTree(spores_available=10)

    tree.purchase(_node(tier=0, cost=10))

    assert tree.spores_available == 0


def test_purchase_deducts_cost_and_emits_node_purchased_with_remaining_spores() -> None:
    tree = SkillTree(spores_available=30)
    node = _node(tier=0, cost=10)

    events = tree.purchase(node)

    assert events == [NodePurchased(node_id=node.id, spores_remaining=20)]


def test_purchase_marks_the_node_as_purchased() -> None:
    tree = SkillTree(spores_available=10)
    node = _node(tier=0, cost=10)

    tree.purchase(node)

    assert tree.is_purchased(node.id) is True
    assert node.id in tree.purchased_nodes


def test_purchase_raises_when_it_cannot_be_purchased() -> None:
    tree = SkillTree(spores_available=5)

    with pytest.raises(RuntimeError):
        tree.purchase(_node(tier=0, cost=10))


def test_purchase_raising_leaves_spores_and_purchased_nodes_unchanged() -> None:
    tree = SkillTree(spores_available=5)
    node = _node(tier=0, cost=10)

    with pytest.raises(RuntimeError):
        tree.purchase(node)

    assert tree.spores_available == 5
    assert node.id not in tree.purchased_nodes


def test_add_spores_increases_the_available_balance() -> None:
    tree = SkillTree(spores_available=5)

    tree.add_spores(10)

    assert tree.spores_available == 15


def test_is_purchased_is_false_for_an_unpurchased_node() -> None:
    tree = SkillTree()

    assert tree.is_purchased(SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=0)) is False


def test_constructor_reconstitutes_purchased_nodes_without_spending_spores() -> None:
    node_id = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0)

    tree = SkillTree(spores_available=5, purchased_nodes=[node_id])

    assert tree.is_purchased(node_id) is True
    assert tree.purchased_nodes == frozenset({node_id})
    assert tree.spores_available == 5


def test_constructor_reconstitutes_a_higher_tier_without_its_prerequisite_purchased() -> None:
    tier_two = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=2)

    tree = SkillTree(purchased_nodes=[tier_two])

    assert tree.is_purchased(tier_two) is True
    tier_zero = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0)
    assert tree.is_purchased(tier_zero) is False


def test_constructor_defaults_to_no_purchased_nodes() -> None:
    tree = SkillTree()

    assert tree.purchased_nodes == frozenset()


def test_constructor_copies_the_purchased_nodes_iterable_rather_than_aliasing_it() -> None:
    node_id = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0)
    source = {node_id}

    tree = SkillTree(purchased_nodes=source)
    source.clear()

    assert tree.purchased_nodes == frozenset({node_id})
