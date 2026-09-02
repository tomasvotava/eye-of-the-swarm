"""app.py: window/clock owner and the async main loop (ADR 0009). `App` holds a single
current-`Scene` reference, swapped by resolving each frame's `update()` return value, and `run()`
wraps it in a `while running: ... await asyncio.sleep(0)` loop so the same code runs unmodified
under pygbag's cooperative scheduler. It's also the composition root for the GUI layer (ADR 0009):
the only module that imports every concrete `Scene` implementation, so no scene module needs to
import another -- and the owner of the `SpriteAtlas`/`SaveStore` instances every scene is built
with, so no scene threads `save_store` to a sibling it doesn't otherwise need.
"""

import asyncio
import os
import random
from typing import assert_never

import pygame

from eye.gui.assets import build_placeholder_atlas
from eye.gui.scene import EnterCombat, EnterExploration, EnterSkillTree, Scene, SceneTransition
from eye.gui.scenes.combat import CombatScene
from eye.gui.scenes.dev_assets import DevAssetViewerScene
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.scenes.skilltree import SkillTreeScene
from eye.persistence import save
from eye.persistence.port import SaveStore

_WINDOW_SIZE = (1280, 720)
_MAX_FPS = 60
_TITLE = "The Eye of the Swarm"

# Set (to any value) to boot straight into DevAssetViewerScene instead of the generational loop --
# a developer-only escape hatch, never the game's default entry point.
_DEV_ASSET_VIEWER_ENV_VAR = "EYE_DEV_ASSET_VIEWER"


def _dev_asset_viewer_requested() -> bool:
    return _DEV_ASSET_VIEWER_ENV_VAR in os.environ


class App:
    """Owns the current `Scene` and steps it. Takes an already-created `screen`/`clock` rather
    than constructing them itself, so tests can drive it against a headless `Surface` without a
    real display -- window/display setup is `run()`'s job, not this class's.
    """

    def __init__(
        self,
        screen: pygame.Surface,
        clock: pygame.Clock,
        save_store: SaveStore,
        rng: random.Random,
        dev_asset_viewer: bool = False,
    ) -> None:
        self._screen = screen
        self._clock = clock
        self._atlas = build_placeholder_atlas()
        self._save_store = save_store
        if dev_asset_viewer:
            self._scene: Scene = DevAssetViewerScene(self._atlas)
        else:
            game = save.load_or_new(rng, save_store)
            self._scene = ExplorationScene(game.start_generation(), game, self._atlas)
        self._running = True

    @property
    def running(self) -> bool:
        return self._running

    @property
    def scene(self) -> Scene:
        return self._scene

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self._running = False
            return
        self._scene.handle_pygame_event(event)

    def step(self, dt: float) -> None:
        transition = self._scene.update(dt)
        if transition is not None:
            self._scene = self._resolve_transition(transition)
        self._scene.draw(self._screen)

    def _resolve_transition(self, transition: SceneTransition) -> Scene:
        match transition:
            case EnterCombat(generation=generation, game=game, encounter=encounter):
                return CombatScene(generation, game, encounter, self._atlas, save_store=self._save_store)
            case EnterExploration(generation=generation, game=game):
                return ExplorationScene(generation, game, self._atlas)
            case EnterSkillTree(game=game):
                return SkillTreeScene(game, self._atlas, save_store=self._save_store)
            case _:
                assert_never(transition)

    def tick(self) -> float:
        return self._clock.tick(_MAX_FPS) / 1000


async def run(save_store: SaveStore | None = None, rng: random.Random | None = None) -> None:
    pygame.init()
    screen = pygame.display.set_mode(_WINDOW_SIZE)
    pygame.display.set_caption(_TITLE)
    clock = pygame.Clock()

    store = save_store if save_store is not None else save.default_store()
    app = App(
        screen,
        clock,
        store,
        rng if rng is not None else random.Random(),  # noqa: S311 -- game RNG, not cryptographic
        dev_asset_viewer=_dev_asset_viewer_requested(),
    )

    dt = 0.0
    while app.running:
        for event in pygame.event.get():
            app.handle_event(event)
        app.step(dt)
        pygame.display.flip()
        dt = app.tick()
        await asyncio.sleep(0)


def main() -> None:
    asyncio.run(run())
