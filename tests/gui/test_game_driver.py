from collections.abc import Sequence

import pygame
import pytest

from eye.character import Character
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.stats import Stats
from eye.exploration.encounters import EncounterKind
from eye.gui.assets import build_placeholder_atlas
from eye.gui.game_driver import GameDriver
from eye.gui.scenes.combat import ACTION_KEYS, CombatScene
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.scenes.skilltree import _ROWS, SkillTreeScene
from eye.gui.tuning import WALK_TO_ENCOUNTER_DURATION_SECONDS
from eye.persistence.codec import decode, encode
from eye.session.game import Game
from eye.session.generation import Generation
from eye.skilltree.catalog import CATALOG
from tests.persistence.doubles import FakeSaveStore
from tests.session.doubles import ScriptedEncounterRandom

_STATS = Stats(max_hp=20, attack=5, defense=2, meter_capacity=100, meter_fill_rate=1)
_ACTIONS = (ActionDefinition(kind=ActionKind.STRUGGLE, name="Struggle"),)


def _driver(
    kind_queue: Sequence[EncounterKind] = (EncounterKind.NOTHING, EncounterKind.NOTHING),
    save_store: FakeSaveStore | None = None,
) -> GameDriver:
    # Defaults to two queued NOTHING screens rather than an empty queue: ExplorationScene's
    # for_new_generation() (ADR 0012) fires advance() once immediately, whether at construction or
    # after a later Continue -- one entry covers GameDriver.__init__()'s own throwaway generation
    # (immediately overwritten by _driver_with() below), a second covers a genuine Continue later
    # in the same test, and tests that never reach either case just leave the rest unused.
    return GameDriver(build_placeholder_atlas(), ScriptedEncounterRandom(kind_queue), save_store or FakeSaveStore())


def _generation(stats: Stats = _STATS, character: Character | None = None) -> Generation:
    return Generation(
        character=character or Character(current_hp=stats.max_hp, max_hp=stats.max_hp),
        stats=stats,
        actions=_ACTIONS,
        rng=ScriptedEncounterRandom([EncounterKind.ENEMY]),
        starting_screen=0,
        matured_turfs=(),
    )


def _driver_with(generation: Generation, save_store: FakeSaveStore | None = None) -> GameDriver:
    # Bypasses GameDriver's own Game.start_generation() the same way test_combat.py's
    # _game_owning() bypasses it -- so a test can pin exact combat stats -- and wires ownership by
    # hand the same way start_generation() would have.
    driver = _driver(save_store=save_store)
    driver._game._current_generation = generation
    driver._generation = generation
    driver._scene = ExplorationScene.for_new_generation(generation, driver._game, driver._atlas)
    return driver


def _advance(driver: GameDriver) -> None:
    # Drives a full screen-walk lap (ADR 0012): ExplorationScene.for_new_generation() already
    # joins at AT_ENTRY with the screen's encounter pending, so one ADVANCE press plus a walk to
    # the marker is enough to reveal it -- the EnterCombat/HUD-message outcome every caller here
    # is actually after.
    driver.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    driver.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)


def _drive_battle_to_conclusion(driver: GameDriver, max_frames: int = 200) -> None:
    for _ in range(max_frames):
        driver.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=ACTION_KEYS[0]))
        driver.update(0.016)
        if not isinstance(driver._scene, CombatScene):
            return
    raise AssertionError("battle did not conclude within max_frames")


def test_construction_starts_a_fresh_generation_in_an_exploration_scene_for_a_brand_new_game() -> None:
    driver = _driver()

    assert isinstance(driver._scene, ExplorationScene)
    assert driver._scene._generation.died is False


def test_construction_boots_into_the_skill_tree_when_a_save_already_exists() -> None:
    saved = Game(ScriptedEncounterRandom(()), matured_turf_positions=(3, 7))
    store = FakeSaveStore(data=encode(saved))

    driver = _driver(save_store=store)

    assert isinstance(driver._scene, SkillTreeScene)
    assert driver._game.matured_turf_positions == (3, 7)
    assert driver._generation is None  # no life started yet -- Continue starts the first one


def test_continue_from_the_boot_skill_tree_starts_a_new_generation() -> None:
    saved = Game(ScriptedEncounterRandom(()), matured_turf_positions=(3,))
    driver = _driver(save_store=FakeSaveStore(data=encode(saved)))
    assert isinstance(driver._scene, SkillTreeScene)

    driver.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
    driver.update(0.016)

    assert isinstance(driver._scene, ExplorationScene)
    assert driver._generation is not None
    assert driver._scene._generation.died is False


def test_active_generation_raises_if_no_generation_has_started_yet() -> None:
    driver = _driver(save_store=FakeSaveStore(data=encode(Game(ScriptedEncounterRandom(())))))
    assert driver._generation is None

    with pytest.raises(RuntimeError, match="no generation is active"):
        driver._active_generation()


def test_update_never_returns_a_top_level_transition() -> None:
    driver = _driver([EncounterKind.ENEMY])

    assert driver.update(0.016) is None
    _advance(driver)
    assert isinstance(driver._scene, CombatScene)
    assert driver.update(0.016) is None


def test_enter_combat_transition_swaps_to_a_combat_scene() -> None:
    driver = _driver([EncounterKind.ENEMY])

    _advance(driver)

    assert isinstance(driver._scene, CombatScene)


def test_win_returns_to_exploration_without_persisting() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    driver = _driver_with(_generation(stats=overwhelming))

    _advance(driver)
    assert isinstance(driver._scene, CombatScene)

    _drive_battle_to_conclusion(driver)

    assert isinstance(driver._scene, ExplorationScene)
    assert driver._save_store.load() is None  # a win alone produces no SeedsMatured/SporesAwarded


def test_loss_ends_the_generation_persists_and_returns_a_skill_tree_scene() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=fragile, character=Character(current_hp=5, max_hp=5))
    store = FakeSaveStore()
    driver = _driver_with(generation, save_store=store)

    _advance(driver)
    _drive_battle_to_conclusion(driver)

    assert isinstance(driver._scene, SkillTreeScene)
    assert generation.died is True
    driver._game.start_generation()  # raises if end_generation() didn't clear Game's current generation
    raw = store.load()
    assert raw is not None
    snapshot = decode(raw, CATALOG.values())
    assert snapshot.spores_available == driver._game.skill_tree.spores_available


def test_skill_tree_purchases_persist_through_the_wired_on_purchase_hook() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=fragile, character=Character(current_hp=5, max_hp=5))
    store = FakeSaveStore()
    driver = _driver_with(generation, save_store=store)
    _advance(driver)
    _drive_battle_to_conclusion(driver)
    assert isinstance(driver._scene, SkillTreeScene)
    node = _ROWS[0][0]
    driver._game.skill_tree.add_spores(node.cost)

    driver._scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    driver._scene.update(0.016)

    raw = store.load()
    assert raw is not None
    snapshot = decode(raw, CATALOG.values())
    assert node.id in snapshot.purchased_nodes


def test_continue_after_skill_tree_starts_a_new_generation() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    driver = _driver_with(_generation(stats=fragile, character=Character(current_hp=5, max_hp=5)))
    _advance(driver)
    _drive_battle_to_conclusion(driver)
    assert isinstance(driver._scene, SkillTreeScene)

    driver.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
    driver.update(0.016)

    assert isinstance(driver._scene, ExplorationScene)
    assert driver._scene._generation.died is False


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    driver = _driver()

    driver.draw(pygame.Surface(surface_size))
