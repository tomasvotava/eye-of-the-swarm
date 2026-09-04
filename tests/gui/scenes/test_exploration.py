from collections.abc import Sequence

import pygame
import pytest

from eye.combat.effects import EffectName
from eye.exploration.encounters import Biome, EncounterKind, ResourceKind, Strain
from eye.exploration.events import EffectGranted, EnemyEncountered, NothingHappened, ResourceGranted
from eye.exploration.tuning import SEED_GROWTH_RATE_CAP, SEED_GROWTH_THRESHOLD
from eye.gui.assets import SpriteKey, build_placeholder_atlas
from eye.gui.play_scene import EnterCombat, PlaySceneTransition
from eye.gui.scenes.exploration import (
    KEY_ACTIONS,
    ExplorationAction,
    ExplorationScene,
    _Phase,
    _resolve_encounter_sprite_key,
)
from eye.gui.tuning import WALK_TO_ENCOUNTER_DURATION_SECONDS, WALK_TO_EXIT_DURATION_SECONDS
from eye.session.events import SessionEvent
from eye.session.game import Game
from eye.session.generation import Generation
from tests.session.doubles import ScriptedEncounterRandom

_ADVANCES_TO_READY_SEED = int(SEED_GROWTH_THRESHOLD // SEED_GROWTH_RATE_CAP)


def _scene(kind_queue: Sequence[EncounterKind] = ()) -> tuple[ExplorationScene, Generation]:
    game = Game(ScriptedEncounterRandom(kind_queue))
    generation = game.start_generation()
    return ExplorationScene.for_new_generation(generation, game, build_placeholder_atlas()), generation


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
