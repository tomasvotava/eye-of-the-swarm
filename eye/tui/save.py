import random
import warnings
from pathlib import Path

import platformdirs

from eye.combat.ai import ActionChooser
from eye.persistence.codec import SaveDataError, decode, encode
from eye.persistence.port import SaveStore
from eye.persistence.select import default_save_store
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from eye.skilltree.state import SkillTree

_APP_NAME = "eye-of-the-swarm"
_SAVE_FILENAME = "save.json"


def load_or_new(rng: random.Random, chooser: ActionChooser, save_store: SaveStore | None = None) -> Game:
    store = _resolve_store(save_store)
    raw = store.load()
    if raw is None:
        return Game(rng, chooser)

    try:
        snapshot = decode(raw, CATALOG.values())
    except SaveDataError as exc:
        warnings.warn(f"ignoring unreadable save data: {exc}", stacklevel=2)
        return Game(rng, chooser)

    skill_tree = SkillTree(spores_available=snapshot.spores_available, purchased_nodes=snapshot.purchased_nodes)
    return Game(rng, chooser, skill_tree=skill_tree, matured_turf_positions=snapshot.matured_turf_positions)


def persist(game: Game, save_store: SaveStore | None = None) -> None:
    _resolve_store(save_store).save(encode(game))


def _resolve_store(save_store: SaveStore | None) -> SaveStore:
    return save_store if save_store is not None else default_save_store(_default_save_path())


def _default_save_path() -> Path:
    return Path(platformdirs.user_data_dir(_APP_NAME)) / _SAVE_FILENAME
