from dataclasses import dataclass

from eye.skilltree.tree import SkillNodeId


@dataclass(frozen=True, slots=True)
class NodePurchased:
    node_id: SkillNodeId
    spores_remaining: int


type SkillTreeEvent = NodePurchased
