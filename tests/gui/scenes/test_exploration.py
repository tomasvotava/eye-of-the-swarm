from collections.abc import Sequence

import pygame
import pytest

from eye.exploration.encounters import EncounterKind
from eye.exploration.events import EnemyEncountered
from eye.exploration.tuning import SEED_GROWTH_RATE_CAP, SEED_GROWTH_THRESHOLD
from eye.gui.assets import build_placeholder_atlas
from eye.gui.scene import EnterCombat
from eye.gui.scenes.exploration import KEY_ACTIONS, ExplorationAction, ExplorationScene
from eye.session.game import Game
from eye.session.generation import Generation
from tests.session.doubles import ScriptedEncounterRandom

_ADVANCES_TO_READY_SEED = int(SEED_GROWTH_THRESHOLD // SEED_GROWTH_RATE_CAP)


def _scene(kind_queue: Sequence[EncounterKind] = ()) -> tuple[ExplorationScene, Generation]:
    game = Game(ScriptedEncounterRandom(kind_queue))
    generation = game.start_generation()
    return ExplorationScene(generation, game, build_placeholder_atlas()), generation


def _press(scene: ExplorationScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_key_actions_maps_the_expected_controls() -> None:
    assert KEY_ACTIONS[pygame.K_SPACE] is ExplorationAction.ADVANCE
    assert KEY_ACTIONS[pygame.K_RETURN] is ExplorationAction.ADVANCE
    assert KEY_ACTIONS[pygame.K_p] is ExplorationAction.PLANT_SEED


def test_update_with_no_pending_action_returns_none_and_does_not_advance() -> None:
    scene, generation = _scene([EncounterKind.NOTHING])

    assert scene.update(0.016) is None
    assert generation.is_seed_ready is False


def test_unmapped_key_is_ignored() -> None:
    scene, generation = _scene([EncounterKind.NOTHING])

    _press(scene, pygame.K_z)

    assert scene.update(0.016) is None
    assert generation.is_seed_ready is False


def test_non_keydown_event_is_ignored() -> None:
    scene, _ = _scene()

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE))

    assert scene.update(0.016) is None


def test_advance_action_grows_the_seed_and_returns_none_when_nothing_happens() -> None:
    scene, generation = _scene([EncounterKind.NOTHING] * _ADVANCES_TO_READY_SEED)

    for _ in range(_ADVANCES_TO_READY_SEED):
        _press(scene, pygame.K_SPACE)
        assert scene.update(0.016) is None

    assert generation.is_seed_ready is True


def test_plant_seed_action_is_a_no_op_before_the_seed_is_ready() -> None:
    scene, generation = _scene([EncounterKind.NOTHING])

    _press(scene, pygame.K_p)
    scene.update(0.016)

    assert generation.pending_seeds == ()
    assert generation.is_seed_ready is False


def test_plant_seed_action_plants_once_the_seed_is_ready() -> None:
    scene, generation = _scene([EncounterKind.NOTHING] * _ADVANCES_TO_READY_SEED)
    for _ in range(_ADVANCES_TO_READY_SEED):
        _press(scene, pygame.K_SPACE)
        scene.update(0.016)
    assert generation.is_seed_ready is True

    _press(scene, pygame.K_p)
    scene.update(0.016)

    assert generation.is_seed_ready is False
    assert generation.pending_seeds != ()


def test_advance_action_returns_an_enter_combat_transition_on_encounter() -> None:
    scene, generation = _scene([EncounterKind.ENEMY])
    game = scene._game

    _press(scene, pygame.K_SPACE)
    transition = scene.update(0.016)

    assert isinstance(transition, EnterCombat)
    assert transition.generation is generation
    assert transition.game is game
    assert isinstance(transition.encounter, EnemyEncountered)


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    scene, _ = _scene([EncounterKind.NOTHING])

    scene.draw(pygame.Surface(surface_size))
