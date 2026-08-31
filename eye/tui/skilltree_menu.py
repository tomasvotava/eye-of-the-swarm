from collections.abc import Callable, Iterator

from rich.console import Console

from eye.skilltree.catalog import CATALOG
from eye.skilltree.state import SkillTree
from eye.skilltree.tree import SkillNode
from eye.tui._input import next_line, parse_bounded_index

_DONE_COMMANDS = frozenset({"done", "continue", ""})


def run(
    console: Console,
    skill_tree: SkillTree,
    input_source: Iterator[str],
    on_purchase: Callable[[], None] = lambda: None,
) -> None:
    nodes = _ordered_nodes()
    while True:
        _render_nodes(console, skill_tree, nodes)
        console.print(f"Spores available: {skill_tree.spores_available}")
        console.print("Enter a node number to purchase, or 'done' to continue.")

        raw = next_line(input_source, "skilltree_menu.run")
        if raw.strip().lower() in _DONE_COMMANDS:
            return

        chosen_index = parse_bounded_index(raw, len(nodes))
        if chosen_index is None:
            console.print(f"Enter a number between 1 and {len(nodes)}, or 'done'.")
            continue
        node = nodes[chosen_index]

        try:
            skill_tree.purchase(node)
        except RuntimeError as exc:
            console.print(str(exc))
            continue

        console.print(f"Purchased {node.name or node.id}.", markup=False)
        on_purchase()


def _ordered_nodes() -> list[SkillNode]:
    return sorted(CATALOG.values(), key=lambda node: (node.id.branch.name, node.id.sub_branch.name, node.id.tier))


def _render_nodes(console: Console, skill_tree: SkillTree, nodes: list[SkillNode]) -> None:
    for index, node in enumerate(nodes, start=1):
        status = _status(skill_tree, node)
        console.print(
            f"{index}) [{status}] {node.name or node.id} "
            f"({node.id.branch.name}/{node.id.sub_branch.name} tier {node.id.tier}, cost {node.cost})",
            markup=False,
        )


def _status(skill_tree: SkillTree, node: SkillNode) -> str:
    if skill_tree.is_purchased(node.id):
        return "owned"
    if skill_tree.can_purchase(node):
        return "available"
    return "locked"
