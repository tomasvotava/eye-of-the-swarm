import json
from collections.abc import Sequence
from pathlib import Path

import pygame
import pytest

from eye.combat.effects import EffectName
from eye.exploration.encounters import Biome, EncounterKind, ResourceKind, Strain
from eye.exploration.events import EffectGranted, EnemyEncountered, NothingHappened, ResourceGranted
from eye.exploration.tuning import SEED_GROWTH_RATE_CAP, SEED_GROWTH_THRESHOLD
from eye.gui.assets import PLACEHOLDER_SPRITE_SIZE, SpriteKey, build_art_atlas, build_placeholder_atlas
from eye.gui.effect_card import EffectCard, card_column_width
from eye.gui.play_scene import EnterCombat, PlaySceneTransition
from eye.gui.scenes.exploration import (
    _BUFF_ICON_SIZE,
    _BUFF_ICON_STEP,
    _EFFECT_CARD_FOOTER,
    _ICON_MARGIN,
    _PLAYER_SCALE_FACTOR,
    KEY_ACTIONS,
    ExplorationAction,
    ExplorationScene,
    PlayerAnimationState,
    _Phase,
    _resolve_encounter_sprite_key,
)
from eye.gui.tuning import (
    ENTRY_X_FRACTION,
    WALK_TO_ENCOUNTER_DURATION_SECONDS,
    WALK_TO_EXIT_DURATION_SECONDS,
)
from eye.gui.widgets import EFFECT_DESCRIPTIONS, SpriteBuffIcon, effect_label
from eye.session.events import SessionEvent
from eye.session.game import Game
from eye.session.generation import Generation
from tests.session.doubles import ScriptedEncounterRandom

_ADVANCES_TO_READY_SEED = int(SEED_GROWTH_THRESHOLD // SEED_GROWTH_RATE_CAP)


def _scene(kind_queue: Sequence[EncounterKind] = ()) -> tuple[ExplorationScene, Generation]:
    game = Game(ScriptedEncounterRandom(kind_queue))
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


def _press(scene: ExplorationScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def _resolve_next_screen(scene: ExplorationScene) -> PlaySceneTransition | None:
    """Drives `scene` from wherever it currently sits (`RESOLVED` or `AT_ENTRY`, both reachable
    between screens) through to the next `RESOLVED`/`EnterCombat` reveal -- one full screen's
    worth of walking. `for_new_generation()` already fires `advance()` for the first screen and
    joins at `AT_ENTRY`, so only the second half-lap is needed there; every screen after starts
    the full `RESOLVED -> WALKING_TO_EXIT -> AT_ENTRY -> WALKING_TO_ENCOUNTER` cycle."""
    if scene._phase is _Phase.RESOLVED:
        _press(scene, pygame.K_SPACE)
        assert scene.update(WALK_TO_EXIT_DURATION_SECONDS) is None
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

    _press(scene, pygame.K_p)
    scene.update(0.016)

    assert generation.is_seed_ready is False
    assert generation.pending_seeds != ()


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

    _press(scene, pygame.K_SPACE)
    transition = scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)

    assert isinstance(transition, EnterCombat)
    assert isinstance(transition.encounter, EnemyEncountered)


def test_enter_combat_is_withheld_until_the_walk_to_the_encounter_completes() -> None:
    scene, _ = _scene([EncounterKind.ENEMY])

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
    sampled = surface.get_at((x, surface.get_height() // 2))
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
    assert len(calls) == len(row) + (0 if scene._effect_card is None else 1)
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
    # The reveal point: advance() applied the pickup back when the screen loaded (ADR 0012).
    granted = _granted_effect(generation)

    assert scene._effect_card is None  # AT_ENTRY, the pickup not reached yet

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)
    assert scene._effect_card is None  # mid-walk

    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS / 2)  # arrives at the marker, RESOLVED

    card = scene._effect_card
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
    assert scene._effect_card is None

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS)  # screen 2 loads: advance() applies the pickup
    granted = _granted_effect(generation)
    assert scene._effect_card is None  # AT_ENTRY, the pickup not reached yet

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_ENCOUNTER_DURATION_SECONDS)

    card = scene._effect_card
    assert card is not None
    assert card.title == effect_label(granted)


@pytest.mark.parametrize("kind", [EncounterKind.RESOURCE_PICKUP, EncounterKind.NOTHING])
def test_a_screen_that_grants_no_effect_raises_no_card(kind: EncounterKind) -> None:
    scene, _ = _scene([kind])

    _resolve_next_screen(scene)

    assert scene._effect_card is None


def test_an_enemy_encounter_raises_no_card() -> None:
    scene, _ = _scene([EncounterKind.ENEMY])

    assert isinstance(_resolve_next_screen(scene), EnterCombat)
    assert scene._effect_card is None


def test_the_effect_card_stands_however_long_the_player_leaves_it() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)
    assert scene._effect_card is not None

    for _ in range(100):
        assert scene.update(1.0) is None

    assert scene._effect_card is not None


def test_advancing_with_the_card_up_dismisses_it_without_starting_the_walk() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP, EncounterKind.NOTHING])
    _resolve_next_screen(scene)
    assert scene._effect_card is not None

    _press(scene, pygame.K_SPACE)
    assert scene.update(WALK_TO_EXIT_DURATION_SECONDS) is None

    assert scene._effect_card is None
    assert scene._phase is _Phase.RESOLVED


def test_the_frame_that_dismisses_the_card_still_advances_the_player_animation(tmp_path: Path) -> None:
    # The dismiss branch sits below the animator tick, not above it, so this frame still
    # advances the clip.
    scene = _scene_with_real_player_art(tmp_path, [EncounterKind.EFFECT_PICKUP, EncounterKind.NOTHING])
    _resolve_next_screen(scene)
    assert scene._effect_card is not None
    assert scene._player_animator is not None
    before = scene._player_animator.current_frame()

    _press(scene, pygame.K_SPACE)
    scene.update(1 / 8)  # exactly one frame at the default 8fps test clip

    assert scene._effect_card is None
    after = scene._player_animator.current_frame()
    assert pygame.image.tobytes(before, "RGBA") != pygame.image.tobytes(after, "RGBA")


def test_a_key_bound_to_no_action_dismisses_the_card_too() -> None:
    assert pygame.K_q not in KEY_ACTIONS
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP, EncounterKind.NOTHING])
    _resolve_next_screen(scene)
    assert scene._effect_card is not None

    _press(scene, pygame.K_q)
    assert scene.update(WALK_TO_EXIT_DURATION_SECONDS) is None

    assert scene._effect_card is None
    assert scene._phase is _Phase.RESOLVED


def test_the_plant_key_dismisses_the_card_without_planting() -> None:
    scene, generation = _scene([EncounterKind.NOTHING] * (_ADVANCES_TO_READY_SEED - 1) + [EncounterKind.EFFECT_PICKUP])
    for _ in range(_ADVANCES_TO_READY_SEED):
        _resolve_next_screen(scene)
    assert generation.is_seed_ready is True
    assert scene._effect_card is not None

    _press(scene, pygame.K_p)
    scene.update(0.016)

    assert scene._effect_card is None
    assert generation.pending_seeds == ()
    assert generation.is_seed_ready is True


def test_a_second_press_advances_once_the_card_has_been_dismissed() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP, EncounterKind.NOTHING])
    _resolve_next_screen(scene)

    _press(scene, pygame.K_SPACE)
    scene.update(0.016)
    assert scene._effect_card is None

    _press(scene, pygame.K_SPACE)
    scene.update(WALK_TO_EXIT_DURATION_SECONDS / 2)

    assert scene._phase is _Phase.WALKING_TO_EXIT


def test_draw_centers_the_effect_card_at_the_width_battle_typesets_its_own_into(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[EffectCard, int, int, str | None]] = []

    def spy_draw_effect_card(
        surface: pygame.Surface, card: EffectCard, *, center_x: int, column_width: int, footer: str | None = None
    ) -> None:
        calls.append((card, center_x, column_width, footer))

    monkeypatch.setattr("eye.gui.scenes.exploration.draw_effect_card", spy_draw_effect_card)
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)
    surface = pygame.Surface((800, 600))

    scene.draw(surface)

    assert calls == [(scene._effect_card, surface.get_width() // 2, card_column_width(surface), _EFFECT_CARD_FOOTER)]


def test_draw_renders_no_effect_card_when_none_is_up(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[None] = []
    monkeypatch.setattr(
        "eye.gui.scenes.exploration.draw_effect_card",
        lambda *args, **kwargs: calls.append(None),
    )
    scene, _ = _scene([EncounterKind.NOTHING])
    _resolve_next_screen(scene)

    scene.draw(pygame.Surface((800, 600)))

    assert calls == []


def test_draw_with_the_effect_card_up_and_the_default_icons_does_not_raise() -> None:
    scene, _ = _scene([EncounterKind.EFFECT_PICKUP])
    _resolve_next_screen(scene)
    assert scene._effect_card is not None

    scene.draw(pygame.Surface((800, 600)))


def test_the_hud_line_still_reports_the_pickup_while_the_card_is_up() -> None:
    scene, generation = _scene([EncounterKind.EFFECT_PICKUP])
    granted = _granted_effect(generation)

    _resolve_next_screen(scene)

    assert scene._effect_card is not None
    assert scene._last_message == f"You feel {effect_label(granted)} take hold."
