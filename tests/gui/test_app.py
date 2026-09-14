from __future__ import annotations

import pygame
import pytest

from eye.exploration.encounters import EncounterKind
from eye.gui.app import _DEV_ASSET_VIEWER_ENV_VAR, App, _dev_asset_viewer_requested, _initial_scene
from eye.gui.game_driver import GameDriver
from eye.gui.scene import Scene
from eye.gui.scenes.dev_assets import DevAssetViewerScene
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


def _app(initial_scene: Scene | None = None) -> App:
    return App(pygame.Surface((64, 48)), pygame.Clock(), initial_scene or _StubScene())


def test_initial_scene_returns_a_game_driver_by_default() -> None:
    # A brand-new game immediately fires advance() for its first screen via for_new_generation()
    # (ADR 0012), so the queue needs at least one entry even though this test doesn't otherwise
    # care what that screen holds.
    scene = _initial_scene(FakeSaveStore(), ScriptedEncounterRandom([EncounterKind.NOTHING]), dev_asset_viewer=False)

    assert isinstance(scene, GameDriver)


def test_initial_scene_returns_the_dev_asset_viewer_when_requested() -> None:
    scene = _initial_scene(FakeSaveStore(), ScriptedEncounterRandom(()), dev_asset_viewer=True)

    assert isinstance(scene, DevAssetViewerScene)


def test_dev_asset_viewer_requested_reflects_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_DEV_ASSET_VIEWER_ENV_VAR, raising=False)
    assert _dev_asset_viewer_requested() is False

    monkeypatch.setenv(_DEV_ASSET_VIEWER_ENV_VAR, "1")
    assert _dev_asset_viewer_requested() is True


def test_app_starts_on_the_scene_it_was_given() -> None:
    scene = _StubScene()

    app = _app(scene)

    assert app.scene is scene
    assert app.running


def test_quit_event_stops_the_app_without_reaching_the_scene() -> None:
    stub = _StubScene()
    app = _app(stub)

    app.handle_event(pygame.event.Event(pygame.QUIT))

    assert app.running is False
    assert stub.handled_pygame_events == []


def test_non_quit_events_are_forwarded_to_the_current_scene() -> None:
    stub = _StubScene()
    app = _app(stub)

    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
    app.handle_event(event)

    assert stub.handled_pygame_events == [event]
    assert app.running


def test_step_draws_the_scene_and_stays_on_it_when_update_returns_none() -> None:
    stub = _StubScene()
    app = _app(stub)

    app.step(0.016)

    assert stub.updates == [0.016]
    assert stub.drawn
    assert app.scene is stub


def test_step_swaps_to_the_scene_returned_by_update() -> None:
    stub = _StubScene()
    stub.next_scene = _StubScene()
    app = _app(stub)

    app.step(0.016)

    assert app.scene is stub.next_scene
    assert app.scene.drawn


def test_tick_returns_a_non_negative_frame_delta() -> None:
    app = _app()

    assert app.tick() >= 0.0
