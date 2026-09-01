import random
from collections.abc import Iterable

import pytest

from eye.persistence.codec import GameSnapshot, SaveDataError, decode, encode
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from eye.skilltree.state import SkillTree
from eye.skilltree.tree import Branch, SkillNode, SkillNodeId, SubBranch
from tests.session.doubles import ScriptedEncounterRandom


def _game(spores_available: int = 0, matured_turf_positions: tuple[int, ...] = ()) -> Game:
    return Game(
        rng=ScriptedEncounterRandom(()),
        skill_tree=SkillTree(spores_available=spores_available),
        matured_turf_positions=matured_turf_positions,
    )


def _decode(data: str, catalog: Iterable[SkillNode] = CATALOG.values()) -> GameSnapshot:
    return decode(data, catalog)


def test_round_trip_reconstructs_matching_skill_tree_and_matured_turf_positions() -> None:
    game = _game(spores_available=20, matured_turf_positions=(3, 7, 12))
    self_attack_tier0 = CATALOG[SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0)]
    swarm_defense_tier0 = CATALOG[SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.DEFENSE, tier=0)]
    game.skill_tree.purchase(self_attack_tier0)
    game.skill_tree.purchase(swarm_defense_tier0)

    snapshot = _decode(encode(game))
    rebuilt = Game(
        rng=random.Random(),
        skill_tree=SkillTree(spores_available=snapshot.spores_available, purchased_nodes=snapshot.purchased_nodes),
        matured_turf_positions=snapshot.matured_turf_positions,
    )

    assert rebuilt.skill_tree.spores_available == game.skill_tree.spores_available
    assert rebuilt.skill_tree.purchased_nodes == game.skill_tree.purchased_nodes
    assert rebuilt.matured_turf_positions == game.matured_turf_positions


def test_encode_writes_schema_version_1() -> None:
    snapshot = _decode(encode(_game()))

    assert snapshot.schema_version == 1


def test_round_trip_with_no_purchases_and_no_matured_turf() -> None:
    snapshot = _decode(encode(_game()))

    assert snapshot == GameSnapshot(
        schema_version=1, spores_available=0, purchased_nodes=frozenset(), matured_turf_positions=()
    )


def test_decode_raises_on_malformed_json() -> None:
    with pytest.raises(SaveDataError):
        _decode("not json")


def test_decode_raises_when_top_level_is_not_an_object() -> None:
    with pytest.raises(SaveDataError):
        _decode("[]")


def test_decode_raises_on_missing_required_field() -> None:
    with pytest.raises(SaveDataError):
        _decode('{"schema_version": 1, "purchased_nodes": [], "matured_turf_positions": []}')


def test_decode_raises_when_spores_available_has_the_wrong_type() -> None:
    payload = '{"schema_version": 1, "spores_available": "10", "purchased_nodes": [], "matured_turf_positions": []}'

    with pytest.raises(SaveDataError):
        _decode(payload)


def test_decode_raises_on_unrecognized_schema_version() -> None:
    payload = '{"schema_version": 2, "spores_available": 0, "purchased_nodes": [], "matured_turf_positions": []}'

    with pytest.raises(SaveDataError):
        _decode(payload)


def test_decode_raises_on_unknown_branch_in_purchased_nodes() -> None:
    payload = (
        '{"schema_version": 1, "spores_available": 0, '
        '"purchased_nodes": [{"branch": "NOT_A_BRANCH", "sub_branch": "ATTACK", "tier": 0}], '
        '"matured_turf_positions": []}'
    )

    with pytest.raises(SaveDataError):
        _decode(payload)


def test_decode_raises_on_unknown_sub_branch_in_purchased_nodes() -> None:
    payload = (
        '{"schema_version": 1, "spores_available": 0, '
        '"purchased_nodes": [{"branch": "SELF", "sub_branch": "NOT_A_SUB_BRANCH", "tier": 0}], '
        '"matured_turf_positions": []}'
    )

    with pytest.raises(SaveDataError):
        _decode(payload)


def test_decode_raises_for_a_purchased_node_that_does_not_exist_in_the_catalog() -> None:
    payload = (
        '{"schema_version": 1, "spores_available": 0, '
        '"purchased_nodes": [{"branch": "SELF", "sub_branch": "ATTACK", "tier": 99}], '
        '"matured_turf_positions": []}'
    )

    with pytest.raises(SaveDataError):
        _decode(payload)


def test_decode_accepts_a_purchased_node_present_in_an_injected_catalog() -> None:
    node = SkillNode(id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0), cost=10)
    payload = (
        '{"schema_version": 1, "spores_available": 0, '
        '"purchased_nodes": [{"branch": "SELF", "sub_branch": "ATTACK", "tier": 0}], '
        '"matured_turf_positions": []}'
    )

    snapshot = decode(payload, catalog=[node])

    assert snapshot.purchased_nodes == frozenset({node.id})


def test_decode_raises_when_matured_turf_positions_contains_a_non_int() -> None:
    payload = (
        '{"schema_version": 1, "spores_available": 0, "purchased_nodes": [], "matured_turf_positions": ["not an int"]}'
    )

    with pytest.raises(SaveDataError):
        _decode(payload)
