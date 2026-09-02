"""app.py: window/clock owner and the async main loop (ADR 0009). `App` holds a single
current-`Scene` reference, swapped from each frame's `update()` return value, and `run()` wraps it
in a `while running: ... await asyncio.sleep(0)` loop so the same code runs unmodified under
pygbag's cooperative scheduler.
"""

import asyncio
import random

import pygame

from eye.gui.assets import build_placeholder_atlas
from eye.gui.scene import Scene
from eye.gui.scenes.exploration import ExplorationScene
from eye.persistence import save
from eye.persistence.port import SaveStore

_WINDOW_SIZE = (1280, 720)
_MAX_FPS = 60
_TITLE = "The Eye of the Swarm"


class App:
    """Owns the current `Scene` and steps it. Takes an already-created `screen`/`clock` rather
    than constructing them itself, so tests can drive it against a headless `Surface` without a
    real display -- window/display setup is `run()`'s job, not this class's.
    """

    def __init__(self, screen: pygame.Surface, clock: pygame.Clock, save_store: SaveStore, rng: random.Random) -> None:
        self._screen = screen
        self._clock = clock
        game = save.load_or_new(rng, save_store)
        atlas = build_placeholder_atlas()
        self._scene: Scene = ExplorationScene(game.start_generation(), game, atlas, save_store=save_store)
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


async def run(save_store: SaveStore | None = None, rng: random.Random | None = None) -> None:
    pygame.init()
    screen = pygame.display.set_mode(_WINDOW_SIZE)
    pygame.display.set_caption(_TITLE)
    clock = pygame.Clock()

    store = save_store if save_store is not None else save.default_store()
    app = App(screen, clock, store, rng if rng is not None else random.Random())  # noqa: S311 -- game RNG, not cryptographic

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
