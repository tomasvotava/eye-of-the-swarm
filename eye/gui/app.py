"""app.py: window/clock owner and the async main loop (ADR 0009/0010). `App` holds a single
current-`Scene` reference, swapped from each frame's `update()` return value, and `run()` wraps it
in a `while running: ... await asyncio.sleep(0)` loop so the same code runs unmodified under
pygbag's cooperative scheduler. `App` itself takes an already-built initial `Scene` and knows
nothing about what any scene is or does -- `Game`, `Generation`, and `eye.persistence` are all
`GameDriver`'s concern (ADR 0010), not this module's class. `run()` is where the two top-level
screens this Epic ships (`DevAssetViewerScene`, `GameDriver`) actually get chosen; a future
splash/menu epic adds screens here without touching `App`.
"""

from __future__ import annotations

import asyncio
import os
import random
from pathlib import Path

import pygame

from eye.gui.assets import build_art_atlas
from eye.gui.game_driver import GameDriver
from eye.gui.scene import Scene
from eye.gui.scenes.dev_assets import DevAssetViewerScene
from eye.persistence.port import SaveStore

_WINDOW_SIZE = (640, 480)
_MAX_FPS = 60
_TITLE = "The Eye of the Swarm"
_SPRITES_DIR = Path("eye/gui/sprites")

# Set (to any value) to boot straight into DevAssetViewerScene instead of the generational loop --
# a developer-only escape hatch, never the game's default entry point.
_DEV_ASSET_VIEWER_ENV_VAR = "EYE_DEV_ASSET_VIEWER"


def _dev_asset_viewer_requested() -> bool:
    return _DEV_ASSET_VIEWER_ENV_VAR in os.environ


class App:
    """Owns the current `Scene` and steps it. Takes an already-created `screen`/`clock`/
    `initial_scene` rather than constructing any of them itself, so tests can drive it against a
    headless `Surface` and an arbitrary `Scene` double without a real display or a real game --
    picking what to play is `run()`'s job, not this class's.
    """

    def __init__(self, screen: pygame.Surface, clock: pygame.Clock, initial_scene: Scene) -> None:
        self._screen = screen
        self._clock = clock
        self._scene = initial_scene
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
        next_scene = self._scene.update(dt)
        if next_scene is not None:
            self._scene = next_scene
        self._scene.draw(self._screen)

    def tick(self) -> float:
        return self._clock.tick(_MAX_FPS) / 1000


def _initial_scene(save_store: SaveStore | None, rng: random.Random, dev_asset_viewer: bool) -> Scene:
    atlas = build_art_atlas(_SPRITES_DIR)
    if dev_asset_viewer:
        return DevAssetViewerScene(atlas)
    return GameDriver(atlas, rng, save_store)


async def run(save_store: SaveStore | None = None, rng: random.Random | None = None) -> None:
    pygame.init()
    screen = pygame.display.set_mode(_WINDOW_SIZE, flags=pygame.SCALED)
    pygame.display.set_caption(_TITLE)
    clock = pygame.Clock()

    scene = _initial_scene(
        save_store,
        rng if rng is not None else random.Random(),  # noqa: S311 -- game RNG, not cryptographic
        dev_asset_viewer=_dev_asset_viewer_requested(),
    )
    app = App(screen, clock, scene)

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
