import io

import pytest
from rich.console import Console

from eye.skilltree.catalog import CATALOG
from eye.skilltree.state import SkillTree
from eye.skilltree.tree import Branch, SkillNodeId, SubBranch
from eye.tui import skilltree_menu

_TIER0_SELF_ATTACK = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0)
_TIER1_SELF_ATTACK = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=1)


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, width=120), buffer


def _index_of(node_id: SkillNodeId) -> int:
    nodes = skilltree_menu._ordered_nodes()
    return next(i for i, node in enumerate(nodes, start=1) if node.id == node_id)


def test_run_lists_node_names_and_costs() -> None:
    console, buffer = _console()
    skill_tree = SkillTree()

    skilltree_menu.run(console, skill_tree, iter(["done"]))

    output = buffer.getvalue()
    node = CATALOG[_TIER0_SELF_ATTACK]
    assert node.name in output
    assert str(node.cost) in output


def test_run_lists_node_status_words() -> None:
    console, buffer = _console()
    skill_tree = SkillTree(spores_available=100)

    skilltree_menu.run(console, skill_tree, iter(["done"]))

    output = buffer.getvalue()
    assert "available" in output
    assert "locked" in output


def test_run_done_exits_without_purchasing() -> None:
    console, _ = _console()
    skill_tree = SkillTree(spores_available=100)

    skilltree_menu.run(console, skill_tree, iter(["done"]))

    assert skill_tree.purchased_nodes == frozenset()


def test_run_purchases_a_valid_node_by_number() -> None:
    console, buffer = _console()
    skill_tree = SkillTree(spores_available=100)
    index = _index_of(_TIER0_SELF_ATTACK)

    skilltree_menu.run(console, skill_tree, iter([str(index), "done"]))

    assert _TIER0_SELF_ATTACK in skill_tree.purchased_nodes
    assert "Nasty Tendrils" in buffer.getvalue()


def test_run_invokes_on_purchase_callback() -> None:
    console, _ = _console()
    skill_tree = SkillTree(spores_available=100)
    index = _index_of(_TIER0_SELF_ATTACK)
    calls = []

    skilltree_menu.run(console, skill_tree, iter([str(index), "done"]), on_purchase=lambda: calls.append(1))

    assert calls == [1]


def test_run_shows_error_for_unmet_prerequisite_and_keeps_looping() -> None:
    console, buffer = _console()
    skill_tree = SkillTree(spores_available=100)
    index = _index_of(_TIER1_SELF_ATTACK)

    skilltree_menu.run(console, skill_tree, iter([str(index), "done"]))

    assert _TIER1_SELF_ATTACK not in skill_tree.purchased_nodes
    assert "cannot be purchased" in buffer.getvalue()


def test_run_shows_error_for_insufficient_spores() -> None:
    console, buffer = _console()
    skill_tree = SkillTree(spores_available=0)
    index = _index_of(_TIER0_SELF_ATTACK)

    skilltree_menu.run(console, skill_tree, iter([str(index), "done"]))

    assert _TIER0_SELF_ATTACK not in skill_tree.purchased_nodes
    assert "cannot be purchased" in buffer.getvalue()


def test_run_reprompts_on_out_of_range_number() -> None:
    console, buffer = _console()
    skill_tree = SkillTree(spores_available=100)

    skilltree_menu.run(console, skill_tree, iter(["9999", "done"]))

    assert "done" in buffer.getvalue().lower()
    assert skill_tree.purchased_nodes == frozenset()


def test_run_raises_when_input_is_exhausted_without_a_done_command() -> None:
    console, _ = _console()
    skill_tree = SkillTree()

    with pytest.raises(RuntimeError):
        skilltree_menu.run(console, skill_tree, iter([]))
