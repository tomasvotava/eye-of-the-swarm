from pathlib import Path

import platformdirs
import pygame
import pytest

from eye.gui.scene import Scene
from eye.gui.scenes.settings import KEY_ACTIONS, SettingsAction, SettingsScene
from eye.persistence import save
from eye.persistence.settings import SETTINGS_SCHEMA_VERSION, SettingsSnapshot, decode_settings, encode_settings


@pytest.fixture(autouse=True)
def _isolated_save_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Redirects save.settings_store()'s underlying path under tmp_path -- SettingsScene builds its
    # own store internally (ADR 0017), so tests can't inject a fake and must isolate the real
    # filesystem adapter instead, the same paths a developer's own settings would otherwise occupy.
    monkeypatch.setattr(platformdirs, "user_data_dir", lambda _app_name: str(tmp_path))


class _StubScene:
    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> Scene | None:
        return None

    def draw(self, surface: pygame.Surface) -> None:
        pass


def _press(scene: SettingsScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_key_actions_maps_the_expected_controls() -> None:
    assert KEY_ACTIONS[pygame.K_LEFT] is SettingsAction.DECREASE_SPEED
    assert KEY_ACTIONS[pygame.K_RIGHT] is SettingsAction.INCREASE_SPEED
    assert KEY_ACTIONS[pygame.K_ESCAPE] is SettingsAction.BACK


def test_defaults_to_1x_when_nothing_saved_yet() -> None:
    scene = SettingsScene(_StubScene())

    assert scene._settings.combat_speed_multiplier == 1.0
    assert scene._settings.schema_version == SETTINGS_SCHEMA_VERSION


def test_falls_back_to_default_when_saved_settings_are_corrupt() -> None:
    save.settings_store().save("not json")

    scene = SettingsScene(_StubScene())

    assert scene._settings.combat_speed_multiplier == 1.0


def test_loads_the_previously_saved_multiplier() -> None:
    save.settings_store().save(
        encode_settings(SettingsSnapshot(schema_version=SETTINGS_SCHEMA_VERSION, combat_speed_multiplier=2.0))
    )

    scene = SettingsScene(_StubScene())

    assert scene._settings.combat_speed_multiplier == 2.0


def test_loaded_multiplier_steps_from_its_own_preset_not_the_default() -> None:
    # Regression guard for _closest_preset_index: every other increase/decrease test starts from
    # the 1.0x default (index 2), so a snapping bug that only misplaces a *loaded* value would
    # still pass every one of them. Assert on the persisted result, not the private index.
    save.settings_store().save(
        encode_settings(SettingsSnapshot(schema_version=SETTINGS_SCHEMA_VERSION, combat_speed_multiplier=2.0))
    )
    scene = SettingsScene(_StubScene())

    _press(scene, pygame.K_RIGHT)
    scene.update(0.016)

    raw = save.settings_store().load()
    assert raw is not None
    assert decode_settings(raw).combat_speed_multiplier == 3.0  # the preset directly above 2.0


def test_update_with_no_pending_action_returns_none() -> None:
    scene = SettingsScene(_StubScene())

    assert scene.update(0.016) is None


def test_non_keydown_event_is_ignored() -> None:
    scene = SettingsScene(_StubScene())

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_RIGHT))

    assert scene.update(0.016) is None


def test_unmapped_key_is_ignored() -> None:
    scene = SettingsScene(_StubScene())

    _press(scene, pygame.K_z)

    assert scene.update(0.016) is None


def test_escape_returns_to_the_back_scene() -> None:
    back_scene = _StubScene()
    scene = SettingsScene(back_scene)

    _press(scene, pygame.K_ESCAPE)

    assert scene.update(0.016) is back_scene


def test_increase_speed_moves_to_the_next_preset_and_persists_immediately() -> None:
    scene = SettingsScene(_StubScene())
    starting = scene._settings.combat_speed_multiplier

    _press(scene, pygame.K_RIGHT)
    scene.update(0.016)

    assert scene._settings.combat_speed_multiplier > starting
    raw = save.settings_store().load()
    assert raw is not None
    assert decode_settings(raw).combat_speed_multiplier == scene._settings.combat_speed_multiplier


def test_decrease_speed_moves_to_the_previous_preset_and_persists_immediately() -> None:
    scene = SettingsScene(_StubScene())
    starting = scene._settings.combat_speed_multiplier

    _press(scene, pygame.K_LEFT)
    scene.update(0.016)

    assert scene._settings.combat_speed_multiplier < starting
    raw = save.settings_store().load()
    assert raw is not None
    assert decode_settings(raw).combat_speed_multiplier == scene._settings.combat_speed_multiplier


def test_decrease_speed_is_clamped_at_the_lowest_preset() -> None:
    scene = SettingsScene(_StubScene())

    for _ in range(20):
        _press(scene, pygame.K_LEFT)
        scene.update(0.016)
    lowest = scene._settings.combat_speed_multiplier

    _press(scene, pygame.K_LEFT)
    scene.update(0.016)

    assert scene._settings.combat_speed_multiplier == lowest


def test_increase_speed_is_clamped_at_the_highest_preset() -> None:
    scene = SettingsScene(_StubScene())

    for _ in range(20):
        _press(scene, pygame.K_RIGHT)
        scene.update(0.016)
    highest = scene._settings.combat_speed_multiplier

    _press(scene, pygame.K_RIGHT)
    scene.update(0.016)

    assert scene._settings.combat_speed_multiplier == highest


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    scene = SettingsScene(_StubScene())

    scene.draw(pygame.Surface(surface_size))


def test_on_change_receives_each_persisted_snapshot() -> None:
    received: list[SettingsSnapshot] = []
    scene = SettingsScene(_StubScene(), on_change=received.append)

    _press(scene, pygame.K_RIGHT)
    scene.update(0.016)

    assert [snapshot.combat_speed_multiplier for snapshot in received] == [1.5]
    assert received[-1] == decode_settings(save.settings_store().load() or "")


def test_on_change_is_not_called_when_a_step_is_clamped() -> None:
    received: list[SettingsSnapshot] = []
    scene = SettingsScene(_StubScene(), on_change=received.append)

    for _ in range(10):
        _press(scene, pygame.K_LEFT)
        scene.update(0.016)
    received.clear()
    _press(scene, pygame.K_LEFT)
    scene.update(0.016)

    assert received == []
