import json
from collections import deque
from collections.abc import Sequence
from pathlib import Path

import pygame
import pygame.typing
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
from eye.exploration.encounters import ENCOUNTERABLE_STRAINS, EncounterKind, Strain
from eye.exploration.events import EnemyEncountered
from eye.gui.assets import SpriteKey, build_art_atlas, build_placeholder_atlas
from eye.gui.play_scene import BattleConcluded, PlaySceneTransition
from eye.gui.scenes.combat import (
    _BAR_HEIGHT,
    _FONT_SIZE,
    _GAP,
    _MARGIN,
    _METER_HEIGHT,
    ACTION_KEYS,
    CombatAnimationState,
    CombatScene,
    DisplayedCombatantState,
    Phase,
    _build_combat_animator,
    _DeadVariant,
    _hp_tween_phase,
    _LoadedCombatAnimationState,
    _resolve_enemy_sprite_key,
)
from eye.gui.tuning import BATTLE_DEATH_POSE_HOLD_SECONDS, BATTLE_VALUE_TWEEN_SECONDS
from eye.gui.widgets import BuffIcon, TextBuffIcon
from eye.session.generation import Generation
from tests.session.doubles import ScriptedEncounterRandom

_STATS = Stats(max_hp=20, attack=5, defense=2, meter_capacity=100, meter_fill_rate=1)


def _write_clip(directory: Path, name: str, frame_count: int = 2, frame_size: int = 4, fps: float = 8) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pygame.image.save(pygame.Surface((frame_size * frame_count, frame_size)), directory / f"{name}.png")
    manifest = {"frame_width": frame_size, "frame_height": frame_size, "frame_count": frame_count, "fps": fps}
    (directory / f"{name}.json").write_text(json.dumps(manifest))


def _write_dead_variant(directory: Path, size: int = 4) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    pygame.image.save(pygame.Surface((size, size)), directory / "dead.png")


def _write_full_combat_sprite_set(directory: Path, *, attack_fps: float = 8, hit_fps: float = 8) -> None:
    _write_clip(directory, "idle", frame_count=2, fps=8)
    _write_clip(directory, "attack", frame_count=2, fps=attack_fps)
    _write_clip(directory, "hit", frame_count=2, fps=hit_fps)
    _write_dead_variant(directory)


def _combatant(name: str = "Combatant") -> Combatant:
    return Combatant(name=name, base_stats=_STATS, current_hp=_STATS.max_hp)


# One instance of every BattleEvent variant -- used to check that `_phases_for` is exhaustive.
# Death/Revive/HitLanded/HitReflected/SelfDamageTaken are the animation-driven swing events and
# return real phases; every other variant stays stubbed to `[]` pending ADR 0013's remaining
# Announcement/Tween/Overlay treatments.
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


def _generation(
    stats: Stats = _STATS, character: Character | None = None, strain_queue: Sequence[Strain] = ()
) -> Generation:
    return Generation(
        character=character or Character(current_hp=stats.max_hp, max_hp=stats.max_hp),
        stats=stats,
        actions=_ACTIONS,
        rng=ScriptedEncounterRandom([EncounterKind.ENEMY], strain_queue=strain_queue),
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

    # A generous budget: animation-driven swing/tween phases (ADR 0013) give HitLanded/
    # SelfDamageTaken real duration, so several update() calls are needed before the next query
    # can appear.
    for _ in range(200):
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


_ANIMATION_DRIVEN_EVENT_TYPES = (Death, Revive, HitLanded, HitReflected, SelfDamageTaken)


def test_phases_for_is_exhaustive_over_every_battle_event_variant() -> None:
    # No crash for any variant is the exhaustiveness check itself -- assert_never() would raise.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())

    for event in _ONE_OF_EACH_BATTLE_EVENT:
        scene._phases_for(event)


def test_phases_for_returns_empty_for_variants_not_yet_animated() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())

    for event in _ONE_OF_EACH_BATTLE_EVENT:
        if not isinstance(event, _ANIMATION_DRIVEN_EVENT_TYPES):
            assert scene._phases_for(event) == []


def test_phases_for_returns_real_phases_for_every_animation_driven_swing_event() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())

    for event in _ONE_OF_EACH_BATTLE_EVENT:
        if isinstance(event, _ANIMATION_DRIVEN_EVENT_TYPES):
            assert scene._phases_for(event) != []


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


def test_build_combat_animator_returns_none_for_a_key_with_no_animation_clips() -> None:
    assert _build_combat_animator(build_placeholder_atlas(), SpriteKey.BEATLE) is None


def test_build_combat_animator_builds_the_full_four_state_clip_set(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value)
    atlas = build_art_atlas(tmp_path)

    animator = _build_combat_animator(atlas, SpriteKey.BEATLE)

    assert animator is not None
    for state in CombatAnimationState:
        animator.set_state(state)
        assert isinstance(animator.current_frame(), pygame.Surface)


def test_build_combat_animator_forces_loop_false_on_the_attack_and_hit_clips(tmp_path: Path) -> None:
    # build_art_atlas itself only sets loop=True defaults -- _build_combat_animator must override
    # it, or a swing phase's animation would keep cycling forever once its bounded duration ends.
    # A 2-frame, fps=8 clip advanced by dt=1000.0 (8000 frame-durations, an even multiple) lands
    # back on frame 0 if it loops -- only loop=False freezes it on the clip's *last* frame instead,
    # so asserting against frames[-1] (not just "some frame that stopped changing") is what
    # actually distinguishes the two rather than passing for either.
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value)
    atlas = build_art_atlas(tmp_path)
    loaded = atlas.get_animation_set(SpriteKey.BEATLE, _LoadedCombatAnimationState)
    animator = _build_combat_animator(atlas, SpriteKey.BEATLE)
    assert animator is not None

    for loaded_state, combat_state in (
        (_LoadedCombatAnimationState.ATTACK, CombatAnimationState.ATTACK),
        (_LoadedCombatAnimationState.HIT, CombatAnimationState.HIT),
    ):
        animator.set_state(combat_state)
        animator.update(1000.0)
        assert animator.current_frame() is loaded[loaded_state].frames[-1]


def test_build_combat_animator_dead_state_resolves_to_the_static_variant(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value)
    atlas = build_art_atlas(tmp_path)
    animator = _build_combat_animator(atlas, SpriteKey.BEATLE)
    assert animator is not None
    dead_surface = atlas.get_variant_set(SpriteKey.BEATLE, _DeadVariant)[_DeadVariant.DEAD]

    animator.set_state(CombatAnimationState.DEAD)

    assert animator.current_frame() is dead_surface


def test_build_combat_animator_raises_when_the_dead_variant_is_missing(tmp_path: Path) -> None:
    directory = tmp_path / SpriteKey.BEATLE.value
    _write_clip(directory, "idle")
    _write_clip(directory, "attack")
    _write_clip(directory, "hit")
    atlas = build_art_atlas(tmp_path)

    with pytest.raises(ValueError, match=r"variants.*DEAD"):
        _build_combat_animator(atlas, SpriteKey.BEATLE)


def test_displayed_state_is_seeded_before_battle_starts_own_events_are_revealed() -> None:
    # Mirrors test_construction_starts_the_battle_and_prefills_the_resonance_meter's setup: a
    # Resonance effect makes battle.start() mutate current_meter immediately on construction.
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())

    assert scene._battle.player.current_meter > 0  # start() already mutated live Combatant state
    assert scene._player_displayed.meter == 0  # but the seeded snapshot predates that mutation


def test_death_phase_holds_for_the_tuned_duration_and_sets_the_dead_state(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)
    atlas = build_art_atlas(tmp_path)
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), atlas)
    dead_surface = atlas.get_variant_set(SpriteKey.PLAYER, _DeadVariant)[_DeadVariant.DEAD]

    phases = scene._phases_for(Death(combatant=scene._battle.player))

    assert len(phases) == 1
    assert phases[0].duration_seconds == BATTLE_DEATH_POSE_HOLD_SECONDS
    phases[0].on_start()
    assert scene._player_animator is not None
    assert scene._player_animator.current_frame() is dead_surface


def test_death_phase_defensively_snaps_hp_with_no_preceding_tween() -> None:
    # A Wilty-triggered death sets current_hp directly with no preceding damage event at all --
    # Death's on_start must not assume some earlier phase already tweened displayed.hp to match.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene._battle.player.current_hp = 0
    assert scene._player_displayed.hp != 0  # still the untouched construction-time snapshot

    scene._phases_for(Death(combatant=scene._battle.player))[0].on_start()

    assert scene._player_displayed.hp == 0.0


def _hit_landed(scene: CombatScene) -> HitLanded:
    return HitLanded(
        source=scene._battle.player,
        target=scene._battle.enemy,
        action=ActionKind.STRUGGLE,
        hit_index=0,
        hit_count=1,
        damage=5,
        target_hp_after=scene._battle.enemy.current_hp - 5,
    )


def test_hit_landed_phase_duration_is_the_targets_clip_when_it_is_slower(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value, attack_fps=8)  # 2/8 = 0.25s
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value, hit_fps=2)  # 2/2 = 1.0s
    atlas = build_art_atlas(tmp_path)
    generation = _generation(strain_queue=[Strain.BEATLE])
    scene = CombatScene(generation, _encounter(generation), atlas)

    phases = scene._phases_for(_hit_landed(scene))

    assert phases[0].duration_seconds == pytest.approx(1.0)


def test_hit_landed_phase_duration_is_the_sources_clip_when_it_is_slower(tmp_path: Path) -> None:
    # The companion to the test above, with the slower clip on the opposite side -- together they
    # rule out an implementation that just always returns one side's duration.
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value, attack_fps=2)  # 2/2 = 1.0s
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value, hit_fps=8)  # 2/8 = 0.25s
    atlas = build_art_atlas(tmp_path)
    generation = _generation(strain_queue=[Strain.BEATLE])
    scene = CombatScene(generation, _encounter(generation), atlas)

    phases = scene._phases_for(_hit_landed(scene))

    assert phases[0].duration_seconds == pytest.approx(1.0)


def test_swing_phase_drives_source_attack_and_target_hit_then_resets_both_to_idle(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value)
    atlas = build_art_atlas(tmp_path)
    player_clips = atlas.get_animation_set(SpriteKey.PLAYER, _LoadedCombatAnimationState)
    enemy_clips = atlas.get_animation_set(SpriteKey.BEATLE, _LoadedCombatAnimationState)
    generation = _generation(strain_queue=[Strain.BEATLE])
    scene = CombatScene(generation, _encounter(generation), atlas)
    assert scene._player_animator is not None
    assert scene._enemy_animator is not None

    swing = scene._phases_for(_hit_landed(scene))[0]
    swing.on_start()
    assert scene._player_animator.current_frame() is player_clips[_LoadedCombatAnimationState.ATTACK].frames[0]
    assert scene._enemy_animator.current_frame() is enemy_clips[_LoadedCombatAnimationState.HIT].frames[0]

    swing.on_complete()
    assert scene._player_animator.current_frame() is player_clips[_LoadedCombatAnimationState.IDLE].frames[0]
    assert scene._enemy_animator.current_frame() is enemy_clips[_LoadedCombatAnimationState.IDLE].frames[0]


def test_reaction_phase_drives_hit_then_resets_to_idle(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)
    atlas = build_art_atlas(tmp_path)
    player_clips = atlas.get_animation_set(SpriteKey.PLAYER, _LoadedCombatAnimationState)
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), atlas)
    assert scene._player_animator is not None

    reaction = scene._reaction_phase(scene._battle.player)
    reaction.on_start()
    assert scene._player_animator.current_frame() is player_clips[_LoadedCombatAnimationState.HIT].frames[0]

    reaction.on_complete()
    assert scene._player_animator.current_frame() is player_clips[_LoadedCombatAnimationState.IDLE].frames[0]


def test_advance_phases_leaves_displayed_hp_strictly_between_before_and_after_mid_tween() -> None:
    # The central claim of ADR 0013: DisplayedCombatantState reflects only fully-completed phases,
    # never the live Combatant -- which Battle has, per its own contract, already fully resolved
    # by the time any of its events reach the GUI.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    pre_hit_hp = scene._enemy_displayed.hp
    target_hp_after = round(pre_hit_hp) - 5
    event = HitLanded(
        source=scene._battle.player,
        target=scene._battle.enemy,
        action=ActionKind.STRUGGLE,
        hit_index=0,
        hit_count=1,
        damage=5,
        target_hp_after=target_hp_after,
    )
    scene._battle.enemy.current_hp = target_hp_after  # Battle has already resolved this hit

    scene._queue_events([event])
    scene._advance_phases(0.0)  # cascades the zero-duration swing phase (no animator), starts the tween
    assert scene._enemy_displayed.hp == pre_hit_hp  # tween hasn't progressed yet

    scene._advance_phases(BATTLE_VALUE_TWEEN_SECONDS / 2)

    assert target_hp_after < scene._enemy_displayed.hp < pre_hit_hp
    assert scene._battle.enemy.current_hp == target_hp_after  # live state was already fully resolved


def test_hp_tween_phase_interpolates_and_snaps_exactly_on_completion() -> None:
    displayed = DisplayedCombatantState(hp=100.0, meter=0.0)
    phase = _hp_tween_phase(displayed, 60)

    phase.on_progress(0.5)
    assert displayed.hp == pytest.approx(80.0)

    phase.on_complete()
    assert displayed.hp == 60.0


def test_buff_icons_still_read_live_combatant_state_not_the_displayed_snapshot() -> None:
    # The buff row deliberately reads live Combatant state, not the DisplayedCombatantState
    # snapshot -- see combat.py's _draw_combatant comment for why. Recording which EffectName
    # values actually get rendered (rather than only inspecting the snapshot, which no drawing
    # code reads) is what makes this catch a regression to reading the snapshot instead.
    rendered: list[EffectName] = []

    def _spy_factory(effect: EffectName) -> BuffIcon:
        rendered.append(effect)
        return TextBuffIcon(effect)

    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), buff_icon_factory=_spy_factory)
    scene._battle.player.effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.BATTLE, 3))

    scene.draw(pygame.Surface((800, 600)))

    assert EffectName.FIBROUS in rendered


def test_meter_bar_still_reads_live_combatant_state_not_the_displayed_snapshot() -> None:
    # Same reasoning as the buff-icon test above: MeterFilled/MeterConsumed are still phase-less,
    # so the meter bar would otherwise be frozen at its construction-time snapshot for the whole
    # battle. Recording the actual ratio _draw_bar is called with (rather than only inspecting the
    # snapshot) is what makes this catch a regression to reading it instead.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas())
    scene._battle.player.current_meter = 42
    assert scene._player_displayed.meter != 42  # snapshot never moved from its construction value
    ratios: list[float] = []
    original_draw_bar = scene._draw_bar

    def _spy_draw_bar(surface: pygame.Surface, rect: pygame.Rect, ratio: float, color: pygame.typing.ColorLike) -> None:
        ratios.append(ratio)
        original_draw_bar(surface, rect, ratio, color)

    scene._draw_bar = _spy_draw_bar  # type: ignore[method-assign]

    scene.draw(pygame.Surface((800, 600)))

    # Draw order per _draw_combatant: HP bar then meter bar, player side first.
    expected_ratio = 42 / scene._battle.player.base_stats.meter_capacity
    assert ratios[1] == pytest.approx(expected_ratio)
