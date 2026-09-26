from collections.abc import Sequence
from pathlib import Path

import platformdirs
import pygame
import pytest

from eye.character import Character
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.stats import Stats
from eye.exploration.encounters import EncounterKind
from eye.gui.assets import build_placeholder_atlas
from eye.gui.audio import AudioManager, SoundKey
from eye.gui.game_driver import GameDriver
from eye.gui.narration import NarrationTrigger, RecurringNarration
from eye.gui.scenes.combat import ACTION_KEYS, CombatScene
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.scenes.settings import SettingsScene
from eye.gui.scenes.skilltree import _ROWS, SkillTreeScene
from eye.gui.tuning import WALK_TO_ENCOUNTER_DURATION_SECONDS
from eye.persistence.codec import decode, encode
from eye.session.game import Game
from eye.session.generation import Generation
from eye.skilltree.catalog import CATALOG
from tests.gui.doubles import build_fake_audio_manager, build_spy_audio_manager
from tests.persistence.doubles import FakeSaveStore
from tests.session.doubles import ScriptedEncounterRandom

_STATS = Stats(max_hp=20, attack=5, defense=2, meter_capacity=100, meter_fill_rate=1)
_ACTIONS = (ActionDefinition(kind=ActionKind.STRUGGLE, name="Struggle"),)


def _driver(
    kind_queue: Sequence[EncounterKind] = (EncounterKind.NOTHING, EncounterKind.NOTHING),
    save_store: FakeSaveStore | None = None,
    combat_speed_multiplier: float = 1.0,
    audio: AudioManager | None = None,
) -> GameDriver:
    # Defaults to two queued NOTHING screens rather than an empty queue: ExplorationScene's
    # for_new_generation() (ADR 0012) fires advance() once immediately, whether at construction or
    # after a later Continue -- one entry covers GameDriver.__init__()'s own throwaway generation
    # (immediately overwritten by _driver_with() below), a second covers a genuine Continue later
    # in the same test, and tests that never reach either case just leave the rest unused.
    # save_store always defaults to a FakeSaveStore, never GameDriver's own real-filesystem
    # fallback -- omitting it here would read/write the developer's actual save directory.
    return GameDriver(
        build_placeholder_atlas(),
        ScriptedEncounterRandom(kind_queue),
        audio if audio is not None else build_fake_audio_manager(),
        save_store=save_store or FakeSaveStore(),
        combat_speed_multiplier=combat_speed_multiplier,
    )


def _generation(stats: Stats = _STATS, character: Character | None = None) -> Generation:
    return Generation(
        character=character or Character(current_hp=stats.max_hp, max_hp=stats.max_hp),
        stats=stats,
        actions=_ACTIONS,
        rng=ScriptedEncounterRandom([EncounterKind.ENEMY]),
        starting_screen=0,
        matured_turfs=(),
    )


def _driver_with(
    generation: Generation, save_store: FakeSaveStore | None = None, audio: AudioManager | None = None
) -> GameDriver:
    # Bypasses GameDriver's own Game.start_generation() the same way test_combat.py's
    # _game_owning() bypasses it -- so a test can pin exact combat stats -- and wires ownership by
    # hand the same way start_generation() would have.
    driver = _driver(save_store=save_store, audio=audio)
    driver._game._current_generation = generation
    driver._generation = generation
    driver._scene = ExplorationScene.for_new_generation(generation, driver._game, driver._atlas, driver._audio)
    return driver


def _advance(driver: GameDriver) -> None:
    # Drives a full screen-walk lap (ADR 0012): ExplorationScene.for_new_generation() already
    # joins at AT_ENTRY with the screen's encounter pending, so one ADVANCE press plus a walk to
    # the marker is enough to reveal it -- the EnterCombat/HUD-message outcome every caller here
    # is actually after. Dismisses whatever narration advance() already queued at construction
    # first (FIRST_EXPLORATION, plus FIRST_BATTLE/FIRST_PICKUP if this screen has one) -- otherwise
    # the ADVANCE press below would just dismiss narration instead of walking.
    scene = driver._scene
    assert isinstance(scene, ExplorationScene)
    while scene._narration.queue.is_active:
        scene._narration.queue.dismiss()
    driver.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    driver.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)


def _drive_battle_to_conclusion(driver: GameDriver, max_frames: int = 2000) -> None:
    # Generous budget: EffectApplied/EffectExpired/TurnSkipped/ExtraActionTriggered/BattleEnded
    # (ADR 0013's Announcement treatment) each hold for BATTLE_ANNOUNCEMENT_HOLD_SECONDS, so a real
    # strain inflicting several buffs/debuffs over a multi-round fight needs many more 0.016s
    # frames to fully resolve than the swing/tween-only phases alone required.
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


def test_construction_plays_exploration_ambient_music_for_a_brand_new_game() -> None:
    spy = build_spy_audio_manager()

    _driver(audio=spy.manager)

    assert spy.ambient.played == [(spy.sounds[SoundKey.EXPLORATION], -1, 0)]


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


def test_enter_combat_threads_the_combat_speed_multiplier_into_the_combat_scene() -> None:
    driver = _driver([EncounterKind.ENEMY], combat_speed_multiplier=2.0)

    _advance(driver)

    assert isinstance(driver._scene, CombatScene)
    assert driver._scene._combat_speed_multiplier == 2.0


def _open_settings(driver: GameDriver) -> SettingsScene:
    scene = driver._scene
    assert isinstance(scene, ExplorationScene)
    while scene._narration.queue.is_active:
        scene._narration.queue.dismiss()
    driver.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    settings = driver.update(0.016)
    assert isinstance(settings, SettingsScene)
    return settings


@pytest.fixture
def _isolated_settings_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # SettingsScene persists through the real save.settings_store(); keep it off the developer's
    # own settings file.
    monkeypatch.setattr(platformdirs, "user_data_dir", lambda _app_name: str(tmp_path))


@pytest.mark.usefixtures("_isolated_settings_dir")
def test_open_settings_leaves_the_driver_and_backs_out_to_the_same_inner_scene() -> None:
    driver = _driver()
    exploration = driver._scene

    settings = _open_settings(driver)
    settings.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))

    assert settings.update(0.016) is driver
    assert driver._scene is exploration


@pytest.mark.usefixtures("_isolated_settings_dir")
def test_combat_speed_changed_in_game_reaches_the_next_combat_scene() -> None:
    driver = _driver([EncounterKind.ENEMY], combat_speed_multiplier=1.0)

    settings = _open_settings(driver)
    settings.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))
    settings.update(0.016)
    settings.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert settings.update(0.016) is driver
    _advance(driver)

    assert isinstance(driver._scene, CombatScene)
    assert driver._scene._combat_speed_multiplier == 1.5


def test_enter_combat_threads_the_same_audio_manager_into_the_combat_scene() -> None:
    spy = build_spy_audio_manager()
    driver = _driver([EncounterKind.ENEMY], audio=spy.manager)

    _advance(driver)

    assert isinstance(driver._scene, CombatScene)
    assert driver._scene._audio is spy.manager


def test_win_returns_to_exploration_without_persisting() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    driver = _driver_with(_generation(stats=overwhelming))

    _advance(driver)
    assert isinstance(driver._scene, CombatScene)

    _drive_battle_to_conclusion(driver)

    assert isinstance(driver._scene, ExplorationScene)
    assert driver._save_store.load() is None  # a win alone produces no SeedsMatured/SporesAwarded


def test_loss_plays_menu_ambient_music_since_the_skill_tree_has_none_of_its_own() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=fragile, character=Character(current_hp=5, max_hp=5))
    spy = build_spy_audio_manager()
    driver = _driver_with(generation, audio=spy.manager)

    _advance(driver)
    _drive_battle_to_conclusion(driver)

    assert isinstance(driver._scene, SkillTreeScene)
    assert spy.ambient.played[-1] == (spy.sounds[SoundKey.MENU], -1, 0)


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


def test_a_fresh_generation_gets_its_own_narration_triggers_instance() -> None:
    driver = _driver()

    first = driver._narration
    driver.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))  # dismiss FIRST_EXPLORATION
    driver.update(0.016)
    driver._game._current_generation = None  # let a second start_generation() through, mirroring _driver_with
    driver._scene = driver._start_new_generation()

    assert driver._narration is not first


def test_a_persisted_trigger_does_not_re_fire_in_a_later_generation() -> None:
    driver = _driver()
    driver._narration.fire(NarrationTrigger.FIRST_DEATH, "msg", "sub")
    driver._persist()

    driver._game._current_generation = None  # let a second start_generation() through, mirroring _driver_with
    driver._scene = driver._start_new_generation()

    assert NarrationTrigger.FIRST_DEATH in driver._narration._seen


def test_a_new_generation_starts_with_every_recurring_announcement_unlatched() -> None:
    driver = _driver()
    driver._narration.announce_recurring(
        RecurringNarration.SEED_READY, armed=True, level=True, message="m", subtitle="s"
    )
    driver._persist()

    driver._game._current_generation = None  # let a second start_generation() through, mirroring _driver_with
    driver._scene = driver._start_new_generation()
    while driver._narration.queue.is_active:
        driver._narration.queue.dismiss()
    driver._narration.announce_recurring(
        RecurringNarration.SEED_READY, armed=True, level=True, message="m", subtitle="s"
    )

    assert driver._narration.queue.is_active is True


def test_a_persisted_trigger_survives_a_fresh_game_driver_instance() -> None:
    save_store = FakeSaveStore()
    narration_store = FakeSaveStore()
    first_driver = GameDriver(
        build_placeholder_atlas(),
        ScriptedEncounterRandom((EncounterKind.NOTHING,)),
        build_fake_audio_manager(),
        save_store=save_store,
        narration_store=narration_store,
    )
    first_driver._narration.fire(NarrationTrigger.FIRST_DEATH, "msg", "sub")
    first_driver._persist()

    second_driver = GameDriver(
        build_placeholder_atlas(),
        ScriptedEncounterRandom(()),
        build_fake_audio_manager(),
        save_store=save_store,
        narration_store=narration_store,
    )

    assert NarrationTrigger.FIRST_DEATH in second_driver._narration._seen


def test_the_same_narration_instance_threads_through_an_enter_combat_transition() -> None:
    driver = _driver([EncounterKind.ENEMY])
    before = driver._narration

    _advance(driver)

    assert isinstance(driver._scene, CombatScene)
    assert driver._scene._narration is before


def test_the_same_narration_instance_threads_back_into_exploration_after_combat() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    driver = _driver_with(_generation(stats=overwhelming))
    before = driver._narration

    _advance(driver)
    _drive_battle_to_conclusion(driver)

    assert isinstance(driver._scene, ExplorationScene)
    assert driver._scene._narration is before
