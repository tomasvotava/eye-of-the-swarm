import random
import sys
import warnings
from pathlib import Path

from eye.persistence.codec import SaveDataError, decode, encode
from eye.persistence.port import SaveStore
from eye.persistence.select import default_save_store
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from eye.skilltree.state import SkillTree

_APP_NAME = "eye-of-the-swarm"
_SAVE_FILENAME = "save.json"


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


def default_store() -> SaveStore:
    """Construct the `SaveStore` that `load_or_new()`/`persist()` fall back to when called with
    `save_store=None`, for a caller that must hold one concrete instance up front (e.g. the GUI
    driver, which threads the same store through every scene) rather than letting each call
    resolve it anew.
    """
    return _resolve_store(None)


def _resolve_store(save_store: SaveStore | None) -> SaveStore:
    if save_store is not None:
        return save_store
    # emscripten's default_save_store() ignores filesystem_path entirely -- skip computing it
    # there so platformdirs (unneeded and pygbag-hostile) never has to be a web dependency.
    if sys.platform == "emscripten":
        return default_save_store()
    return default_save_store(_default_save_path())


def _default_save_path() -> Path:
    import platformdirs

    return Path(platformdirs.user_data_dir(_APP_NAME)) / _SAVE_FILENAME
