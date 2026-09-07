from collections import deque

import pygame
import pytest

from eye.bestiary import BESTIARY
from eye.character import Character
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.battle import TurnPhase
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName
from eye.combat.events import (
    ActionChosen,
    BattleEnded,
    BattleEvent,
    Death,
    DotTicked,
    EffectApplied,
    EffectExpired,
    ExtraActionTriggered,
    HealApplied,
    HitLanded,
    HitReflected,
    MeterConsumed,
    MeterFilled,
    Revive,
    SelfDamageTaken,
    TurnSkipped,
)
from eye.combat.stats import Combatant, Stats
from eye.combat.tuning import RESONANCE_METER_PREFILL_RATIO
from eye.exploration.encounters import ENCOUNTERABLE_STRAINS, EncounterKind
from eye.exploration.events import EnemyEncountered
from eye.gui.assets import SpriteKey, build_placeholder_atlas
from eye.gui.play_scene import BattleConcluded, PlaySceneTransition
from eye.gui.scenes.combat import (
    _BAR_HEIGHT,
    _FONT_SIZE,
    _GAP,
    _MARGIN,
    _METER_HEIGHT,
    ACTION_KEYS,
    CombatScene,
    Phase,
    _resolve_enemy_sprite_key,
)
from eye.session.generation import Generation
from tests.session.doubles import ScriptedEncounterRandom

_STATS = Stats(max_hp=20, attack=5, defense=2, meter_capacity=100, meter_fill_rate=1)


def _combatant(name: str = "Combatant") -> Combatant:
    return Combatant(name=name, base_stats=_STATS, current_hp=_STATS.max_hp)


# One instance of every BattleEvent variant -- used to check that `_phases_for` is exhaustive and
# currently stubbed to `[]` across the board, regardless of the field values on each event.
_ONE_OF_EACH_BATTLE_EVENT: tuple[BattleEvent, ...] = (
    Death(combatant=_combatant()),
    Revive(combatant=_combatant(), revived_hp=5),
    TurnSkipped(combatant=_combatant()),
    ActionChosen(actor=_combatant(), action=ActionKind.STRUGGLE, was_swapped_by_clouded_judgement=False),
    HitLanded(
        source=_combatant(),
        target=_combatant(),
        action=ActionKind.STRUGGLE,
        hit_index=0,
        hit_count=1,
        damage=3,
        target_hp_after=17,
    ),
    HitReflected(source=_combatant(), target=_combatant(), damage=2, target_hp_after=18),
    SelfDamageTaken(combatant=_combatant(), damage=1, combatant_hp_after=19),
    EffectApplied(target=_combatant(), effect=EffectName.FIBROUS, category=EffectCategory.BATTLE, remaining_turns=3),
    EffectExpired(target=_combatant(), effect=EffectName.FIBROUS),
    DotTicked(target=_combatant(), effect=EffectName.TOXICITY, damage=1, target_hp_after=19),
    HealApplied(target=_combatant(), effect=EffectName.NOURISHED, amount=2, target_hp_after=20),
    ExtraActionTriggered(actor=_combatant(), extra_action_index=1),
    MeterFilled(combatant=_combatant(), amount=10, meter_after=50),
    MeterConsumed(combatant=_combatant(), meter_after=0),
    BattleEnded(winner=_combatant()),
)

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


def _encounter(generation: Generation) -> EnemyEncountered:
    events = generation.advance()
    return next(event for event in events if isinstance(event, EnemyEncountered))


def _press(scene: CombatScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def _drive_to_transition(scene: CombatScene, max_frames: int = 200) -> PlaySceneTransition:
    for _ in range(max_frames):
        _press(scene, ACTION_KEYS[0])
        result = scene.update(0.016)
        if result is not None:
            return result
    raise AssertionError("battle did not conclude within max_frames")


def test_construction_starts_the_battle_and_prefills_the_resonance_meter() -> None:
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)
    encounter = _encounter(generation)

    scene = CombatScene(generation, encounter, build_placeholder_atlas())

    expected = round(_STATS.meter_capacity * RESONANCE_METER_PREFILL_RATIO)
    assert scene._battle.player.current_meter == expected


def test_handle_pygame_event_ignores_non_keydown() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)  # advance to AWAITING_PLAYER_ACTION

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=ACTION_KEYS[0]))

    assert scene._pending_action_index is None


def test_handle_pygame_event_ignores_a_key_when_no_action_is_pending() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())

    _press(scene, ACTION_KEYS[0])  # no update() yet, so no PlayerTurnNeedsAction is pending

    assert scene._pending_action_index is None


def test_handle_pygame_event_ignores_an_index_beyond_the_available_actions() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)  # advance to AWAITING_PLAYER_ACTION with exactly two available actions

    _press(scene, ACTION_KEYS[2])

    assert scene._pending_action_index is None


def test_handle_pygame_event_accepts_a_valid_action_index() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)

    _press(scene, ACTION_KEYS[1])

    assert scene._pending_action_index == 1


def test_handle_pygame_event_moves_the_cursor_down_and_wraps() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)

    _press(scene, pygame.K_DOWN)
    assert scene._cursor_index == 1

    _press(scene, pygame.K_DOWN)
    assert scene._cursor_index == 0


def test_handle_pygame_event_moves_the_cursor_up_and_wraps() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)

    _press(scene, pygame.K_UP)

    assert scene._cursor_index == 1  # wraps from 0 to the last available index


def test_handle_pygame_event_enter_selects_the_cursor_position() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)

    _press(scene, pygame.K_DOWN)
    _press(scene, pygame.K_RETURN)

    assert scene._pending_action_index == 1


def test_advance_query_resets_the_cursor_for_a_new_pending_query() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
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


def test_every_encounterable_strain_resolves_to_a_real_sprite_key() -> None:
    # _resolve_enemy_sprite_key falls back to SpriteKey.UNKNOWN on a name mismatch rather than
    # raising, so a live Strain with no matching SpriteKey would ship silently broken (a magenta
    # "missing texture" placeholder) instead of failing loudly -- this pins the naming contract
    # for every Strain that can actually reach the screen.
    for strain in ENCOUNTERABLE_STRAINS:
        assert _resolve_enemy_sprite_key(strain.name) is not SpriteKey.UNKNOWN


def test_update_resolves_automatic_phases_without_input() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())

    scene.update(0.016)

    assert scene._battle.turn_phase is TurnPhase.AWAITING_PLAYER_ACTION


def test_win_finishes_the_battle_and_reports_a_bare_battle_concluded() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=overwhelming)
    encounter = _encounter(generation)
    scene = CombatScene(generation, encounter, build_placeholder_atlas())

    transition = _drive_to_transition(scene)

    assert transition == BattleConcluded()
    assert generation.died is False
    assert generation.spores_gained == BESTIARY[encounter.strain].spore_award


def test_loss_finishes_the_battle_and_reports_a_bare_battle_concluded() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = Character(current_hp=5, max_hp=5)
    generation = _generation(stats=fragile, character=character)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())

    transition = _drive_to_transition(scene)

    assert transition == BattleConcluded()
    assert generation.died is True


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)  # reach AWAITING_PLAYER_ACTION so the action menu also renders

    scene.draw(pygame.Surface(surface_size))


def test_draw_anchors_the_player_left_and_the_enemy_right() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    surface = pygame.Surface((800, 600))
    surface.fill("black")

    scene.draw(surface)

    player_sprite = scene._atlas.get(SpriteKey.PLAYER)
    enemy_sprite = scene._atlas.get(scene._enemy_sprite_key)
    # Both sprites are non-empty placeholder shapes drawn on a black background, so scanning each
    # column for any non-black pixel locates where each panel actually rendered without hardcoding
    # every sub-widget's position. Restricted to the sprite panels' own vertical band so the
    # bottom-anchored menu/log (which always render near the left edge) can't mask a regression.
    black = pygame.Color("black")
    panel_band = range(_MARGIN, _MARGIN + max(player_sprite.get_height(), enemy_sprite.get_height()))
    non_black_columns = [
        x for x in range(surface.get_width()) if any(surface.get_at((x, y)) != black for y in panel_band)
    ]
    assert non_black_columns, "expected the combat scene to draw something"
    assert min(non_black_columns) < player_sprite.get_width() + _MARGIN
    assert max(non_black_columns) > surface.get_width() - enemy_sprite.get_width() - _MARGIN


def test_draw_keeps_the_enemys_buff_icon_row_from_overflowing_the_surface() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    # Short-labelled effects, so the assertion below exercises the row's positioning rather than
    # a pre-existing, orthogonal limitation where a long label (e.g. "Clouded Judgement") can
    # itself render wider than one _BUFF_ICON_STEP.
    for effect in (EffectName.RUNT, EffectName.WILTY, EffectName.FIBROUS):
        scene._battle.enemy.effects.apply(ActiveEffect(effect, EffectCategory.BATTLE, 5))
    surface = pygame.Surface((800, 600))
    surface.fill("black")

    scene.draw(surface)

    enemy_sprite = scene._atlas.get(scene._enemy_sprite_key)
    sprite_x = surface.get_width() - _MARGIN - enemy_sprite.get_width()
    icon_row_top = _MARGIN + _FONT_SIZE + _BAR_HEIGHT + _METER_HEIGHT + _GAP * 2
    # A generous band around the icon row's y-position, well clear of the menu/log which anchor
    # to the bottom of the surface -- isolates the icon row from the sprite/bars drawn above it.
    icon_band = range(icon_row_top, icon_row_top + _FONT_SIZE * 2)
    black = pygame.Color("black")
    icon_columns = [x for x in range(surface.get_width()) if any(surface.get_at((x, y)) != black for y in icon_band)]

    assert icon_columns, "expected the enemy's buff icons to render"
    # The mirrored row anchors flush against the sprite instead of growing rightward past it --
    # a small margin covers anti-aliased glyph edges, not a full icon-step's worth of drift.
    assert max(icon_columns) < sprite_x + _GAP + 20


def test_phases_for_is_exhaustive_and_stubbed_to_empty_for_every_variant() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())

    for event in _ONE_OF_EACH_BATTLE_EVENT:
        assert scene._phases_for(event) == []


def test_advance_phases_blocks_a_real_duration_phase_across_calls() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    starts: list[int] = []
    completions: list[int] = []
    first = Phase(duration_seconds=0.5, on_start=lambda: starts.append(1), on_complete=lambda: completions.append(1))
    second = Phase(duration_seconds=0.5, on_start=lambda: starts.append(2), on_complete=lambda: completions.append(2))
    scene._current_phases = deque([first, second])
    scene._pending_events.clear()

    scene._advance_phases(0.3)
    assert starts == [1]
    assert completions == []

    scene._advance_phases(0.3)
    # The second phase starts the instant the first completes, within this same call -- but does
    # not itself complete yet, since only leftover (zeroed) time was available to it this call.
    assert starts == [1, 2]
    assert completions == [1]

    # Regression check for the exact bug class this driver design exists to make impossible: a
    # later, separate call must not re-fire on_start for a phase already in progress, even though
    # `_phase_elapsed` was left at exactly 0.0 by the call above.
    scene._advance_phases(0.5)
    assert starts == [1, 2]
    assert completions == [1, 2]


def test_advance_phases_does_not_carry_a_completed_phases_leftover_time_into_the_next() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    completions: list[int] = []
    first = Phase(duration_seconds=0.5, on_complete=lambda: completions.append(1))
    second = Phase(duration_seconds=0.2, on_complete=lambda: completions.append(2))
    scene._current_phases = deque([first, second])
    scene._pending_events.clear()

    scene._advance_phases(0.3)
    # This call's dt overshoots the first phase's remaining duration by 0.3s -- more than enough
    # to also finish the second phase (0.2s) if that leftover carried over instead of resetting.
    scene._advance_phases(0.5)

    assert completions == [1]


def test_advance_phases_cascades_zero_duration_phases_within_a_single_call() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    completions: list[int] = []
    scene._current_phases = deque(
        [
            Phase(duration_seconds=0.0, on_complete=lambda: completions.append(1)),
            Phase(duration_seconds=0.0, on_complete=lambda: completions.append(2)),
        ]
    )
    scene._pending_events.clear()

    scene._advance_phases(0.016)

    assert completions == [1, 2]
    assert not scene._current_phases


def test_update_starts_a_real_phase_exactly_once_across_two_frames() -> None:
    # Drives the actual production path (update() -> _queue_events -> _start_next_event ->
    # _phases_for), rather than injecting into _current_phases directly, so it also exercises the
    # gate on real domain-produced events, not just hand-built ones. A RESONANCE effect guarantees
    # battle.start() itself produces events for update()'s first call to pick up.
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    starts: list[BattleEvent] = []
    scene._phases_for = lambda event: [Phase(duration_seconds=1.0, on_start=lambda: starts.append(event))]  # type: ignore[method-assign]

    scene.update(0.016)
    assert len(starts) == 1
    assert scene._current_phases  # the long phase is still in progress
    turn_phase_before = scene._battle.turn_phase

    scene.update(0.016)

    assert len(starts) == 1  # on_start must not refire while the same phase is still in progress
    assert scene._battle.turn_phase == turn_phase_before  # confirms the next domain call was withheld


def test_update_withholds_the_next_domain_call_while_phases_are_pending() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    turn_phase_before = scene._battle.turn_phase
    scene._current_phases = deque([Phase(duration_seconds=1.0)])

    result = scene.update(0.016)

    assert result is None
    assert scene._battle.turn_phase == turn_phase_before
    assert scene._pending_query is None


def test_update_withholds_battle_concluded_while_phases_are_pending() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene._battle.enemy.current_hp = 0  # forces is_over True without going through _conclude()
    scene._current_phases = deque([Phase(duration_seconds=1.0)])

    result = scene.update(0.016)

    assert result is None


def test_handle_pygame_event_withholds_input_while_phases_are_pending() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene.update(0.016)  # reach AWAITING_PLAYER_ACTION with a pending query
    assert scene._pending_query is not None
    scene._current_phases = deque([Phase(duration_seconds=1.0)])

    _press(scene, ACTION_KEYS[0])

    assert scene._pending_action_index is None


def test_log_records_every_event_unbounded_and_is_never_drawn() -> None:
    # _generation()'s default stats (not overwhelming) take the fight several rounds, producing
    # more events than any small display-oriented cap could plausibly hold.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())

    _drive_to_transition(scene)

    assert len(scene._log) > 4  # log has no cap; a bounded log would fail this
    assert not hasattr(scene, "_draw_log")
    scene.draw(pygame.Surface((800, 600)))  # must not raise now that draw() has no log panel
