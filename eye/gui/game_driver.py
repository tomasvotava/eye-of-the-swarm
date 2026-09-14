"""GameDriver: owns the generational loop (ADR 0010). Combines `eye/tui/app.py`'s `_play()`/
`_play_generation()` and `eye/tui/combat.py`'s `play_battle()` into one frame-driven object --
`game`/`generation`/`save_store` live here as long-lived state, not threaded through every scene,
and the win/death/continue routing policy lives here too, not in whichever inner scene happens to
end a life. `app.py` hosts a `GameDriver` as just one top-level `Scene` among others (today, the
only alternative is `DevAssetViewerScene`); it never reaches into a `GameDriver` for its game state
and never needs to know a generational loop runs inside one.

Boots into the skill tree, not exploration, whenever a save already exists: spores are persisted
the moment a generation ends (`_resolve_battle_concluded()`, below), before the player has had a
chance to spend them, so quitting between a death and a purchase would otherwise strand banked
spores until the next death without ever offering a spend -- PROJECT_BRIEF.md §4 puts skill-tree
spending "between runs," and a fresh process launch is exactly that boundary. A brand-new game (no
prior save) skips straight to exploration instead, since there's nothing to spend yet. `_persist()`
also flushes this save file's narration history at the same checkpoints, for the same reason.
"""

from __future__ import annotations

import random
from typing import assert_never

import pygame

from eye.gui.assets import SpriteAtlas
from eye.gui.narration import NarrationTriggers, load_seen_triggers, persist_seen_triggers
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
    def __init__(
        self,
        atlas: SpriteAtlas,
        rng: random.Random,
        save_store: SaveStore | None = None,
        narration_store: SaveStore | None = None,
    ) -> None:
        self._atlas = atlas
        # Resolved once and held, per save.default_store()'s own contract, rather than passing
        # `save_store=None` to load_or_new()/persist() on every call.
        self._save_store = save_store if save_store is not None else save.default_store()
        self._narration_store = narration_store if narration_store is not None else save.narration_store_for_slot(1)
        # One redundant SaveStore.load() at boot -- load_or_new() below reads again internally --
        # rather than growing eye.persistence's shared (TUI + GUI) API for this GUI-only decision;
        # a store's load() is a cheap, side-effect-free read, and this runs once per process launch.
        had_existing_save = self._save_store.load() is not None
        self._game: Game = save.load_or_new(rng, self._save_store)
        # Only set once a life actually begins (__init__'s own start_new_generation() call below,
        # or a later Continue) -- staying None while the boot skill-tree screen is up, since
        # Game.start_generation() raises if called again before the one from __init__ ended.
        self._generation: Generation | None = None
        # This save file's own first-playthrough narration history (PROJECT_BRIEF.md §9.8) --
        # loaded once, then only ever grown by _persist() below, never re-read from disk.
        self._narration_seen = load_seen_triggers(self._narration_store)
        self._narration = NarrationTriggers.for_generation(self._narration_seen)
        self._scene: PlayScene = (
            SkillTreeScene(self._game, self._atlas, on_purchase=self._persist)
            if had_existing_save
            else self._start_new_generation()
        )

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
                return CombatScene(self._active_generation(), encounter, self._atlas, narration=self._narration)
            case BattleConcluded():
                return self._resolve_battle_concluded()
            case Continue():
                return self._start_new_generation()
            case _:
                assert_never(transition)

    def _resolve_battle_concluded(self) -> PlayScene:
        generation = self._active_generation()
        if not generation.died:
            return ExplorationScene.resuming_after_combat(
                generation, self._game, self._atlas, narration=self._narration
            )
        self._game.end_generation(generation)
        self._persist()
        return SkillTreeScene(self._game, self._atlas, on_purchase=self._persist)

    def _start_new_generation(self) -> ExplorationScene:
        self._generation = self._game.start_generation()
        # A fresh life re-sees FIRST_SEED_READY (a standing reminder) but not this save file's
        # already-shown first-playthrough beats -- a new instance, not a cleared old one, since
        # ExplorationScene/CombatScene hold a reference to it too.
        self._narration = NarrationTriggers.for_generation(self._narration_seen)
        return ExplorationScene.for_new_generation(self._generation, self._game, self._atlas, narration=self._narration)

    def _active_generation(self) -> Generation:
        # EnterCombat/BattleConcluded are only ever reported by CombatScene/ExplorationScene,
        # which GameDriver only ever constructs from _start_new_generation() -- see __init__ and
        # the Continue case above -- so self._generation is always set by the time either arrives.
        if self._generation is None:
            raise RuntimeError("no generation is active -- EnterCombat/BattleConcluded arrived before Continue")
        return self._generation

    def _persist(self) -> None:
        save.persist(self._game, self._save_store)
        self._narration_seen |= self._narration.persisted_seen
        persist_seen_triggers(self._narration_store, self._narration_seen)
