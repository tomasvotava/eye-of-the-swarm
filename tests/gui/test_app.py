import pygame

from eye.gui.app import App
from eye.gui.scenes.exploration import ExplorationScene
from eye.persistence.codec import encode
from eye.session.game import Game
from tests.persistence.doubles import FakeSaveStore
from tests.session.doubles import ScriptedEncounterRandom


class _StubScene:
    def __init__(self) -> None:
        self.handled_pygame_events: list[pygame.event.Event] = []
        self.updates: list[float] = []
        self.drawn = False
        self.next_scene: _StubScene | None = None

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        self.handled_pygame_events.append(pygame_event)

    def update(self, dt: float) -> _StubScene | None:
        self.updates.append(dt)
        return self.next_scene

    def draw(self, surface: pygame.Surface) -> None:
        self.drawn = True


def _app(save_store: FakeSaveStore | None = None) -> App:
    store = save_store if save_store is not None else FakeSaveStore()
    return App(pygame.Surface((64, 48)), pygame.Clock(), store, ScriptedEncounterRandom(()))


def test_app_starts_a_fresh_generation_in_an_exploration_scene() -> None:
    app = _app()

    assert isinstance(app.scene, ExplorationScene)
    assert app.scene._generation.died is False
    assert app.running


def test_app_loads_the_saved_game_before_starting_the_generation() -> None:
    saved = Game(ScriptedEncounterRandom(()), matured_turf_positions=(3, 7))
    store = FakeSaveStore(data=encode(saved))

    scene = _app(store).scene

    assert isinstance(scene, ExplorationScene)
    assert scene._game.matured_turf_positions == (3, 7)


def test_quit_event_stops_the_app_without_reaching_the_scene() -> None:
    app = _app()
    app._scene = _StubScene()

    app.handle_event(pygame.event.Event(pygame.QUIT))

    assert app.running is False
    assert app._scene.handled_pygame_events == []


def test_non_quit_events_are_forwarded_to_the_current_scene() -> None:
    app = _app()
    stub = _StubScene()
    app._scene = stub

    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
    app.handle_event(event)

    assert stub.handled_pygame_events == [event]
    assert app.running


def test_step_draws_the_scene_and_stays_on_it_when_update_returns_none() -> None:
    app = _app()
    stub = _StubScene()
    app._scene = stub

    app.step(0.016)

    assert stub.updates == [0.016]
    assert stub.drawn
    assert app.scene is stub


def test_step_swaps_to_the_scene_returned_by_update() -> None:
    app = _app()
    stub = _StubScene()
    stub.next_scene = _StubScene()
    app._scene = stub

    app.step(0.016)

    assert app.scene is stub.next_scene
    assert app.scene.drawn


def test_tick_returns_a_non_negative_frame_delta() -> None:
    app = _app()

    assert app.tick() >= 0.0
