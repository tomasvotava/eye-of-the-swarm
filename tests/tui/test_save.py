import json
import random

import pytest

from eye.persistence.codec import SCHEMA_VERSION, encode
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from eye.skilltree.tree import Branch, SkillNodeId, SubBranch
from eye.tui import save
from tests.session.doubles import ScriptedEncounterRandom

_TIER0_SELF_ATTACK = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0)


class _FakeSaveStore:
    def __init__(self, data: str | None = None) -> None:
        self._data = data

    def load(self) -> str | None:
        return self._data

    def save(self, data: str) -> None:
        self._data = data


def _game(matured_turf_positions: tuple[int, ...] = ()) -> Game:
    return Game(
        rng=ScriptedEncounterRandom(()),
        matured_turf_positions=matured_turf_positions,
    )


def test_load_or_new_returns_a_fresh_game_when_there_is_no_save() -> None:
    store = _FakeSaveStore(data=None)

    game = save.load_or_new(random.Random(), save_store=store)

    assert game.skill_tree.spores_available == 0
    assert game.matured_turf_positions == ()


def test_load_or_new_reconstructs_a_saved_game() -> None:
    original = _game(matured_turf_positions=(3, 7))
    original.skill_tree.add_spores(50)
    original.skill_tree.purchase(CATALOG[_TIER0_SELF_ATTACK])
    store = _FakeSaveStore(data=encode(original))

    loaded = save.load_or_new(random.Random(), save_store=store)

    assert loaded.skill_tree.spores_available == original.skill_tree.spores_available
    assert loaded.skill_tree.purchased_nodes == original.skill_tree.purchased_nodes
    assert loaded.matured_turf_positions == (3, 7)


def test_load_or_new_falls_back_to_a_fresh_game_on_corrupt_data_and_leaves_it_on_disk() -> None:
    store = _FakeSaveStore(data="not json")

    with pytest.warns(UserWarning, match="unreadable save data"):
        game = save.load_or_new(random.Random(), save_store=store)

    assert game.skill_tree.spores_available == 0
    assert store.load() == "not json"


def test_load_or_new_falls_back_to_a_fresh_game_when_a_purchased_node_is_stale() -> None:
    stale = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "spores_available": 10,
            "purchased_nodes": [{"branch": "SELF", "sub_branch": "ATTACK", "tier": 999}],
            "matured_turf_positions": [],
        }
    )
    store = _FakeSaveStore(data=stale)

    with pytest.warns(UserWarning, match="unreadable save data"):
        game = save.load_or_new(random.Random(), save_store=store)

    assert game.skill_tree.spores_available == 0


def test_persist_writes_the_encoded_game_to_the_store() -> None:
    game = _game()
    game.skill_tree.add_spores(5)
    store = _FakeSaveStore()

    save.persist(game, save_store=store)

    assert store.load() == encode(game)


def test_default_save_path_resolves_under_a_platformdirs_user_data_dir() -> None:
    path = save._default_save_path()

    assert path.name == "save.json"
    assert "eye-of-the-swarm" in path.parent.as_posix()
