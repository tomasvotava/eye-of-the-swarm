import dataclasses

from eye.skilltree.events import NodePurchased, SkillTreeEvent
from eye.skilltree.tree import SkillNode, SkillNodeId


class SkillTree:
    def __init__(self, spores_available: int = 0) -> None:
        self._spores_available = spores_available
        self._purchased: set[SkillNodeId] = set()

    def add_spores(self, amount: int) -> None:
        self._spores_available += amount

    def is_purchased(self, node_id: SkillNodeId) -> bool:
        return node_id in self._purchased

    def can_purchase(self, node: SkillNode) -> bool:
        if self.is_purchased(node.id):
            return False
        if node.id.tier > 0 and not self.is_purchased(dataclasses.replace(node.id, tier=node.id.tier - 1)):
            return False
        return self._spores_available >= node.cost

    def purchase(self, node: SkillNode) -> list[SkillTreeEvent]:
        if not self.can_purchase(node):
            raise RuntimeError(f"node {node.id} cannot be purchased")
        self._spores_available -= node.cost
        self._purchased.add(node.id)
        return [NodePurchased(node_id=node.id, spores_remaining=self._spores_available)]

    @property
    def spores_available(self) -> int:
        return self._spores_available

    @property
    def purchased_nodes(self) -> frozenset[SkillNodeId]:
        return frozenset(self._purchased)
