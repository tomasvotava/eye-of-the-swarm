import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, TypeIs

from eye.session.game import Game
from eye.skilltree.tree import Branch, SkillNode, SkillNodeId, SubBranch

SCHEMA_VERSION = 1


class SaveDataError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GameSnapshot:
    schema_version: int
    spores_available: int
    purchased_nodes: frozenset[SkillNodeId]
    matured_turf_positions: tuple[int, ...]


def encode(game: Game) -> str:
    skill_tree = game.skill_tree
    payload = {
        "schema_version": SCHEMA_VERSION,
        "spores_available": skill_tree.spores_available,
        "purchased_nodes": [
            {"branch": node_id.branch.name, "sub_branch": node_id.sub_branch.name, "tier": node_id.tier}
            for node_id in skill_tree.purchased_nodes
        ],
        "matured_turf_positions": list(game.matured_turf_positions),
    }
    return json.dumps(payload)


def decode(data: str, catalog: Iterable[SkillNode]) -> GameSnapshot:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SaveDataError(f"save data is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise SaveDataError(f"save data must be a JSON object, got {type(payload).__name__}")

    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise SaveDataError(f"unsupported schema_version: {schema_version!r}")

    spores_available = payload.get("spores_available")
    if not _is_int(spores_available):
        raise SaveDataError(f"spores_available must be an int, got {spores_available!r}")

    known_node_ids = {node.id for node in catalog}
    return GameSnapshot(
        schema_version=SCHEMA_VERSION,
        spores_available=spores_available,
        purchased_nodes=_decode_purchased_nodes(payload.get("purchased_nodes"), known_node_ids),
        matured_turf_positions=_decode_matured_turf_positions(payload.get("matured_turf_positions")),
    )


def _is_int(value: Any) -> TypeIs[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _decode_purchased_nodes(raw: Any, known_node_ids: set[SkillNodeId]) -> frozenset[SkillNodeId]:
    if not isinstance(raw, list):
        raise SaveDataError(f"purchased_nodes must be a list, got {type(raw).__name__}")

    node_ids = set[SkillNodeId]()
    for entry in raw:
        if not isinstance(entry, dict):
            raise SaveDataError(f"purchased_nodes entries must be objects, got {type(entry).__name__}")

        branch_name = entry.get("branch")
        if not isinstance(branch_name, str) or branch_name not in Branch.__members__:
            raise SaveDataError(f"unknown branch: {branch_name!r}")

        sub_branch_name = entry.get("sub_branch")
        if not isinstance(sub_branch_name, str) or sub_branch_name not in SubBranch.__members__:
            raise SaveDataError(f"unknown sub_branch: {sub_branch_name!r}")

        tier = entry.get("tier")
        if not _is_int(tier):
            raise SaveDataError(f"tier must be an int, got {tier!r}")

        node_id = SkillNodeId(branch=Branch[branch_name], sub_branch=SubBranch[sub_branch_name], tier=tier)
        if node_id not in known_node_ids:
            raise SaveDataError(f"purchased node not in the current skill tree catalog: {node_id}")
        node_ids.add(node_id)
    return frozenset(node_ids)


def _decode_matured_turf_positions(raw: Any) -> tuple[int, ...]:
    if not isinstance(raw, list):
        raise SaveDataError(f"matured_turf_positions must be a list, got {type(raw).__name__}")

    positions: list[int] = []
    for item in raw:
        if not _is_int(item):
            raise SaveDataError(f"matured_turf_positions must contain only ints, got {item!r}")
        positions.append(item)
    return tuple(positions)
