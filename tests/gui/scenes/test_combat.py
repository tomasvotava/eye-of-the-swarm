import random

import pygame
import pytest

from eye.bestiary import BESTIARY
from eye.character import Character
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.battle import TurnPhase
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName
from eye.combat.stats import Stats
from eye.combat.tuning import RESONANCE_METER_PREFILL_RATIO
from eye.exploration.encounters import EncounterKind, Strain
from eye.exploration.events import EnemyEncountered
from eye.gui.assets import SpriteKey, build_placeholder_atlas
from eye.gui.scenes.combat import ACTION_KEYS, CombatScene, _resolve_enemy_sprite_key
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.scenes.skilltree import SkillTreeScene
from eye.session.game import Game
from eye.session.generation import Generation
from tests.session.doubles import ScriptedEncounterRandom

_STATS = Stats(max_hp=20, attack=5, defense=2, meter_capacity=100, meter_fill_rate=1)
# Two entries (both STRUGGLE-kind, so win/loss math is unaffected by which one gets picked) so
# cursor navigation across more than one row is actually exercised.
_ACTIONS = (
    ActionDefinition(kind=ActionKind.STRUGGLE, name="Struggle"),
    ActionDefinition(kind=ActionKind.STRUGGLE, name="Wild Swing"),
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


def _game_owning(generation: Generation) -> Game:
    # CombatScene calls game.end_generation() on a death, which requires the Game to already
    # "own" the generation it started -- Generation is constructed directly here (bypassing
    # Game.start_generation()) so the test can pin exact combat stats, so ownership is wired by
    # hand the same way it would be if start_generation() had built it.
    game = Game(random.Random())
    game._current_generation = generation
    return game


def _encounter(generation: Generation) -> EnemyEncountered:
    events = generation.advance()
    return next(event for event in events if isinstance(event, EnemyEncountered))


def _press(scene: CombatScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def _drive_to_transition(scene: CombatScene, max_frames: int = 200) -> ExplorationScene | SkillTreeScene:
    for _ in range(max_frames):
        _press(scene, ACTION_KEYS[0])
        result = scene.update(0.016)
        if result is not None:
            assert isinstance(result, ExplorationScene | SkillTreeScene)
            return result
    raise AssertionError("battle did not conclude within max_frames")


def test_construction_starts_the_battle_and_prefills_the_resonance_meter() -> None:
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)
    game = _game_owning(generation)
    encounter = _encounter(generation)

    scene = CombatScene(generation, game, encounter, build_placeholder_atlas())

    expected = round(_STATS.meter_capacity * RESONANCE_METER_PREFILL_RATIO)
    assert scene._battle.player.current_meter == expected


def test_handle_pygame_event_ignores_non_keydown() -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)  # advance to AWAITING_PLAYER_ACTION

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=ACTION_KEYS[0]))

    assert scene._pending_action_index is None


def test_handle_pygame_event_ignores_a_key_when_no_action_is_pending() -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())

    _press(scene, ACTION_KEYS[0])  # no update() yet, so no PlayerTurnNeedsAction is pending

    assert scene._pending_action_index is None


def test_handle_pygame_event_ignores_an_index_beyond_the_available_actions() -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)  # advance to AWAITING_PLAYER_ACTION with exactly two available actions

    _press(scene, ACTION_KEYS[2])

    assert scene._pending_action_index is None


def test_handle_pygame_event_accepts_a_valid_action_index() -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)

    _press(scene, ACTION_KEYS[1])

    assert scene._pending_action_index == 1


def test_handle_pygame_event_moves_the_cursor_down_and_wraps() -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)

    _press(scene, pygame.K_DOWN)
    assert scene._cursor_index == 1

    _press(scene, pygame.K_DOWN)
    assert scene._cursor_index == 0


def test_handle_pygame_event_moves_the_cursor_up_and_wraps() -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)

    _press(scene, pygame.K_UP)

    assert scene._cursor_index == 1  # wraps from 0 to the last available index


def test_handle_pygame_event_enter_selects_the_cursor_position() -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)

    _press(scene, pygame.K_DOWN)
    _press(scene, pygame.K_RETURN)

    assert scene._pending_action_index == 1


def test_advance_query_resets_the_cursor_for_a_new_pending_query() -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)  # first AWAITING_PLAYER_ACTION query, cursor at 0
    _press(scene, pygame.K_DOWN)
    assert scene._cursor_index == 1
    _press(scene, pygame.K_RETURN)

    for _ in range(10):
        scene.update(0.016)
        if scene._pending_query is not None:
            break
    else:
        raise AssertionError("did not reach the next player-action query")

    assert scene._cursor_index == 0


def test_resolve_enemy_sprite_key_matches_a_same_named_sprite_key() -> None:
    assert _resolve_enemy_sprite_key("BRAMBLE") is SpriteKey.BRAMBLE


def test_resolve_enemy_sprite_key_falls_back_to_unknown_for_an_unmatched_name() -> None:
    assert _resolve_enemy_sprite_key("NOT_A_REAL_STRAIN") is SpriteKey.UNKNOWN


def test_update_resolves_automatic_phases_without_input() -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())

    scene.update(0.016)

    assert scene._battle.turn_phase is TurnPhase.AWAITING_PLAYER_ACTION


def test_win_finishes_the_battle_and_returns_a_fresh_exploration_scene() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=overwhelming)
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())

    next_scene = _drive_to_transition(scene)

    assert isinstance(next_scene, ExplorationScene)
    assert generation.died is False
    assert generation.spores_gained == BESTIARY[Strain.BRAMBLE].spore_award


def test_loss_ends_the_generation_and_returns_a_skill_tree_scene() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = Character(current_hp=5, max_hp=5)
    generation = _generation(stats=fragile, character=character)
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())

    next_scene = _drive_to_transition(scene)

    assert isinstance(next_scene, SkillTreeScene)
    assert generation.died is True
    game.start_generation()  # raises if end_generation() didn't clear Game's current generation


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    generation = _generation()
    game = _game_owning(generation)
    scene = CombatScene(generation, game, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)  # reach AWAITING_PLAYER_ACTION so the action menu also renders

    scene.draw(pygame.Surface(surface_size))
