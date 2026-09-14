import random
import sys
import warnings
from pathlib import Path

from eye.persistence.codec import GameSnapshot, SaveDataError, decode, encode
from eye.persistence.port import SaveStore
from eye.persistence.select import default_save_store
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from eye.skilltree.state import SkillTree

_APP_NAME = "eye-of-the-swarm"


def load_or_new(rng: random.Random, save_store: SaveStore | None = None) -> Game:
    store = _resolve_store(save_store)
    raw = store.load()
    if raw is None:
        return Game(rng)

    try:
        snapshot = decode(raw, CATALOG.values())
    except SaveDataError as exc:
        warnings.warn(f"ignoring unreadable save data: {exc}", stacklevel=2)
        return Game(rng)

    skill_tree = SkillTree(spores_available=snapshot.spores_available, purchased_nodes=snapshot.purchased_nodes)
    return Game(rng, skill_tree=skill_tree, matured_turf_positions=snapshot.matured_turf_positions)


def persist(game: Game, save_store: SaveStore | None = None) -> None:
    _resolve_store(save_store).save(encode(game))


def store_for_slot(slot: int) -> SaveStore:
    return _namespaced_store(f"save-{slot}")


def settings_store() -> SaveStore:
    return _namespaced_store("settings")


def narration_store_for_slot(slot: int) -> SaveStore:
    return _namespaced_store(f"narration-{slot}")


def _namespaced_store(namespace: str) -> SaveStore:
    # emscripten's default_save_store() ignores filesystem_path entirely -- skip computing it
    # there so platformdirs (unneeded and pygbag-hostile) never has to be a web dependency.
    if sys.platform == "emscripten":
        return default_save_store(namespace)
    return default_save_store(namespace, _default_save_path(namespace))


def peek(save_store: SaveStore) -> GameSnapshot | None:
    """Load and decode a slot's snapshot without constructing a `Game`, letting `SaveDataError`
    propagate rather than swallowing it the way `load_or_new()` does -- the menu needs to tell the
    player a slot is corrupt, not silently treat it as empty.
    """
    raw = save_store.load()
    return None if raw is None else decode(raw, CATALOG.values())


def default_store() -> SaveStore:
    """Construct the `SaveStore` that `load_or_new()`/`persist()` fall back to when called with
    `save_store=None`, for a caller that must hold one concrete instance up front (e.g. the GUI
    driver, which threads the same store through every scene) rather than letting each call
    resolve it anew. Callers with no slot of their own -- the TUI, and the GUI before a slot is
    picked -- get slot 1.
    """
    return store_for_slot(1)


def _resolve_store(save_store: SaveStore | None) -> SaveStore:
    return save_store if save_store is not None else default_store()


def _default_save_path(namespace: str) -> Path:
    import platformdirs

    return Path(platformdirs.user_data_dir(_APP_NAME)) / f"{namespace}.json"
