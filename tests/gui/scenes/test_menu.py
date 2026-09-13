from pathlib import Path

import platformdirs
import pygame
import pytest

from eye.exploration.encounters import EncounterKind
from eye.gui.assets import build_placeholder_atlas
from eye.gui.game_driver import GameDriver
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.scenes.menu import KEY_ACTIONS, MenuAction, MenuScene, SlotStatus, _SlotView, _status_label
from eye.gui.scenes.skilltree import SkillTreeScene
from eye.persistence import save
from eye.persistence.codec import GameSnapshot, decode, encode
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from tests.session.doubles import ScriptedEncounterRandom


@pytest.fixture(autouse=True)
def _isolated_save_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Redirects save.store_for_slot()'s underlying paths under tmp_path -- MenuScene builds its own
    # stores internally (ADR 0017), so tests can't inject fakes and must isolate the real
    # filesystem adapter instead, the same paths a developer's own save data would otherwise occupy.
    monkeypatch.setattr(platformdirs, "user_data_dir", lambda _app_name: str(tmp_path))


def _write_slot(slot: int, data: str) -> None:
    save.store_for_slot(slot).save(data)


def _game_with_progress() -> Game:
    game = Game(ScriptedEncounterRandom(()), matured_turf_positions=(3, 7))
    game.skill_tree.add_spores(50)
    return game


def _scene() -> MenuScene:
    # A confirmed New Game action drives GameDriver into ExplorationScene.for_new_generation(),
    # which immediately calls advance() -- queue a NOTHING screen so it doesn't underflow
    # ScriptedEncounterRandom's scripted queue, matching test_game_driver.py's own convention.
    return MenuScene(build_placeholder_atlas(), ScriptedEncounterRandom((EncounterKind.NOTHING,)))


def _press(scene: MenuScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_key_actions_maps_the_expected_controls() -> None:
    assert KEY_ACTIONS[pygame.K_UP] is MenuAction.MOVE_UP
    assert KEY_ACTIONS[pygame.K_DOWN] is MenuAction.MOVE_DOWN
    assert KEY_ACTIONS[pygame.K_RETURN] is MenuAction.CONFIRM
    assert KEY_ACTIONS[pygame.K_SPACE] is MenuAction.CONFIRM


def test_slots_are_empty_when_no_save_data_exists() -> None:
    scene = _scene()

    assert [view.status for view in scene._slots] == [SlotStatus.EMPTY] * 3
    assert all(view.snapshot is None for view in scene._slots)


def test_slot_is_corrupt_when_save_data_is_undecodable() -> None:
    _write_slot(2, "not json")

    scene = _scene()

    assert scene._slots[0].status is SlotStatus.EMPTY
    assert scene._slots[1].status is SlotStatus.CORRUPT
    assert scene._slots[1].snapshot is None
    assert scene._slots[2].status is SlotStatus.EMPTY


def test_slot_is_valid_and_carries_the_decoded_snapshot() -> None:
    _write_slot(3, encode(_game_with_progress()))

    scene = _scene()

    view = scene._slots[2]
    assert view.status is SlotStatus.VALID
    assert view.snapshot is not None
    assert view.snapshot.spores_available == 50
    assert view.snapshot.matured_turf_positions == (3, 7)


def test_update_with_no_pending_action_returns_none() -> None:
    scene = _scene()

    assert scene.update(0.016) is None


def test_unmapped_key_is_ignored() -> None:
    scene = _scene()

    _press(scene, pygame.K_z)

    assert scene.update(0.016) is None


def test_non_keydown_event_is_ignored() -> None:
    scene = _scene()

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_DOWN))

    assert scene.update(0.016) is None


def test_move_down_from_the_last_slot_wraps_to_the_first_and_back() -> None:
    scene = _scene()

    _press(scene, pygame.K_DOWN)
    scene.update(0.016)
    _press(scene, pygame.K_DOWN)
    scene.update(0.016)
    _press(scene, pygame.K_DOWN)
    scene.update(0.016)

    assert scene._cursor == 0


def test_move_up_from_the_first_slot_wraps_to_the_last() -> None:
    scene = _scene()

    _press(scene, pygame.K_UP)
    scene.update(0.016)

    assert scene._cursor == 2


def test_confirm_builds_a_game_driver_bound_to_the_selected_slots_store() -> None:
    scene = _scene()

    _press(scene, pygame.K_DOWN)
    scene.update(0.016)  # cursor -> slot 2
    _press(scene, pygame.K_RETURN)
    transition = scene.update(0.016)

    assert isinstance(transition, GameDriver)
    assert transition._save_store is scene._slots[1].store
    assert isinstance(transition._scene, ExplorationScene)  # empty slot -> a fresh run, not the skill tree


def test_confirm_on_a_corrupt_slot_still_builds_a_game_driver() -> None:
    _write_slot(1, "not json")
    scene = _scene()

    _press(scene, pygame.K_SPACE)
    transition = scene.update(0.016)

    assert isinstance(transition, GameDriver)
    # GameDriver's own had_existing_save check (see GOTCHAS.md) reads whether load() returned
    # anything, not whether it decoded -- a corrupt slot's undecoded bytes still count as "existing",
    # so New Game on a corrupt slot boots into the skill-tree screen with nothing purchasable
    # instead of a fresh exploration run. Pinned here as the current (known, ticketed) behavior, not
    # endorsed -- fixing it is GameDriver's concern, not this menu's.
    assert isinstance(transition._scene, SkillTreeScene)


def test_status_label_for_an_empty_slot() -> None:
    view = _SlotView(1, save.store_for_slot(1), SlotStatus.EMPTY, None)

    assert _status_label(view) == "Empty -- New Game"


def test_status_label_for_a_corrupt_slot_reads_distinctly_from_empty() -> None:
    view = _SlotView(1, save.store_for_slot(1), SlotStatus.CORRUPT, None)

    assert _status_label(view) != _status_label(_SlotView(1, save.store_for_slot(1), SlotStatus.EMPTY, None))
    assert "Corrupt" in _status_label(view)


def _decoded_snapshot(game: Game) -> GameSnapshot:
    return decode(encode(game), CATALOG.values())


def test_status_label_for_a_valid_slot_with_no_matured_turf_shows_zero_progress() -> None:
    # The common case: a save written right after a death that granted spores but matured no turf.
    # A regression here would raise on max(()) with no default, crashing the menu's own draw().
    game = Game(ScriptedEncounterRandom(()), matured_turf_positions=())
    game.skill_tree.add_spores(4)
    view = _SlotView(1, save.store_for_slot(1), SlotStatus.VALID, _decoded_snapshot(game))

    assert _status_label(view) == "Spores: 4   Progress: 0 -- Continue"


def test_status_label_for_a_valid_slot_shows_spores_and_furthest_matured_position() -> None:
    view = _SlotView(1, save.store_for_slot(1), SlotStatus.VALID, _decoded_snapshot(_game_with_progress()))

    assert _status_label(view) == "Spores: 50   Progress: 7 -- Continue"


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise_with_a_mix_of_slot_statuses(surface_size: tuple[int, int]) -> None:
    _write_slot(2, "not json")
    _write_slot(3, encode(_game_with_progress()))
    scene = _scene()

    scene.draw(pygame.Surface(surface_size))
