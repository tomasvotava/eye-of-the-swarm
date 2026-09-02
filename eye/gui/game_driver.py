"""GameDriver: owns the generational loop (ADR 0010). Combines `eye/tui/app.py`'s `_play()`/
`_play_generation()` and `eye/tui/combat.py`'s `play_battle()` into one frame-driven object --
`game`/`generation`/`save_store` live here as long-lived state, not threaded through every scene,
and the win/death/continue routing policy lives here too, not in whichever inner scene happens to
end a life. `app.py` hosts a `GameDriver` as just one top-level `Scene` among others (today, the
only alternative is `DevAssetViewerScene`); it never reaches into a `GameDriver` for its game state
and never needs to know a generational loop runs inside one.
"""

import random
from typing import assert_never

import pygame

from eye.gui.assets import SpriteAtlas
from eye.gui.play_scene import BattleConcluded, Continue, EnterCombat, PlayScene, PlaySceneTransition
from eye.gui.scene import Scene
from eye.gui.scenes.combat import CombatScene
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.scenes.skilltree import SkillTreeScene
from eye.persistence import save
from eye.persistence.port import SaveStore
from eye.session.game import Game
from eye.session.generation import Generation


class GameDriver:
    def __init__(self, atlas: SpriteAtlas, rng: random.Random, save_store: SaveStore | None = None) -> None:
        self._atlas = atlas
        # Resolved once and held, per save.default_store()'s own contract, rather than passing
        # `save_store=None` to load_or_new()/persist() on every call.
        self._save_store = save_store if save_store is not None else save.default_store()
        self._game: Game = save.load_or_new(rng, self._save_store)
        self._generation: Generation = self._game.start_generation()
        self._scene: PlayScene = ExplorationScene(self._generation, self._game, self._atlas)

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        self._scene.handle_pygame_event(pygame_event)

    def update(self, dt: float) -> Scene | None:
        transition = self._scene.update(dt)
        if transition is not None:
            self._scene = self._resolve(transition)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        self._scene.draw(surface)

    def _resolve(self, transition: PlaySceneTransition) -> PlayScene:
        match transition:
            case EnterCombat(encounter=encounter):
                return CombatScene(self._generation, encounter, self._atlas)
            case BattleConcluded():
                return self._resolve_battle_concluded()
            case Continue():
                self._generation = self._game.start_generation()
                return ExplorationScene(self._generation, self._game, self._atlas)
            case _:
                assert_never(transition)

    def _resolve_battle_concluded(self) -> PlayScene:
        if not self._generation.died:
            return ExplorationScene(self._generation, self._game, self._atlas)
        self._game.end_generation(self._generation)
        self._persist()
        return SkillTreeScene(self._game, self._atlas, on_purchase=self._persist)

    def _persist(self) -> None:
        save.persist(self._game, self._save_store)
