import pygame
import pytest

from eye.exploration.encounters import EncounterKind
from eye.exploration.events import EnemyEncountered
from eye.gui.app import _DEV_ASSET_VIEWER_ENV_VAR, App, _dev_asset_viewer_requested
from eye.gui.scene import EnterCombat, EnterExploration, EnterSkillTree, SceneTransition
from eye.gui.scenes.combat import CombatScene
from eye.gui.scenes.dev_assets import DevAssetViewerScene
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.scenes.skilltree import SkillTreeScene
from eye.persistence.codec import encode
from eye.session.game import Game
from tests.persistence.doubles import FakeSaveStore
from tests.session.doubles import ScriptedEncounterRandom


class _StubScene:
    def __init__(self) -> None:
        self.handled_pygame_events: list[pygame.event.Event] = []
        self.updates: list[float] = []
        self.drawn = False
        self.next_transition: SceneTransition | None = None

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        self.handled_pygame_events.append(pygame_event)

    def update(self, dt: float) -> SceneTransition | None:
        self.updates.append(dt)
        return self.next_transition

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


def test_dev_asset_viewer_requested_reflects_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(_DEV_ASSET_VIEWER_ENV_VAR, raising=False)
    assert _dev_asset_viewer_requested() is False

    monkeypatch.setenv(_DEV_ASSET_VIEWER_ENV_VAR, "1")
    assert _dev_asset_viewer_requested() is True


def test_app_boots_into_the_dev_asset_viewer_when_requested() -> None:
    app = App(
        pygame.Surface((64, 48)), pygame.Clock(), FakeSaveStore(), ScriptedEncounterRandom(()), dev_asset_viewer=True
    )

    assert isinstance(app.scene, DevAssetViewerScene)


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


def test_step_resolves_a_returned_transition_into_the_matching_scene() -> None:
    app = _app()
    stub = _StubScene()
    game = Game(ScriptedEncounterRandom(()))
    stub.next_transition = EnterSkillTree(game=game)
    app._scene = stub

    app.step(0.016)

    assert isinstance(app.scene, SkillTreeScene)


def test_resolve_transition_builds_an_exploration_scene_from_the_apps_own_atlas() -> None:
    app = _app()
    game = Game(ScriptedEncounterRandom(()))
    generation = game.start_generation()

    scene = app._resolve_transition(EnterExploration(generation=generation, game=game))

    assert isinstance(scene, ExplorationScene)
    assert scene._generation is generation
    assert scene._game is game
    assert scene._atlas is app._atlas


def test_resolve_transition_builds_a_skill_tree_scene_using_the_apps_own_save_store() -> None:
    store = FakeSaveStore()
    app = _app(store)
    game = Game(ScriptedEncounterRandom(()))

    scene = app._resolve_transition(EnterSkillTree(game=game))

    assert isinstance(scene, SkillTreeScene)
    assert scene._game is game
    assert scene._save_store is store


def test_resolve_transition_builds_a_combat_scene_using_the_apps_own_save_store() -> None:
    store = FakeSaveStore()
    app = _app(store)
    game = Game(ScriptedEncounterRandom([EncounterKind.ENEMY]))
    generation = game.start_generation()
    encounter = next(event for event in generation.advance() if isinstance(event, EnemyEncountered))

    scene = app._resolve_transition(EnterCombat(generation=generation, game=game, encounter=encounter))

    assert isinstance(scene, CombatScene)
    assert scene._save_store is store


def test_tick_returns_a_non_negative_frame_delta() -> None:
    app = _app()

    assert app.tick() >= 0.0
