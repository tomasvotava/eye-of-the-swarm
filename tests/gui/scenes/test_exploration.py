import json
import math
from collections.abc import Callable, Sequence
from pathlib import Path

import pygame
import pytest

from eye.combat.effects import EffectName
from eye.combat.tuning import PROXIMITY_FALLOFF_RANGE
from eye.exploration.encounters import _RESOURCE_MAGNITUDES, Biome, EncounterKind, ResourceKind, Strain
from eye.exploration.events import EffectGranted, EnemyEncountered, NothingHappened, ResourceGranted
from eye.exploration.tuning import SEED_GROWTH_RATE_CAP, SEED_GROWTH_THRESHOLD
from eye.gui.app import _WINDOW_SIZE
from eye.gui.assets import (
    PLACEHOLDER_SPRITE_SIZE,
    SpriteAtlas,
    SpriteKey,
    build_art_atlas,
    build_placeholder_atlas,
)
from eye.gui.biome import resolve_biome
from eye.gui.card import Card, card_column_width
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.narration import NarrationEntry, NarrationTrigger, NarrationTriggers
from eye.gui.play_scene import EnterCombat, PlaySceneTransition
from eye.gui.scenes.exploration import (
    _BUFF_ICON_SIZE,
    _BUFF_ICON_STEP,
    _CARD_FOOTER,
    _FONT_SIZE,
    _HUD_MARGIN,
    _ICON_MARGIN,
    _PLAYER_SCALE_FACTOR,
    _SPORES_ICON_SIZE,
    _SPORES_LABEL_GAP,
    _TEXT_COLOR,
    KEY_ACTIONS,
    RESOURCE_DESCRIPTIONS,
    EncounterAnimationState,
    ExplorationAction,
    ExplorationScene,
    PlayerAnimationState,
    _build_encounter_animator,
    _encounter_scale_factor,
    _Phase,
    _resolve_encounter_sprite_key,
)
from eye.gui.tuning import (
    ENCOUNTER_ENEMY_SCALE_FACTOR,
    ENCOUNTER_PICKUP_SCALE_FACTOR,
    ENCOUNTER_X_FRACTION,
    ENTRY_X_FRACTION,
    EXPLORATION_GROUND_Y_FRACTION,
    WALK_TO_ENCOUNTER_DURATION_SECONDS,
    WALK_TO_EXIT_DURATION_SECONDS,
)
from eye.gui.widgets import EFFECT_DESCRIPTIONS, SpriteBuffIcon, SpriteIcon, borderless_icon, effect_label
from eye.session.events import SessionEvent
from eye.session.game import Game
from eye.session.generation import Generation
from tests.session.doubles import ScriptedEncounterRandom

_ADVANCES_TO_READY_SEED = int(SEED_GROWTH_THRESHOLD // SEED_GROWTH_RATE_CAP)


def _scene(
    kind_queue: Sequence[EncounterKind] = (), resource_queue: Sequence[ResourceKind] = ()
) -> tuple[ExplorationScene, Generation]:
    game = Game(ScriptedEncounterRandom(kind_queue, resource_queue=resource_queue))
    generation = game.start_generation()
    return ExplorationScene.for_new_generation(generation, game, build_placeholder_atlas()), generation


def _write_player_clips(assets_dir: Path, frame_count: int = 2, fps: float = 8) -> None:
    # Mirrors tests/gui/scenes/test_dev_assets.py's own helper -- too small a duplicate to
    # justify a shared test fixture module for.
    player_dir = assets_dir / SpriteKey.PLAYER.value
    player_dir.mkdir(parents=True, exist_ok=True)
    for name in ("idle", "walk"):
        sheet = pygame.Surface((4 * frame_count, 4))
        for index in range(frame_count):
            color = (index * 40 % 256, 0, 0, 255)
            sheet.fill(color, pygame.Rect(index * 4, 0, 4, 4))
        pygame.image.save(sheet, player_dir / f"{name}.png")
        manifest = {"frame_width": 4, "frame_height": 4, "frame_count": frame_count, "fps": fps}
        (player_dir / f"{name}.json").write_text(json.dumps(manifest))


def _scene_with_real_player_art(tmp_path: Path, kind_queue: Sequence[EncounterKind] = ()) -> ExplorationScene:
    _write_player_clips(tmp_path)
    game = Game(ScriptedEncounterRandom(kind_queue))
    generation = game.start_generation()
    return ExplorationScene.for_new_generation(generation, game, build_art_atlas(tmp_path))


def _write_static_sprite(tmp_path: Path, key: SpriteKey, size: int) -> None:
    sprite_dir = tmp_path / key.value
    sprite_dir.mkdir(parents=True, exist_ok=True)
    pygame.image.save(pygame.Surface((size, size)), sprite_dir / "sprite.png")


def _write_idle_clip(tmp_path: Path, key: SpriteKey, frame_count: int = 2, frame_size: int = 4, fps: float = 8) -> None:
    # Distinct fill colour per frame (mirrors _write_player_clips) so a frame-advance test can
    # tell them apart.
    key_dir = tmp_path / key.value
    key_dir.mkdir(parents=True, exist_ok=True)
    sheet = pygame.Surface((frame_size * frame_count, frame_size))
    for index in range(frame_count):
        color = (index * 40 % 256, 0, 0, 255)
        sheet.fill(color, pygame.Rect(index * frame_size, 0, frame_size, frame_size))
    pygame.image.save(sheet, key_dir / "idle.png")
    manifest = {"frame_width": frame_size, "frame_height": frame_size, "frame_count": frame_count, "fps": fps}
    (key_dir / "idle.json").write_text(json.dumps(manifest))


def _press(scene: ExplorationScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def _resolve_next_screen(scene: ExplorationScene) -> PlaySceneTransition | None:
    """Drives `scene` from wherever it currently sits (`RESOLVED` or `AT_ENTRY`, both reachable
    between screens) through to the next `RESOLVED`/`EnterCombat` reveal -- one full screen's
    worth of walking. `for_new_generation()` already fires `advance()` for the first screen and
    joins at `AT_ENTRY`, so only the second half-lap is needed there; every screen after starts
    the full `RESOLVED -> WALKING_TO_EXIT -> AT_ENTRY -> WALKING_TO_ENCOUNTER` cycle.

    Dismisses any narration active ahead of each press below (e.g. FIRST_EXPLORATION queued at
    construction, or FIRST_SEED_READY/FIRST_PROXIMITY_FALLOFF raised by the first half-lap's own
    update() call) -- otherwise that press would just dismiss it instead of walking."""

    def _dismiss_any_narration() -> None:
        while scene._narration.queue.is_active:
            scene._narration.queue.dismiss()

    if scene._phase is _Phase.RESOLVED:
        _dismiss_any_narration()
        _press(scene, pygame.K_SPACE)
        assert scene.update(WALK_TO_EXIT_DURATION_SECONDS) is None
    _dismiss_any_narration()
    _press(scene, pygame.K_SPACE)
    return scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)


def test_key_actions_maps_the_expected_controls() -> None:
    assert KEY_ACTIONS[pygame.K_SPACE] is ExplorationAction.ADVANCE
    assert KEY_ACTIONS[pygame.K_RETURN] is ExplorationAction.ADVANCE
    assert KEY_ACTIONS[pygame.K_p] is ExplorationAction.PLANT_SEED


def test_for_new_generation_calls_advance_once_and_starts_at_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING]))
    generation = game.start_generation()
    calls: list[None] = []
    original_advance = generation.advance

    def counting_advance() -> list[SessionEvent]:
        calls.append(None)
        return original_advance()

    monkeypatch.setattr(generation, "advance", counting_advance)

    scene = ExplorationScene.for_new_generation(generation, game, build_placeholder_atlas())

    assert len(calls) == 1
    assert scene._phase is _Phase.AT_ENTRY


def test_resuming_after_combat_does_not_advance_and_starts_resolved(monkeypatch: pytest.MonkeyPatch) -> None:
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING]))
    generation = game.start_generation()
    calls: list[None] = []
    monkeypatch.setattr(generation, "advance", lambda: calls.append(None))

    scene = ExplorationScene.resuming_after_combat(generation, game, build_placeholder_atlas())

    assert calls == []
    assert scene._phase is _Phase.RESOLVED


def test_advance_fires_exactly_once_per_screen_at_the_right_moments(monkeypatch: pytest.MonkeyPatch) -> None:
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING, EncounterKind.NOTHING]))
    generation = game.start_generation()
    calls: list[None] = []
    original_advance = generation.advance

    def counting_advance() -> list[SessionEvent]:
        calls.append(None)
        return original_advance()

    monkeypatch.setattr(generation, "advance", counting_advance)

    scene = ExplorationScene.for_new_generation(generation, game, build_placeholder_atlas())
    assert len(calls) == 1  # fired once at construction, for the first screen
    _drain_narration(scene)  # INTRO_LORE + FIRST_EXPLORATION, queued at construction

    _press(scene, pygame.K_SPACE)
    assert scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS) is None  # reveal only, no new advance()
    assert len(calls) == 1

    _press(scene, pygame.K_SPACE)
    assert scene.update(WALK_TO_EXIT_DURATION_SECONDS) is None  # arrival at AT_ENTRY: second advance() fires
    assert len(calls) == 2

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)  # reveal of the second screen, no new call
    assert len(calls) == 2


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
    scene, _ = _scene([EncounterKind.NOTHING])

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE))

    assert scene.update(0.016) is None


def test_advance_action_grows_the_seed_and_returns_none_when_nothing_happens() -> None:
    scene, generation = _scene([EncounterKind.NOTHING] * _ADVANCES_TO_READY_SEED)

    # for_new_generation() already consumed the first NOTHING screen at construction.
    for _ in range(_ADVANCES_TO_READY_SEED):
        assert _resolve_next_screen(scene) is None

    assert generation.is_seed_ready is True


def test_plant_seed_action_is_a_no_op_before_the_seed_is_ready() -> None:
    scene, generation = _scene([EncounterKind.NOTHING] * 2)
    _resolve_next_screen(scene)  # now RESOLVED, well short of _ADVANCES_TO_READY_SEED
    assert generation.is_seed_ready is False

    _press(scene, pygame.K_p)
    scene.update(0.016)

    assert generation.pending_seeds == ()
    assert generation.is_seed_ready is False


def test_plant_seed_action_plants_once_the_seed_is_ready() -> None:
    scene, generation = _scene([EncounterKind.NOTHING] * _ADVANCES_TO_READY_SEED)
    for _ in range(_ADVANCES_TO_READY_SEED):
        _resolve_next_screen(scene)
    assert generation.is_seed_ready is True
    assert scene._phase is _Phase.RESOLVED

    # The very first press's own update() is what raises FIRST_SEED_READY (the trigger check runs
    # before is_seed_ready flips visible to it, one frame behind) -- that press is withheld from
    # planting alongside it.
    _press(scene, pygame.K_p)
    scene.update(0.016)
    assert generation.is_seed_ready is True
    assert scene._narration.queue.is_active is True

    # The second press both dismisses that narration and plants, in the same press.
    _press(scene, pygame.K_p)
    scene.update(0.016)

    assert generation.is_seed_ready is False
    assert generation.pending_seeds != ()


def test_plant_seed_action_is_withheld_while_a_card_is_up_even_once_narration_is_dismissed() -> None:
    # The screen whose own advance() makes the seed ready is also the one revealing a pickup, so
    # FIRST_SEED_READY can raise (at rest -- see test_seed_ready_does_not_fire_mid_walk_...) on a
    # frame where that pickup's card is already showing.
    scene, generation = _scene([EncounterKind.NOTHING] * (_ADVANCES_TO_READY_SEED - 1) + [EncounterKind.EFFECT_PICKUP])
    for _ in range(_ADVANCES_TO_READY_SEED):
        _resolve_next_screen(scene)
    assert generation.is_seed_ready is True
    assert scene._card is not None
    scene._narration.queue.dismiss()  # FIRST_PICKUP, raised alongside the card

    scene.update(0.016)  # a frame at rest: raises FIRST_SEED_READY, card still up
    assert scene._narration.queue.is_active is True
    assert scene._card is not None

    _press(scene, pygame.K_p)
    scene.update(0.016)

    assert scene._card is not None
    assert generation.is_seed_ready is True
    assert generation.pending_seeds == ()


def test_plant_seed_action_is_a_no_op_mid_walk() -> None:
    scene, generation = _scene([EncounterKind.NOTHING] * _ADVANCES_TO_READY_SEED)
    for _ in range(_ADVANCES_TO_READY_SEED):
        _resolve_next_screen(scene)
    assert generation.is_seed_ready is True

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS / 2)  # now WALKING_TO_EXIT, mid-walk
    assert scene._phase is _Phase.WALKING_TO_EXIT

    _press(scene, pygame.K_p)
    scene.update(0.001)

    assert generation.pending_seeds == ()
    assert generation.is_seed_ready is True


def test_plant_seed_action_is_a_no_op_at_entry_even_when_the_seed_is_ready() -> None:
    # Queue enough NOTHING screens for the seed to become ready, then stop the walk right at
    # AT_ENTRY (before the current screen's own encounter is revealed) -- plant must still be a
    # no-op there, per ADR 0012's stricter-than-"sometime after arriving" plant window.
    scene, generation = _scene([EncounterKind.NOTHING] * (_ADVANCES_TO_READY_SEED + 1))
    for _ in range(_ADVANCES_TO_READY_SEED):
        _resolve_next_screen(scene)
    assert generation.is_seed_ready is True

    _press(scene, pygame.K_SPACE)
    assert scene.update(WALK_TO_EXIT_DURATION_SECONDS) is None  # arrives at AT_ENTRY
    assert scene._phase is _Phase.AT_ENTRY

    _press(scene, pygame.K_p)
    scene.update(0.016)

    assert generation.pending_seeds == ()
    assert generation.is_seed_ready is True


def test_can_plant_seed_reflects_phase_not_just_seed_readiness() -> None:
    # _can_plant_seed() backs both the actual plant gate and the GUI's "seed ready" icon/HUD
    # label -- it must go False the moment the phase leaves RESOLVED, even though the domain's
    # is_seed_ready stays True until an actual plant_seed() call consumes it.
    scene, generation = _scene([EncounterKind.NOTHING] * (_ADVANCES_TO_READY_SEED + 1))
    for _ in range(_ADVANCES_TO_READY_SEED):
        _resolve_next_screen(scene)
    assert generation.is_seed_ready is True
    assert scene._can_plant_seed() is True  # RESOLVED, per _resolve_next_screen()'s contract

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS)  # now AT_ENTRY
    assert generation.is_seed_ready is True
    assert scene._can_plant_seed() is False


def test_advance_action_returns_an_enter_combat_transition_on_encounter() -> None:
    scene, _ = _scene([EncounterKind.ENEMY])
    _drain_narration(scene)  # FIRST_EXPLORATION + FIRST_BATTLE, both fired by advance() at construction

    _press(scene, pygame.K_SPACE)
    transition = scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)

    assert isinstance(transition, EnterCombat)
    assert isinstance(transition.encounter, EnemyEncountered)


def test_enter_combat_is_withheld_until_the_walk_to_the_encounter_completes() -> None:
    scene, _ = _scene([EncounterKind.ENEMY])
    _drain_narration(scene)  # FIRST_EXPLORATION + FIRST_BATTLE, both fired by advance() at construction

    _press(scene, pygame.K_SPACE)
    assert scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2) is None  # still walking

    assert isinstance(scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2), EnterCombat)  # now arrives


def test_resolve_encounter_sprite_key_for_each_screen_event_kind() -> None:
    assert (
        _resolve_encounter_sprite_key([EnemyEncountered(strain=Strain.BRAMBLE, biome=Biome.BRAMBEROSITY)])
        is SpriteKey.BRAMBLE
    )
    assert _resolve_encounter_sprite_key([EffectGranted(effect=EffectName.FIBROUS)]) is SpriteKey.EFFECT_PICKUP
    assert (
        _resolve_encounter_sprite_key([ResourceGranted(kind=ResourceKind.HEAL, amount=10)]) is SpriteKey.RESOURCE_PICKUP
    )
    assert _resolve_encounter_sprite_key([NothingHappened()]) is None
    assert _resolve_encounter_sprite_key([]) is None


def test_encounter_scale_factor_is_the_pickup_factor_for_either_pickup_marker() -> None:
    assert _encounter_scale_factor(SpriteKey.EFFECT_PICKUP) == ENCOUNTER_PICKUP_SCALE_FACTOR
    assert _encounter_scale_factor(SpriteKey.RESOURCE_PICKUP) == ENCOUNTER_PICKUP_SCALE_FACTOR


def test_encounter_scale_factor_is_the_enemy_factor_for_a_strain_or_unknown() -> None:
    assert _encounter_scale_factor(SpriteKey.GOLEM) == ENCOUNTER_ENEMY_SCALE_FACTOR
    assert _encounter_scale_factor(SpriteKey.UNKNOWN) == ENCOUNTER_ENEMY_SCALE_FACTOR


def test_encounter_static_sprite_is_none_when_the_screen_is_empty() -> None:
    scene, _ = _scene([EncounterKind.NOTHING])

    assert scene._encounter_animator is None
    assert scene._encounter_static_sprite is None


def test_encounter_static_sprite_is_scaled_by_the_pickup_factor(tmp_path: Path) -> None:
    # 20 * ENCOUNTER_PICKUP_SCALE_FACTOR (0.45) is an exact 9 -- avoids relying on how
    # pygame.transform.scale_by rounds a fractional pixel count.
    _write_static_sprite(tmp_path, SpriteKey.EFFECT_PICKUP, size=20)
    game = Game(ScriptedEncounterRandom([EncounterKind.EFFECT_PICKUP]))
    generation = game.start_generation()

    scene = ExplorationScene.for_new_generation(generation, game, build_art_atlas(tmp_path))

    assert scene._encounter_animator is None  # pickup markers never carry animation data
    assert scene._encounter_static_sprite is not None
    expected = round(20 * ENCOUNTER_PICKUP_SCALE_FACTOR)
    assert scene._encounter_static_sprite.get_size() == (expected, expected)


def test_encounter_static_sprite_is_scaled_by_the_enemy_factor(tmp_path: Path) -> None:
    _write_static_sprite(tmp_path, SpriteKey.GOLEM, size=4)
    game = Game(ScriptedEncounterRandom([EncounterKind.ENEMY], strain_queue=[Strain.GOLEM]))
    generation = game.start_generation()

    scene = ExplorationScene.for_new_generation(generation, game, build_art_atlas(tmp_path))

    assert scene._encounter_animator is None  # no idle.json written -- static art only
    assert scene._encounter_static_sprite is not None
    expected = round(4 * ENCOUNTER_ENEMY_SCALE_FACTOR)
    assert scene._encounter_static_sprite.get_size() == (expected, expected)


def test_encounter_static_sprite_is_rebuilt_on_arrival_at_the_next_screen(tmp_path: Path) -> None:
    _write_static_sprite(tmp_path, SpriteKey.EFFECT_PICKUP, size=20)
    _write_static_sprite(tmp_path, SpriteKey.RESOURCE_PICKUP, size=40)
    game = Game(ScriptedEncounterRandom([EncounterKind.EFFECT_PICKUP, EncounterKind.RESOURCE_PICKUP]))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, build_art_atlas(tmp_path))
    first_size = round(20 * ENCOUNTER_PICKUP_SCALE_FACTOR)
    assert scene._encounter_static_sprite is not None
    assert scene._encounter_static_sprite.get_size() == (first_size, first_size)

    _resolve_next_screen(scene)  # reveals screen 1 (RESOLVED); encounter sprite is still screen 1's
    _resolve_next_screen(scene)  # walks off screen 1, advance() fires for screen 2, reveals it too

    second_size = round(40 * ENCOUNTER_PICKUP_SCALE_FACTOR)
    assert scene._encounter_static_sprite is not None
    assert scene._encounter_static_sprite.get_size() == (second_size, second_size)


def test_draw_blits_the_scaled_encounter_sprite_centered_on_the_marker(tmp_path: Path) -> None:
    _write_static_sprite(tmp_path, SpriteKey.EFFECT_PICKUP, size=20)
    game = Game(ScriptedEncounterRandom([EncounterKind.EFFECT_PICKUP]))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, build_art_atlas(tmp_path))
    assert scene._encounter_static_sprite is not None

    # Large enough that the player's own placeholder sprite, drawn near the left edge, can't
    # reach as far as the marker sampled below.
    surface = pygame.Surface(_WINDOW_SIZE)
    scene.draw(surface)

    x = round(surface.get_width() * ENCOUNTER_X_FRACTION)
    y = round(surface.get_height() * EXPLORATION_GROUND_Y_FRACTION)
    sampled = surface.get_at((x, y))
    assert sampled == scene._encounter_static_sprite.get_at(
        (scene._encounter_static_sprite.get_width() // 2, scene._encounter_static_sprite.get_height() // 2)
    )


def test_build_encounter_animator_returns_none_without_animation_data() -> None:
    atlas = build_placeholder_atlas()

    assert _build_encounter_animator(atlas, SpriteKey.GOLEM, scale_factor=3.0) is None


def test_build_encounter_animator_scales_every_frame_by_scale_factor(tmp_path: Path) -> None:
    _write_idle_clip(tmp_path, SpriteKey.GOLEM)  # 4x4 test clip frames
    atlas = build_art_atlas(tmp_path)

    animator = _build_encounter_animator(atlas, SpriteKey.GOLEM, scale_factor=3.0)

    assert animator is not None
    assert animator.current_frame().get_size() == (12, 12)


def test_encounter_animator_is_built_for_a_strain_with_animation_data(tmp_path: Path) -> None:
    _write_idle_clip(tmp_path, SpriteKey.GOLEM)  # 4x4 test clip frames
    game = Game(ScriptedEncounterRandom([EncounterKind.ENEMY], strain_queue=[Strain.GOLEM]))
    generation = game.start_generation()

    scene = ExplorationScene.for_new_generation(generation, game, build_art_atlas(tmp_path))

    assert scene._encounter_animator is not None
    frame_size = round(4 * ENCOUNTER_ENEMY_SCALE_FACTOR)
    assert scene._encounter_animator.current_frame().get_size() == (frame_size, frame_size)
    assert scene._encounter_animator.state is EncounterAnimationState.IDLE


def test_encounter_animator_is_rebuilt_to_none_when_the_next_screen_has_no_animation_data(tmp_path: Path) -> None:
    _write_idle_clip(tmp_path, SpriteKey.GOLEM)
    game = Game(ScriptedEncounterRandom([EncounterKind.ENEMY, EncounterKind.NOTHING], strain_queue=[Strain.GOLEM]))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, build_art_atlas(tmp_path))
    assert scene._encounter_animator is not None

    _resolve_next_screen(scene)  # reveals screen 1 (RESOLVED); animator is still screen 1's Strain
    _resolve_next_screen(scene)  # walks off screen 1, advance() fires for the empty screen 2

    assert scene._encounter_animator is None
    assert scene._encounter_static_sprite is None


def test_updating_advances_the_encounter_animation_frame(tmp_path: Path) -> None:
    _write_idle_clip(tmp_path, SpriteKey.GOLEM)  # 2 frames at 8fps
    game = Game(ScriptedEncounterRandom([EncounterKind.ENEMY], strain_queue=[Strain.GOLEM]))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, build_art_atlas(tmp_path))
    assert scene._encounter_animator is not None
    first_frame = scene._encounter_animator.current_frame()

    scene.update(1 / 8)  # exactly one frame at the default 8fps test clip

    second_frame = scene._encounter_animator.current_frame()
    assert pygame.image.tobytes(first_frame, "RGBA") != pygame.image.tobytes(second_frame, "RGBA")


def test_draw_blits_the_encounter_animator_frame_when_available(tmp_path: Path) -> None:
    _write_idle_clip(tmp_path, SpriteKey.GOLEM)
    game = Game(ScriptedEncounterRandom([EncounterKind.ENEMY], strain_queue=[Strain.GOLEM]))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, build_art_atlas(tmp_path))
    assert scene._encounter_animator is not None

    surface = pygame.Surface(_WINDOW_SIZE)
    scene.draw(surface)

    expected = scene._encounter_animator.current_frame()
    x = round(surface.get_width() * ENCOUNTER_X_FRACTION)
    y = round(surface.get_height() * EXPLORATION_GROUND_Y_FRACTION)
    sampled = surface.get_at((x, y))
    assert sampled == expected.get_at((expected.get_width() // 2, expected.get_height() // 2))


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise_across_every_phase(surface_size: tuple[int, int]) -> None:
    scene, _ = _scene([EncounterKind.NOTHING, EncounterKind.NOTHING])
    surface = pygame.Surface(surface_size)

    scene.draw(surface)  # AT_ENTRY

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)
    scene.draw(surface)  # WALKING_TO_ENCOUNTER, mid-walk

    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)
    scene.draw(surface)  # RESOLVED

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS / 2)
    scene.draw(surface)  # WALKING_TO_EXIT, mid-walk


def test_without_animation_data_the_player_animator_is_none() -> None:
    scene, _ = _scene([EncounterKind.NOTHING])

    assert scene._player_animator is None


def test_with_animation_data_the_player_animator_is_built(tmp_path: Path) -> None:
    scene = _scene_with_real_player_art(tmp_path, [EncounterKind.NOTHING])

    assert scene._player_animator is not None


def test_player_animator_frames_are_scaled_by_player_scale_factor(tmp_path: Path) -> None:
    scene = _scene_with_real_player_art(tmp_path, [EncounterKind.NOTHING])  # 4x4 test clip frames
    assert scene._player_animator is not None

    frame_size = round(4 * _PLAYER_SCALE_FACTOR)
    assert scene._player_animator.current_frame().get_size() == (frame_size, frame_size)


def test_player_static_sprite_fallback_is_scaled_by_player_scale_factor() -> None:
    scene, _ = _scene([EncounterKind.NOTHING])  # placeholder atlas has no player animation data
    assert scene._player_animator is None

    sprite_size = round(PLACEHOLDER_SPRITE_SIZE * _PLAYER_SCALE_FACTOR)
    assert scene._player_static_sprite.get_size() == (sprite_size, sprite_size)


def test_player_animation_state_is_idle_at_entry_and_walk_during_the_walk_to_the_encounter(
    tmp_path: Path,
) -> None:
    scene = _scene_with_real_player_art(tmp_path, [EncounterKind.NOTHING])
    _drain_narration(scene)  # INTRO_LORE + FIRST_EXPLORATION, queued at construction
    phase_at_entry = scene._phase
    assert phase_at_entry is _Phase.AT_ENTRY
    animator = scene._player_animator
    assert animator is not None
    state_at_entry = animator._state
    assert state_at_entry is PlayerAnimationState.IDLE

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)  # mid-walk to the marker
    phase_mid_walk = scene._phase
    assert phase_mid_walk is _Phase.WALKING_TO_ENCOUNTER
    state_mid_walk = animator._state
    assert state_mid_walk is PlayerAnimationState.WALK

    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)  # arrives, RESOLVED
    phase_resolved = scene._phase
    assert phase_resolved is _Phase.RESOLVED
    state_resolved = animator._state
    assert state_resolved is PlayerAnimationState.IDLE


def test_player_animation_state_is_walk_during_the_walk_to_the_exit(tmp_path: Path) -> None:
    scene = _scene_with_real_player_art(tmp_path, [EncounterKind.NOTHING, EncounterKind.NOTHING])
    _resolve_next_screen(scene)
    phase_resolved = scene._phase
    assert phase_resolved is _Phase.RESOLVED
    assert scene._player_animator is not None

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS / 2)  # mid-walk to the exit
    phase_mid_walk = scene._phase
    assert phase_mid_walk is _Phase.WALKING_TO_EXIT
    assert scene._player_animator._state is PlayerAnimationState.WALK


def test_resuming_after_combat_starts_the_player_animator_idle(tmp_path: Path) -> None:
    _write_player_clips(tmp_path)
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING]))
    generation = game.start_generation()

    scene = ExplorationScene.resuming_after_combat(generation, game, build_art_atlas(tmp_path))

    assert scene._phase is _Phase.RESOLVED
    assert scene._player_animator is not None
    assert scene._player_animator._state is PlayerAnimationState.IDLE


def test_updating_advances_the_player_animation_frame_during_a_walk(tmp_path: Path) -> None:
    scene = _scene_with_real_player_art(tmp_path, [EncounterKind.NOTHING])
    assert scene._player_animator is not None

    _press(scene, pygame.K_SPACE)
    scene.update(0.0)  # enters WALKING_TO_ENCOUNTER without consuming any walk time yet
    first_frame = scene._player_animator.current_frame()

    scene.update(1 / 8)  # exactly one frame at the default 8fps test clip
    second_frame = scene._player_animator.current_frame()

    assert pygame.image.tobytes(first_frame, "RGBA") != pygame.image.tobytes(second_frame, "RGBA")


def test_draw_with_animation_data_blits_the_animator_frame(tmp_path: Path) -> None:
    scene = _scene_with_real_player_art(tmp_path, [EncounterKind.NOTHING])
    assert scene._player_animator is not None  # AT_ENTRY, drawn at ENTRY_X_FRACTION

    surface = pygame.Surface((64, 64))
    scene.draw(surface)

    expected = scene._player_animator.current_frame()
    x = round(surface.get_width() * ENTRY_X_FRACTION)
    y = round(surface.get_height() * EXPLORATION_GROUND_Y_FRACTION)
    sampled = surface.get_at((x, y))
    assert sampled == expected.get_at((expected.get_width() // 2, expected.get_height() // 2))


class _SpyBuffIcon:
    def __init__(self, effect: EffectName, calls: list[tuple[EffectName, pygame.Vector2, int]]) -> None:
        self.effect = effect
        self._calls = calls

    def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
        self._calls.append((self.effect, pos, size))


def _row_icon_calls(
    scene: ExplorationScene, calls: list[tuple[EffectName, pygame.Vector2, int]]
) -> list[tuple[EffectName, pygame.Vector2, int]]:
    """The subset of `calls` the buff row made: a raised card renders its icon through the same
    factory, and the card's larger icon box is what separates the two."""
    row = [call for call in calls if call[2] == _BUFF_ICON_SIZE]
    card_icons = 0 if scene._card is None else int(isinstance(scene._card.icon, _SpyBuffIcon))
    assert len(calls) == len(row) + card_icons
    return row


def _scene_with_spy_icons(
    kind_queue: Sequence[EncounterKind] = (),
) -> tuple[ExplorationScene, Generation, list[tuple[EffectName, pygame.Vector2, int]]]:
    calls: list[tuple[EffectName, pygame.Vector2, int]] = []
    game = Game(ScriptedEncounterRandom(kind_queue))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(
        generation, game, build_placeholder_atlas(), buff_icon_factory=lambda effect: _SpyBuffIcon(effect, calls)
    )
    return scene, generation, calls


def test_draw_renders_one_buff_icon_per_active_lifespan_effect() -> None:
    scene, generation, calls = _scene_with_spy_icons([EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)
    active = generation.active_lifespan_effects
    assert active  # the pickup granted something to draw

    scene.draw(pygame.Surface((800, 600)))

    assert [effect for effect, _, _ in _row_icon_calls(scene, calls)] == list(active)


def test_draw_renders_no_buff_icons_when_nothing_is_active() -> None:
    scene, generation, calls = _scene_with_spy_icons([EncounterKind.NOTHING])
    _resolve_next_screen(scene)
    assert generation.active_lifespan_effects == ()

    scene.draw(pygame.Surface((800, 600)))

    assert calls == []


def test_buff_icon_row_runs_along_the_top_edge_anchored_to_the_right() -> None:
    scene, generation, calls = _scene_with_spy_icons([EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)
    surface = pygame.Surface((800, 600))

    scene.draw(surface)

    count = len(generation.active_lifespan_effects)
    first_x = surface.get_width() - _ICON_MARGIN - _BUFF_ICON_STEP * (count - 1) - _BUFF_ICON_SIZE
    expected = [
        (pygame.Vector2(first_x + index * _BUFF_ICON_STEP, _ICON_MARGIN), _BUFF_ICON_SIZE) for index in range(count)
    ]
    assert [(pos, size) for _, pos, size in _row_icon_calls(scene, calls)] == expected


def test_exploration_scene_defaults_to_sprite_buff_icons_reused_across_frames() -> None:
    scene, _ = _scene([EncounterKind.NOTHING])

    icon = scene._buff_icon_factory(EffectName.FIBROUS)

    assert isinstance(icon, SpriteBuffIcon)
    assert scene._buff_icon_factory(EffectName.FIBROUS) is icon


def test_resuming_after_combat_uses_the_given_buff_icon_factory() -> None:
    calls: list[tuple[EffectName, pygame.Vector2, int]] = []
    game = Game(ScriptedEncounterRandom([EncounterKind.EFFECT_PICKUP]))
    generation = game.start_generation()
    generation.advance()  # the pickup this scene is resuming next to

    scene = ExplorationScene.resuming_after_combat(
        generation, game, build_placeholder_atlas(), buff_icon_factory=lambda effect: _SpyBuffIcon(effect, calls)
    )
    scene.draw(pygame.Surface((800, 600)))

    assert [effect for effect, _, _ in calls] == list(generation.active_lifespan_effects)


def test_draw_with_active_effects_and_the_default_icons_does_not_raise() -> None:
    game = Game(ScriptedEncounterRandom([EncounterKind.EFFECT_PICKUP]))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, build_placeholder_atlas())
    _resolve_next_screen(scene)
    assert generation.active_lifespan_effects

    scene.draw(pygame.Surface((800, 600)))


def test_buff_icon_row_withholds_a_newly_granted_effect_until_the_walk_resolves() -> None:
    scene, generation, calls = _scene_with_spy_icons([EncounterKind.EFFECT_PICKUP])
    _drain_narration(scene)  # FIRST_EXPLORATION + FIRST_PICKUP, both fired by advance() at construction
    # advance() already granted the effect while the player is still walking to it (ADR 0012).
    granted = generation.active_lifespan_effects
    assert granted
    surface = pygame.Surface((800, 600))

    scene.draw(surface)  # AT_ENTRY, the pickup not reached yet
    assert calls == []

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)
    scene.draw(surface)  # mid-walk
    assert calls == []

    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)  # arrives at the marker, RESOLVED
    scene.draw(surface)

    assert [effect for effect, _, _ in _row_icon_calls(scene, calls)] == list(granted)


def test_buff_icon_row_withholds_an_effect_granted_by_a_later_screens_advance() -> None:
    # The steady-state path: screens after the first load at a WALKING_TO_EXIT arrival.
    scene, generation, calls = _scene_with_spy_icons([EncounterKind.NOTHING, EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)  # screen 1, empty
    assert generation.active_lifespan_effects == ()
    surface = pygame.Surface((800, 600))

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS)  # screen 2 loads: advance() applies the pickup
    granted = generation.active_lifespan_effects
    assert granted
    _drain_narration(scene)  # FIRST_PICKUP, fired by this screen's own advance()
    scene.draw(surface)  # AT_ENTRY, the pickup not reached yet
    assert calls == []

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)
    scene.draw(surface)  # mid-walk
    assert calls == []

    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)  # arrives at the marker, RESOLVED
    scene.draw(surface)

    assert [effect for effect, _, _ in _row_icon_calls(scene, calls)] == list(granted)


def _granted_effect(generation: Generation) -> EffectName:
    # Which effect the pickup rolls is the domain's business, so read it back.
    active = generation.active_lifespan_effects
    assert len(active) == 1
    return active[0]


def test_effect_pickup_raises_the_card_only_once_the_walk_reaches_the_marker() -> None:
    scene, generation, _ = _scene_with_spy_icons([EncounterKind.EFFECT_PICKUP])
    _drain_narration(scene)  # FIRST_EXPLORATION + FIRST_PICKUP, both fired by advance() at construction
    # The reveal point: advance() applied the pickup back when the screen loaded (ADR 0012).
    granted = _granted_effect(generation)

    assert scene._card is None  # AT_ENTRY, the pickup not reached yet

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)
    assert scene._card is None  # mid-walk

    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)  # arrives at the marker, RESOLVED

    card = scene._card
    assert card is not None
    assert card.title == effect_label(granted)
    assert card.description == EFFECT_DESCRIPTIONS[granted]
    assert card.subtitle == "This generation"
    assert isinstance(card.icon, _SpyBuffIcon)
    assert card.icon.effect is granted


def test_effect_pickup_on_a_later_screen_raises_the_card_at_its_own_marker() -> None:
    # The steady-state path: later screens load at a WALKING_TO_EXIT arrival, not at construction.
    scene, generation, _ = _scene_with_spy_icons([EncounterKind.NOTHING, EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)  # screen 1, empty
    assert scene._card is None

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS)  # screen 2 loads: advance() applies the pickup
    granted = _granted_effect(generation)
    _drain_narration(scene)  # FIRST_PICKUP, fired by this screen's own advance()
    assert scene._card is None  # AT_ENTRY, the pickup not reached yet

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)

    card = scene._card
    assert card is not None
    assert card.title == effect_label(granted)


def test_an_empty_screen_raises_no_card() -> None:
    scene, _ = _scene([EncounterKind.NOTHING])

    _resolve_next_screen(scene)

    assert scene._card is None


def test_an_enemy_encounter_raises_no_card() -> None:
    scene, _ = _scene([EncounterKind.ENEMY])

    assert isinstance(_resolve_next_screen(scene), EnterCombat)
    assert scene._card is None


def test_the_effect_card_stands_however_long_the_player_leaves_it() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)
    assert scene._card is not None

    for _ in range(100):
        assert scene.update(1.0) is None

    assert scene._card is not None


def test_advancing_with_the_card_up_dismisses_it_without_starting_the_walk() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP, EncounterKind.NOTHING])
    _resolve_next_screen(scene)
    assert scene._card is not None
    scene._narration.queue.dismiss()  # FIRST_PICKUP, raised alongside the card

    _press(scene, pygame.K_SPACE)
    assert scene.update(WALK_TO_EXIT_DURATION_SECONDS) is None

    assert scene._card is None
    assert scene._phase is _Phase.RESOLVED


def test_the_frame_that_dismisses_the_card_still_advances_the_player_animation(tmp_path: Path) -> None:
    # The dismiss branch sits below the animator tick, not above it, so this frame still
    # advances the clip.
    scene = _scene_with_real_player_art(tmp_path, [EncounterKind.EFFECT_PICKUP, EncounterKind.NOTHING])
    _resolve_next_screen(scene)
    assert scene._card is not None
    scene._narration.queue.dismiss()  # FIRST_PICKUP, raised alongside the card
    assert scene._player_animator is not None
    before = scene._player_animator.current_frame()

    _press(scene, pygame.K_SPACE)
    scene.update(1 / 8)  # exactly one frame at the default 8fps test clip

    assert scene._card is None
    after = scene._player_animator.current_frame()
    assert pygame.image.tobytes(before, "RGBA") != pygame.image.tobytes(after, "RGBA")


def test_a_key_bound_to_no_action_dismisses_the_card_too() -> None:
    assert pygame.K_q not in KEY_ACTIONS
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP, EncounterKind.NOTHING])
    _resolve_next_screen(scene)
    assert scene._card is not None
    scene._narration.queue.dismiss()  # FIRST_PICKUP, raised alongside the card

    _press(scene, pygame.K_q)
    assert scene.update(WALK_TO_EXIT_DURATION_SECONDS) is None

    assert scene._card is None
    assert scene._phase is _Phase.RESOLVED


def test_the_plant_key_dismisses_the_card_without_planting() -> None:
    scene, generation = _scene([EncounterKind.NOTHING] * (_ADVANCES_TO_READY_SEED - 1) + [EncounterKind.EFFECT_PICKUP])
    for _ in range(_ADVANCES_TO_READY_SEED):
        _resolve_next_screen(scene)
    assert generation.is_seed_ready is True
    assert scene._card is not None
    scene._narration.queue.dismiss()  # FIRST_PICKUP, raised alongside the card

    _press(scene, pygame.K_p)
    scene.update(0.016)

    assert scene._card is None
    assert generation.pending_seeds == ()
    assert generation.is_seed_ready is True


def test_a_second_press_advances_once_the_card_has_been_dismissed() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP, EncounterKind.NOTHING])
    _resolve_next_screen(scene)
    scene._narration.queue.dismiss()  # FIRST_PICKUP, raised alongside the card

    _press(scene, pygame.K_SPACE)
    scene.update(0.016)
    assert scene._card is None

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS / 2)

    assert scene._phase is _Phase.WALKING_TO_EXIT


def test_draw_centers_the_effect_card_at_the_width_battle_typesets_its_own_into(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Card, int, int, str | None]] = []

    def spy_draw_card(
        surface: pygame.Surface, card: Card, *, center_x: int, column_width: int, footer: str | None = None
    ) -> None:
        calls.append((card, center_x, column_width, footer))

    monkeypatch.setattr("eye.gui.scenes.exploration.draw_card", spy_draw_card)
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)
    surface = pygame.Surface((800, 600))

    scene.draw(surface)

    assert calls == [(scene._card, surface.get_width() // 2, card_column_width(surface), _CARD_FOOTER)]


def test_draw_renders_no_card_when_none_is_up(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[None] = []
    monkeypatch.setattr(
        "eye.gui.scenes.exploration.draw_card",
        lambda *args, **kwargs: calls.append(None),
    )
    scene, _ = _scene([EncounterKind.NOTHING])
    _resolve_next_screen(scene)

    scene.draw(pygame.Surface((800, 600)))

    assert calls == []


def test_draw_with_the_effect_card_up_and_the_default_icons_does_not_raise() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)
    assert scene._card is not None

    scene.draw(pygame.Surface((800, 600)))


def test_the_hud_line_still_reports_the_pickup_while_the_card_is_up() -> None:
    scene, generation = _scene([EncounterKind.EFFECT_PICKUP])
    granted = _granted_effect(generation)

    _resolve_next_screen(scene)

    assert scene._card is not None
    assert scene._last_message == f"You feel {effect_label(granted)} take hold."


# Spelled out rather than derived, so `.title()` is asserted against words and not against itself.
_EXPECTED_RESOURCE_CARDS: dict[ResourceKind, tuple[str, SpriteKey]] = {
    ResourceKind.HEAL: ("Heal", SpriteKey.ICON_HEALTH),
    ResourceKind.SPORES: ("Spores", SpriteKey.ICON_SPORES),
    ResourceKind.SEED_GROWTH: ("Seed Growth", SpriteKey.ICON_SEED_GROWTH),
    ResourceKind.DISTANCE_DISCOUNT: ("Distance Discount", SpriteKey.ICON_DISTANCE_DISCOUNT),
}


@pytest.mark.parametrize("kind", list(ResourceKind))
def test_a_resource_pickup_raises_a_card_for_what_it_granted(kind: ResourceKind) -> None:
    expected_title, expected_icon_key = _EXPECTED_RESOURCE_CARDS[kind]
    scene, _ = _scene([EncounterKind.RESOURCE_PICKUP], resource_queue=[kind])

    _resolve_next_screen(scene)

    card = scene._card
    assert card is not None
    assert card.title == expected_title
    assert card.description == RESOURCE_DESCRIPTIONS[kind]
    assert card.subtitle == f"+{_RESOURCE_MAGNITUDES[kind]}"
    assert isinstance(card.icon, SpriteIcon)
    assert card.icon.sprite_key is expected_icon_key


def test_resource_descriptions_covers_every_resource_kind() -> None:
    for kind in ResourceKind:
        assert RESOURCE_DESCRIPTIONS[kind]  # non-empty


def test_resource_pickup_raises_the_card_only_once_the_walk_reaches_the_marker() -> None:
    # The reveal point: advance() applied the pickup back when the screen loaded (ADR 0012).
    scene, _ = _scene([EncounterKind.RESOURCE_PICKUP], resource_queue=[ResourceKind.SPORES])
    _drain_narration(scene)  # INTRO_LORE + FIRST_EXPLORATION, queued at construction

    assert scene._card is None  # AT_ENTRY, the pickup not reached yet

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)
    assert scene._card is None  # mid-walk

    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)  # arrives at the marker, RESOLVED

    assert scene._card is not None


def test_resource_pickup_on_a_later_screen_raises_the_card_at_its_own_marker() -> None:
    # The steady-state path: later screens load at a WALKING_TO_EXIT arrival, not at construction.
    scene, _ = _scene(
        [EncounterKind.NOTHING, EncounterKind.RESOURCE_PICKUP], resource_queue=[ResourceKind.DISTANCE_DISCOUNT]
    )
    _resolve_next_screen(scene)  # screen 1, empty
    assert scene._card is None

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS)  # screen 2 loads: advance() applies the resource
    assert scene._card is None  # AT_ENTRY, the pickup not reached yet

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)

    card = scene._card
    assert card is not None
    assert card.title == "Distance Discount"


def test_advancing_with_a_resource_card_up_dismisses_it_without_starting_the_walk() -> None:
    scene, _ = _scene([EncounterKind.RESOURCE_PICKUP, EncounterKind.NOTHING], resource_queue=[ResourceKind.HEAL])
    _resolve_next_screen(scene)
    assert scene._card is not None

    _press(scene, pygame.K_SPACE)
    assert scene.update(WALK_TO_EXIT_DURATION_SECONDS) is None

    assert scene._card is None
    assert scene._phase is _Phase.RESOLVED


def test_the_hud_line_still_reports_a_resource_pickup_while_the_card_is_up() -> None:
    scene, _ = _scene([EncounterKind.RESOURCE_PICKUP], resource_queue=[ResourceKind.SEED_GROWTH])

    _resolve_next_screen(scene)

    assert scene._card is not None
    assert scene._last_message == f"You gain {_RESOURCE_MAGNITUDES[ResourceKind.SEED_GROWTH]} (Seed Growth)."


def test_draw_with_a_resource_card_up_and_the_default_icons_does_not_raise() -> None:
    scene, _ = _scene([EncounterKind.RESOURCE_PICKUP], resource_queue=[ResourceKind.SPORES])
    _resolve_next_screen(scene)
    assert scene._card is not None

    scene.draw(pygame.Surface((800, 600)))


# A colour no icon or glyph paints, so anything still wearing it was left untouched.
_UNDRAWN = pygame.Color("magenta")
# The largest total the counter's slot holds at 640px with the top row at its most crowded.
_SPORES_DIGIT_BUDGET = 6


def _art_atlas() -> SpriteAtlas:
    return build_art_atlas(Path("eye/gui/sprites"))


def _ink_bounds(draw: Callable[[pygame.Surface], None]) -> pygame.Rect:
    """The bounding box of everything `draw` paints onto an otherwise untouched surface. Each
    top-row element gets its own surface; drawn together they would be one band."""
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)
    draw(surface)
    surface.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only what was drawn
    return surface.get_bounding_rect()


def _spores_counter_boxes(scene: ExplorationScene, total: int) -> tuple[pygame.Rect, pygame.Rect]:
    icon = pygame.Rect(scene._spores_counter_left, _ICON_MARGIN, _SPORES_ICON_SIZE, _SPORES_ICON_SIZE)
    text = get_font(GameFont.ITHACA, _FONT_SIZE).render(str(total), True, _TEXT_COLOR)
    return icon, pygame.Rect(
        icon.right + _SPORES_LABEL_GAP,
        _ICON_MARGIN + (_SPORES_ICON_SIZE - text.get_height()) // 2,
        *text.get_size(),
    )


def _assert_counter_reads(scene: ExplorationScene, total: int) -> None:
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)
    scene._draw_spores_counter(surface)

    _, text_box = _spores_counter_boxes(scene, total)
    expected = pygame.Surface(_WINDOW_SIZE)
    expected.fill(_UNDRAWN)
    expected.blit(get_font(GameFont.ITHACA, _FONT_SIZE).render(str(total), True, _TEXT_COLOR), text_box.topleft)

    assert pygame.image.tobytes(surface.subsurface(text_box), "RGBA") == pygame.image.tobytes(
        expected.subsurface(text_box), "RGBA"
    )


def test_the_spores_counter_shows_the_running_total_and_follows_it_as_spores_arrive() -> None:
    award = _RESOURCE_MAGNITUDES[ResourceKind.SPORES]
    scene, generation = _scene([EncounterKind.RESOURCE_PICKUP] * 2, [ResourceKind.SPORES] * 2)
    _drain_narration(scene)  # INTRO_LORE + FIRST_EXPLORATION, queued at construction
    _assert_counter_reads(scene, 0)

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)  # screen 1's marker
    _assert_counter_reads(scene, award)

    _press(scene, pygame.K_SPACE)  # closes the pickup card the marker raised
    scene.update(0.016)
    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS)  # screen 2 loads
    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)  # screen 2's marker

    assert generation.spores_gained == award * 2
    _assert_counter_reads(scene, award * 2)


def test_the_spores_counter_withholds_a_spore_pickup_until_the_walk_reaches_it() -> None:
    # advance() credits the pickup when its screen loads, so the drawn total is a snapshot.
    scene, generation = _scene([EncounterKind.RESOURCE_PICKUP], [ResourceKind.SPORES])
    _drain_narration(scene)  # INTRO_LORE + FIRST_EXPLORATION, queued at construction
    assert generation.spores_gained == _RESOURCE_MAGNITUDES[ResourceKind.SPORES]  # already credited

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)
    _assert_counter_reads(scene, 0)

    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)

    _assert_counter_reads(scene, generation.spores_gained)


def test_the_spores_counter_draws_the_borderless_icon_scaled_into_the_top_rows_box() -> None:
    # The real art, not a fixture: build_placeholder_atlas() is 32x32 for every key and the
    # tmp_path helpers write 4x4, so only a 210x210 source can catch an unscaled blit.
    atlas = _art_atlas()
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING]))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, atlas)
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)

    scene._draw_spores_counter(surface)

    icon_box, _ = _spores_counter_boxes(scene, generation.spores_gained)
    expected = pygame.Surface(_WINDOW_SIZE)
    expected.fill(_UNDRAWN)
    borderless_icon(atlas, SpriteKey.ICON_SPORES).render(expected, pygame.Vector2(icon_box.topleft), _SPORES_ICON_SIZE)

    assert pygame.image.tobytes(surface.subsurface(icon_box), "RGBA") == pygame.image.tobytes(
        expected.subsurface(icon_box), "RGBA"
    )


# Bigger than _ADVANCES_TO_READY_SEED, which counts advances at the uncapped rate: this scene
# spawns beside matured turf, where seed growth is slower.
_MAX_ADVANCES_TO_READY_SEED = _ADVANCES_TO_READY_SEED * 10


def _worst_case_top_row_scene() -> ExplorationScene:
    """The top row as crowded as it can get: both status icons up, every Lifespan effect in the
    buff row, and a spore total at the counter's full digit budget."""
    game = Game(
        ScriptedEncounterRandom([EncounterKind.NOTHING] * (_MAX_ADVANCES_TO_READY_SEED + 1)),
        matured_turf_positions=(1,),
    )
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, _art_atlas())
    for _ in range(_MAX_ADVANCES_TO_READY_SEED):
        if scene._can_plant_seed():
            break
        _resolve_next_screen(scene)
    assert scene._can_plant_seed() is True  # the seed status icon is showing
    assert game.matured_turf_positions != ()  # and so is the turf one

    scene._displayed_effects = tuple(EffectName)
    scene._displayed_spores = 10**_SPORES_DIGIT_BUDGET - 1
    return scene


def test_the_spores_counter_clears_the_rest_of_the_top_row_at_its_most_crowded() -> None:
    # The slot is bounded on both sides by rows that move, so only the worst case proves it fits.
    scene = _worst_case_top_row_scene()

    status_icons = _ink_bounds(scene._draw_status_icons)
    counter = _ink_bounds(scene._draw_spores_counter)
    buff_row = _ink_bounds(scene._draw_buff_icons)

    # An empty rect collides with nothing and would pass every assertion below without drawing.
    assert status_icons.size != (0, 0)
    assert counter.size != (0, 0)
    assert buff_row.size != (0, 0)
    assert len(scene._displayed_effects) == len(EffectName)
    assert not counter.colliderect(status_icons)
    assert not counter.colliderect(buff_row)
    assert pygame.Rect((0, 0), _WINDOW_SIZE).contains(counter)
    # A legibility margin, not bare non-overlap: a full _ICON_MARGIN clear of the buff row.
    _, text_box = _spores_counter_boxes(scene, scene._displayed_spores)
    assert text_box.right + _ICON_MARGIN <= buff_row.left


def test_the_spores_counter_falls_back_to_the_bordered_sprite_for_a_variant_less_atlas() -> None:
    # build_placeholder_atlas() carries no variants, so insisting on the borderless one would raise.
    atlas = build_placeholder_atlas()
    assert atlas.has_variant_set(SpriteKey.ICON_SPORES) is False
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING]))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, atlas)
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)

    scene._draw_spores_counter(surface)

    icon_box, _ = _spores_counter_boxes(scene, generation.spores_gained)
    expected = pygame.Surface(_WINDOW_SIZE)
    expected.fill(_UNDRAWN)
    SpriteIcon(atlas, SpriteKey.ICON_SPORES).render(expected, pygame.Vector2(icon_box.topleft), _SPORES_ICON_SIZE)

    assert pygame.image.tobytes(surface.subsurface(icon_box), "RGBA") == pygame.image.tobytes(
        expected.subsurface(icon_box), "RGBA"
    )


def test_draw_background_renders_the_biome_the_generation_is_currently_in(tmp_path: Path) -> None:
    scene, generation = _scene(kind_queue=[EncounterKind.NOTHING] * 20)
    for _ in range(20):
        scene.update(WALK_TO_EXIT_DURATION_SECONDS)
        scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)

    surface = pygame.Surface(_WINDOW_SIZE)
    scene.draw(surface)  # must not raise; real assertion is the key below

    assert resolve_biome(generation.distance_from_home) is not None  # sanity: resolver is callable


def test_draw_background_uses_the_resolved_biome_key(monkeypatch: pytest.MonkeyPatch) -> None:
    scene, generation = _scene([EncounterKind.NOTHING])
    seen_keys: list[SpriteKey] = []

    def _fake_crop_to_cover(surface: pygame.Surface, target_size: tuple[int, int]) -> pygame.Surface:
        return surface  # placeholder atlas surfaces are already tiny; identity is fine here

    import eye.gui.scenes.exploration as exploration_module

    original_get = scene._atlas.get

    def _tracking_get(key: SpriteKey) -> pygame.Surface:
        if key in (SpriteKey.BIOME_TURF, SpriteKey.BIOME_DEAD_FOREST, SpriteKey.BIOME_FOREST):
            seen_keys.append(key)
        return original_get(key)

    monkeypatch.setattr(scene._atlas, "get", _tracking_get)
    monkeypatch.setattr(exploration_module, "crop_to_cover", _fake_crop_to_cover)

    scene.draw(pygame.Surface(_WINDOW_SIZE))

    assert seen_keys == [resolve_biome(generation.distance_from_home)]


def test_the_bottom_hud_leaves_the_spore_total_to_the_top_row() -> None:
    # Compared against a full render, so this pins where the remaining lines sit too.
    scene, generation = _scene([EncounterKind.RESOURCE_PICKUP], [ResourceKind.SPORES])
    _resolve_next_screen(scene)
    assert generation.spores_gained != 0  # a leftover spores line would have something to say
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)

    scene._draw_hud(surface)

    lines = [
        "Seed ready to plant: no",
        scene._last_message,
        "Space/Enter: advance   P: plant seed",
    ]
    font = get_font(GameFont.ITHACA, _FONT_SIZE)
    expected = pygame.Surface(_WINDOW_SIZE)
    expected.fill(_UNDRAWN)
    top = expected.get_height() - len(lines) * _FONT_SIZE - _HUD_MARGIN
    for index, line in enumerate(lines):
        expected.blit(font.render(line, True, _TEXT_COLOR), (_HUD_MARGIN, top + index * _FONT_SIZE))

    assert pygame.image.tobytes(surface, "RGBA") == pygame.image.tobytes(expected, "RGBA")


def test_draw_props_samples_the_resolved_pools_the_correct_number_of_times(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING]))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, _art_atlas())
    choice_calls = 0
    original_choice = scene._prop_rng.choice

    def _counting_choice(pool: list[pygame.Surface]) -> pygame.Surface:
        nonlocal choice_calls
        choice_calls += 1
        return original_choice(pool)

    monkeypatch.setattr(scene._prop_rng, "choice", _counting_choice)

    scene.draw(pygame.Surface(_WINDOW_SIZE))

    from eye.gui.props import resolve_prop_sampling

    expected_total = sum(count for _, count in resolve_prop_sampling(generation.distance_from_home))
    assert choice_calls == expected_total


def _drain_narration(scene: ExplorationScene) -> list[NarrationEntry]:
    """Dismisses every currently queued entry and returns them in order -- FIRST_EXPLORATION queues
    at construction, so a screen's own trigger can land behind it rather than at the front."""
    entries: list[NarrationEntry] = []
    while scene._narration.queue.is_active:
        current = scene._narration.queue.current
        assert current is not None
        entries.append(current)
        scene._narration.queue.dismiss()
    return entries


def test_for_new_generation_fires_first_exploration_narration() -> None:
    scene, _ = _scene([EncounterKind.NOTHING])

    assert scene._narration.queue.is_active is True


def test_for_new_generation_fires_intro_lore_ahead_of_first_exploration_on_a_fresh_save() -> None:
    scene, _ = _scene([EncounterKind.NOTHING])

    entries = _drain_narration(scene)

    assert entries[-1] == NarrationEntry(
        message="You venture out of the hive to spread your swarm's turf.",
        subtitle="Press Space or Enter to venture further.",
    )
    assert len(entries) > 1  # the lore beats precede it
    assert NarrationTrigger.INTRO_LORE in scene._narration._seen


def test_intro_lore_does_not_refire_for_a_later_generation_on_the_same_save() -> None:
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING]))
    save_seen = frozenset({NarrationTrigger.INTRO_LORE})
    narration = NarrationTriggers.for_generation(save_seen)

    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, build_placeholder_atlas(), narration=narration)

    entries = _drain_narration(scene)
    assert len(entries) == 1  # just FIRST_EXPLORATION -- INTRO_LORE was already seen on this save


def test_resuming_after_combat_does_not_refire_an_already_seen_trigger() -> None:
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING]))
    generation = game.start_generation()
    triggers = NarrationTriggers()
    ExplorationScene.for_new_generation(generation, game, build_placeholder_atlas(), narration=triggers)
    while triggers.queue.is_active:  # the player already saw and cleared everything queued
        triggers.queue.dismiss()

    scene = ExplorationScene.resuming_after_combat(generation, game, build_placeholder_atlas(), narration=triggers)

    assert scene._narration.queue.is_active is False


def test_seed_ready_does_not_fire_mid_walk_and_fires_once_the_screen_is_at_rest() -> None:
    scene, generation = _scene([EncounterKind.NOTHING] * _ADVANCES_TO_READY_SEED)
    assert generation.is_seed_ready is False

    for _ in range(_ADVANCES_TO_READY_SEED):
        _resolve_next_screen(scene)

    assert generation.is_seed_ready is True
    assert scene._phase is _Phase.RESOLVED
    # The seed became ready while arriving at this screen (AT_ENTRY), not while at rest -- the
    # mid-walk check that saw it must not have fired.
    assert NarrationTrigger.FIRST_SEED_READY not in scene._narration._seen

    scene.update(0.016)  # a frame at rest, seed still ready

    assert NarrationTrigger.FIRST_SEED_READY in scene._narration._seen
    assert NarrationEntry(
        message="A seed is ready to plant.",
        subtitle="Press P to plant it - it won't strengthen you, only marks this ground for whoever comes after.",
    ) in _drain_narration(scene)


def test_effect_pickup_fires_first_pickup_narration() -> None:
    # advance() reveals the pickup at construction (ADR 0012) -- FIRST_PICKUP fires there too, as
    # soon as the screen loads, not once the walk reaches the marker.
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP])

    assert NarrationEntry(
        message="Something ahead will change you.",
        subtitle="For good or ill - and it stays with you until this life ends.",
    ) in _drain_narration(scene)


def test_enemy_encounter_fires_first_battle_narration() -> None:
    # advance() reveals the encounter at construction (ADR 0012) -- FIRST_BATTLE fires there too,
    # as soon as the screen loads, before the player has walked up to it.
    scene, _ = _scene([EncounterKind.ENEMY])

    assert NarrationEntry(
        message="A hostile strain blocks your path.",
        subtitle="Ready your swarm. A fight is close.",
    ) in _drain_narration(scene)


def test_a_later_screens_advance_fires_its_own_encounter_narration() -> None:
    # Exercises _arrive_at_exit's own _fire_narration_for_advance call -- the steady-state path for
    # every screen after the first, distinct from for_new_generation's construction-time call.
    scene, _ = _scene([EncounterKind.NOTHING, EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)  # screen 1, empty

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS)  # screen 2 loads: advance() reveals the pickup

    assert NarrationEntry(
        message="Something ahead will change you.",
        subtitle="For good or ill - and it stays with you until this life ends.",
    ) in _drain_narration(scene)


def test_card_is_not_drawn_while_narration_is_active() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP])
    _drain_narration(scene)  # FIRST_EXPLORATION + FIRST_PICKUP, both fired by advance() at construction
    _resolve_next_screen(scene)  # arrives at the pickup and raises its Card
    assert scene._card is not None

    scene._narration.fire(NarrationTrigger.FIRST_DEATH, "msg", "sub")  # some other trigger, still active
    surface = pygame.Surface((800, 600))
    surface.fill(_UNDRAWN)
    scene._draw_raised_card(surface)
    surface.set_colorkey(_UNDRAWN)

    assert surface.get_bounding_rect().size == (0, 0)


def test_narration_dismiss_does_not_also_dismiss_the_pickup_card_underneath() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP])
    _drain_narration(scene)  # FIRST_EXPLORATION + FIRST_PICKUP, both fired by advance() at construction

    _resolve_next_screen(scene)  # arrives at the pickup and raises its Card
    assert scene._card is not None
    assert scene._narration.queue.is_active is False  # already dismissed well before the walk got here

    # Some other trigger (e.g. FIRST_PROXIMITY_FALLOFF, checked every frame independently of the
    # pickup) becoming active while the card is up must not let a dismiss also clear the card.
    scene._narration.fire(NarrationTrigger.FIRST_DEATH, "msg", "sub")
    assert scene._narration.queue.is_active is True

    _press(scene, pygame.K_SPACE)
    scene.update(0.016)

    assert scene._narration.queue.is_active is False  # dismissed
    assert scene._card is not None  # the card underneath is still up to read


def test_resource_pickup_does_not_fire_the_buff_debuff_pickup_narration() -> None:
    scene, _ = _scene([EncounterKind.RESOURCE_PICKUP], resource_queue=[ResourceKind.SPORES])
    _drain_narration(scene)

    _resolve_next_screen(scene)

    assert NarrationTrigger.FIRST_PICKUP not in scene._narration._seen


def test_proximity_falloff_does_not_fire_when_no_turf_has_matured_yet() -> None:
    # inf (no matured turf this generation) trivially satisfies ">= PROXIMITY_FALLOFF_RANGE", but
    # nothing has actually been "ventured" on a fresh save's first screen -- must not fire.
    scene, generation = _scene([EncounterKind.NOTHING])

    scene.update(0.016)

    assert generation.distance_to_nearest_matured_turf == math.inf
    assert NarrationTrigger.FIRST_PROXIMITY_FALLOFF not in scene._narration._seen


def test_proximity_falloff_does_not_fire_within_range_of_a_matured_turf() -> None:
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING]), matured_turf_positions=(0,))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, build_placeholder_atlas())

    scene.update(0.016)

    assert generation.distance_to_nearest_matured_turf < PROXIMITY_FALLOFF_RANGE
    assert NarrationTrigger.FIRST_PROXIMITY_FALLOFF not in scene._narration._seen


def test_proximity_falloff_fires_once_walked_far_enough_past_a_matured_turf() -> None:
    screens_to_walk = int(PROXIMITY_FALLOFF_RANGE)
    game = Game(ScriptedEncounterRandom([EncounterKind.NOTHING] * screens_to_walk), matured_turf_positions=(0,))
    generation = game.start_generation()
    scene = ExplorationScene.for_new_generation(generation, game, build_placeholder_atlas())

    for _ in range(screens_to_walk):
        _resolve_next_screen(scene)

    assert generation.distance_to_nearest_matured_turf >= PROXIMITY_FALLOFF_RANGE
    assert NarrationTrigger.FIRST_PROXIMITY_FALLOFF in scene._narration._seen


def test_narration_dismiss_withholds_a_mid_sequence_advance_but_not_the_last() -> None:
    scene, _ = _scene([EncounterKind.NOTHING])
    # INTRO_LORE (4 entries) + FIRST_EXPLORATION (1), queued at construction.
    entries_queued = 5
    assert scene._narration.queue.is_active is True

    for _ in range(entries_queued - 1):
        # A mid-sequence dismiss (one of INTRO_LORE's own entries) only advances the narration,
        # never the game underneath it.
        _press(scene, pygame.K_SPACE)
        scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)
        assert scene._phase is _Phase.AT_ENTRY

    assert scene._narration.queue.is_active is True  # one entry (FIRST_EXPLORATION) left

    # The press that empties the queue also drives its own action (K_SPACE -> ADVANCE) in the same
    # press.
    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)

    assert scene._narration.queue.is_active is False
    assert scene._phase is _Phase.RESOLVED


def test_draw_renders_the_active_narration_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    scene, _ = _scene([EncounterKind.NOTHING])
    drawn: list[NarrationEntry] = []
    import eye.gui.scenes.exploration as exploration_module

    monkeypatch.setattr(
        exploration_module, "draw_narration", lambda surface, entry, *, center_x, column_width: drawn.append(entry)
    )

    scene.draw(pygame.Surface((800, 600)))

    assert drawn == [scene._narration.queue.current]
