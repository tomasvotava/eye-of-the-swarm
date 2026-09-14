import json
import random
from pathlib import Path

import pytest

from eye.persistence import save
from eye.persistence.adapters.filesystem import FilesystemSaveStore
from eye.persistence.adapters.local_storage import LocalStorageSaveStore
from eye.persistence.codec import SCHEMA_VERSION, SaveDataError, encode
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from eye.skilltree.tree import Branch, SkillNodeId, SubBranch
from tests.persistence.adapters.test_local_storage import FakeJSStorage
from tests.persistence.doubles import FakeSaveStore
from tests.persistence.test_select import _install_fake_emscripten_platform
from tests.session.doubles import ScriptedEncounterRandom

_TIER0_SELF_ATTACK = SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0)


def _game(matured_turf_positions: tuple[int, ...] = ()) -> Game:
    return Game(
        rng=ScriptedEncounterRandom(()),
        matured_turf_positions=matured_turf_positions,
    )


def test_load_or_new_returns_a_fresh_game_when_there_is_no_save() -> None:
    store = FakeSaveStore(data=None)

    game = save.load_or_new(random.Random(), save_store=store)

    assert game.skill_tree.spores_available == 0
    assert game.matured_turf_positions == ()


def test_load_or_new_reconstructs_a_saved_game() -> None:
    original = _game(matured_turf_positions=(3, 7))
    original.skill_tree.add_spores(50)
    original.skill_tree.purchase(CATALOG[_TIER0_SELF_ATTACK])
    store = FakeSaveStore(data=encode(original))

    loaded = save.load_or_new(random.Random(), save_store=store)

    assert loaded.skill_tree.spores_available == original.skill_tree.spores_available
    assert loaded.skill_tree.purchased_nodes == original.skill_tree.purchased_nodes
    assert loaded.matured_turf_positions == (3, 7)


def test_load_or_new_falls_back_to_a_fresh_game_on_corrupt_data_and_leaves_it_on_disk() -> None:
    store = FakeSaveStore(data="not json")

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
    store = FakeSaveStore(data=stale)

    with pytest.warns(UserWarning, match="unreadable save data"):
        game = save.load_or_new(random.Random(), save_store=store)

    assert game.skill_tree.spores_available == 0


def test_persist_writes_the_encoded_game_to_the_store() -> None:
    game = _game()
    game.skill_tree.add_spores(5)
    store = FakeSaveStore()

    save.persist(game, save_store=store)

    assert store.load() == encode(game)


def test_default_save_path_resolves_under_a_platformdirs_user_data_dir() -> None:
    path = save._default_save_path("save-1")

    assert path.name == "save-1.json"
    assert "eye-of-the-swarm" in path.parent.as_posix()


def test_default_store_targets_the_same_path_as_slot_1() -> None:
    store = save.default_store()

    assert isinstance(store, FilesystemSaveStore)
    assert store._path == save._default_save_path("save-1")


def test_default_store_never_computes_a_filesystem_path_under_emscripten(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unreachable(namespace: str) -> None:
        raise AssertionError("the browser build has no filesystem save path to compute")

    _install_fake_emscripten_platform(monkeypatch, FakeJSStorage())
    monkeypatch.setattr(save, "_default_save_path", _unreachable)

    assert isinstance(save.default_store(), LocalStorageSaveStore)


def test_store_for_slot_targets_a_namespaced_path_per_slot() -> None:
    paths = set[Path]()
    for slot in (1, 2, 3):
        store = save.store_for_slot(slot)
        assert isinstance(store, FilesystemSaveStore)
        assert store._path == save._default_save_path(f"save-{slot}")
        paths.add(store._path)

    assert len(paths) == 3


def test_settings_store_targets_the_settings_namespace() -> None:
    store = save.settings_store()

    assert isinstance(store, FilesystemSaveStore)
    assert store._path == save._default_save_path("settings")


def test_narration_store_for_slot_targets_a_namespaced_path_per_slot() -> None:
    paths = set[Path]()
    for slot in (1, 2, 3):
        store = save.narration_store_for_slot(slot)
        assert isinstance(store, FilesystemSaveStore)
        assert store._path == save._default_save_path(f"narration-{slot}")
        paths.add(store._path)

    assert len(paths) == 3


def test_peek_returns_none_for_an_empty_store() -> None:
    store = FakeSaveStore(data=None)

    assert save.peek(store) is None


def test_peek_decodes_a_valid_snapshot_without_constructing_a_game() -> None:
    game = _game(matured_turf_positions=(3, 7))
    game.skill_tree.add_spores(50)
    store = FakeSaveStore(data=encode(game))

    snapshot = save.peek(store)

    assert snapshot is not None
    assert snapshot.spores_available == 50
    assert snapshot.matured_turf_positions == (3, 7)


def test_peek_propagates_save_data_error_on_corrupt_data() -> None:
    store = FakeSaveStore(data="not json")

    with pytest.raises(SaveDataError):
        save.peek(store)


def test_resolve_store_with_none_falls_back_to_slot_1() -> None:
    store = save._resolve_store(None)

    assert isinstance(store, FilesystemSaveStore)
    assert store._path == save._default_save_path("save-1")
