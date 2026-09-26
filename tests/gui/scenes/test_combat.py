import json
import random
from collections import deque
from collections.abc import Mapping, Sequence
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
from eye.combat.tuning import ADRENALINE_REVIVE_HP, RESONANCE_METER_PREFILL_RATIO
from eye.exploration.encounters import ENCOUNTERABLE_STRAINS, EncounterKind, Strain
from eye.exploration.events import EnemyEncountered
from eye.gui.app import _WINDOW_SIZE
from eye.gui.assets import (
    PLACEHOLDER_SPRITE_SIZE,
    IconVariant,
    SpriteKey,
    build_art_atlas,
    build_placeholder_atlas,
)
from eye.gui.audio import SoundKey
from eye.gui.card import Card
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.narration import NarrationEntry, NarrationTrigger, NarrationTriggers
from eye.gui.play_scene import BattleConcluded, PlaySceneTransition
from eye.gui.scenes.combat import (
    _BAR_HEIGHT,
    _BAR_ICON_SIZE,
    _BAR_WIDTH,
    _BUFF_ICON_DURATION_FONT_SIZE,
    _BUFF_ICON_HOP_CEILING,
    _BUFF_ICON_SIZE,
    _COMBATANT_SCALE_FACTOR,
    _FONT_SIZE,
    _GAP,
    _HP_COLOR,
    _MARGIN,
    _METER_COLOR,
    _METER_HEIGHT,
    _OVERLAY_ICON_SIZE,
    _OVERLAY_LABEL_FONT_SIZE,
    _TEXT_COLOR,
    ACTION_KEYS,
    AnchoredCard,
    Announcement,
    CombatAnimationState,
    CombatantLayout,
    CombatScene,
    DisplayedCombatantState,
    HitFlash,
    HitValence,
    Overlay,
    Phase,
    PhaseFocus,
    _build_combat_animator,
    _combatant_layout,
    _DeadVariant,
    _describe_event,
    _dimmed,
    _hp_tween_phase,
    _label,
    _lit_by_hit_flash,
    _LoadedCombatAnimationState,
    _overlay_label_lines,
    _resolve_enemy_sprite_key,
    _turn_title,
    _valence_color,
)
from eye.gui.tuning import (
    BATTLE_ACTING_HIGHLIGHT_COLOR,
    BATTLE_ANNOUNCEMENT_HOLD_SECONDS,
    BATTLE_BUFF_ICON_HOP_DURATION_SECONDS,
    BATTLE_BUFF_ICON_HOP_PIXELS,
    BATTLE_DEATH_POSE_HOLD_SECONDS,
    BATTLE_HIGHLIGHT_PULSE_PERIOD_SECONDS,
    BATTLE_HIT_FLASH_DAMAGE_COLOR,
    BATTLE_HIT_FLASH_DURATION_SECONDS,
    BATTLE_HIT_FLASH_HEALING_COLOR,
    BATTLE_HIT_FLASH_STRENGTH,
    BATTLE_INACTIVE_COMBATANT_DIM_FACTOR,
    BATTLE_RECEIVING_HIGHLIGHT_COLOR,
    BATTLE_VALUE_TWEEN_SECONDS,
)
from eye.gui.widgets import (
    EFFECT_DESCRIPTIONS,
    BuffIcon,
    IconSource,
    NonEffectIcon,
    SpriteBuffIcon,
    SpriteIcon,
    TextBuffIcon,
)
from eye.session.generation import Generation
from tests.gui.doubles import build_fake_audio_manager as _audio
from tests.gui.doubles import build_spy_audio_manager
from tests.session.doubles import ScriptedEncounterRandom

_STATS = Stats(max_hp=20, attack=5, defense=2, meter_capacity=100, meter_fill_rate=1)
# A colour the scene never paints, so colorkeying it leaves exactly the drawn pixels behind.
_UNDRAWN: pygame.typing.ColorLike = "navy"


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
    EffectExpired(target=_combatant(), effect=EffectName.FIBROUS, category=EffectCategory.BATTLE),
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


class _AlwaysRolling(ScriptedEncounterRandom):
    """Every `Battle._roll()` succeeds; the scripted encounter and Strain draws are untouched."""

    def random(self) -> float:
        return 0.0


def _generation(
    stats: Stats = _STATS,
    character: Character | None = None,
    strain_queue: Sequence[Strain] = (),
    rng: random.Random | None = None,
) -> Generation:
    return Generation(
        character=character or Character(current_hp=stats.max_hp, max_hp=stats.max_hp),
        stats=stats,
        actions=_ACTIONS,
        rng=rng or ScriptedEncounterRandom([EncounterKind.ENEMY], strain_queue=strain_queue),
        starting_screen=0,
        matured_turfs=(),
    )


def _encounter(generation: Generation) -> EnemyEncountered:
    events = generation.advance()
    return next(event for event in events if isinstance(event, EnemyEncountered))


def _press(scene: CombatScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def _keep_background_black(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralizes `_draw_background` for tests written before it existed, which key off a plain
    black surface to isolate what the rest of `draw()` paints -- background rendering has its own
    dedicated test."""
    import eye.gui.scenes.combat as combat_module

    def _black_crop_to_cover(surface: pygame.Surface, target_size: tuple[int, int]) -> pygame.Surface:
        black = pygame.Surface(target_size)
        black.fill("black")
        return black

    monkeypatch.setattr(combat_module, "crop_to_cover", _black_crop_to_cover)


def _drive_to_transition(scene: CombatScene, max_frames: int = 2000) -> PlaySceneTransition:
    # Generous budget: beyond the animation-driven swing/tween phases (ADR 0013) already accounted
    # for here, EffectApplied/EffectExpired/TurnSkipped/ExtraActionTriggered/BattleEnded now each
    # hold for BATTLE_ANNOUNCEMENT_HOLD_SECONDS too, so a real strain that inflicts several
    # buffs/debuffs over a multi-round fight needs many more 0.016s frames to fully resolve.
    for _ in range(max_frames):
        _press(scene, ACTION_KEYS[0])
        result = scene.update(0.016)
        if result is not None:
            return result
    raise AssertionError("battle did not conclude within max_frames")


def _drive_to_next_player_query(scene: CombatScene, max_frames: int = 400) -> None:
    for _ in range(max_frames):
        while scene._narration.queue.is_active:
            scene._narration.queue.dismiss()
        scene.update(0.016)
        if scene._pending_query is not None:
            return
    raise AssertionError("did not reach the next player-action query")


def test_construction_starts_the_battle_and_prefills_the_resonance_meter() -> None:
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)
    encounter = _encounter(generation)

    scene = CombatScene(generation, encounter, build_placeholder_atlas(), audio=_audio())

    expected = round(_STATS.meter_capacity * RESONANCE_METER_PREFILL_RATIO)
    assert scene._battle.player.current_meter == expected


def test_construction_starts_non_boss_battle_music() -> None:
    generation = _generation(strain_queue=[Strain.BEATLE])
    encounter = _encounter(generation)
    spy = build_spy_audio_manager()

    CombatScene(generation, encounter, build_placeholder_atlas(), spy.manager)

    assert spy.battle_primary.played == [(spy.sounds[SoundKey.FIGHT_CUE_IN], 0, 0)]


@pytest.mark.parametrize("strain", [Strain.GOLEM, Strain.PHIDIZVIK])
def test_construction_starts_boss_battle_music_for_a_boss_strain(strain: Strain) -> None:
    generation = _generation(strain_queue=[strain])
    encounter = _encounter(generation)
    spy = build_spy_audio_manager()

    CombatScene(generation, encounter, build_placeholder_atlas(), spy.manager)

    assert spy.battle_primary.played == [(spy.sounds[SoundKey.BOSS_FIGHT_CUE_IN], 0, 0)]


def test_update_drives_the_battle_musics_cue_in_to_loop_handoff() -> None:
    generation = _generation(strain_queue=[Strain.BEATLE])
    encounter = _encounter(generation)
    spy = build_spy_audio_manager()
    scene = CombatScene(generation, encounter, build_placeholder_atlas(), spy.manager)
    spy.battle_primary.queued_sound = None  # simulate SDL_mixer moving the loop to "now playing"

    scene.update(0.016)

    assert spy.battle_primary.queue_calls[-1] == spy.sounds[SoundKey.FIGHT_LOOP]


def test_update_drives_the_cue_in_to_loop_handoff_even_while_narration_is_active() -> None:
    # Pins the ordering: audio.update(dt) runs above the narration-active early return, so the
    # handoff does not stall while an overlay holds the rest of the battle pipeline.
    generation = _generation(strain_queue=[Strain.BEATLE])
    encounter = _encounter(generation)
    spy = build_spy_audio_manager()
    scene = CombatScene(generation, encounter, build_placeholder_atlas(), spy.manager)
    scene._narration.fire(NarrationTrigger.FIRST_DEATH, "msg", "sub")
    assert scene._narration.queue.is_active is True
    spy.battle_primary.queued_sound = None
    queue_calls_before = len(spy.battle_primary.queue_calls)

    scene.update(0.016)

    # Checks the count grew, not just that the last entry still reads FIGHT_LOOP -- __init__'s own
    # start_battle_music() already queues FIGHT_LOOP once, so a same-looking-but-stale last entry
    # would pass even if update() never re-queued anything at all.
    assert len(spy.battle_primary.queue_calls) == queue_calls_before + 1
    assert spy.battle_primary.queue_calls[-1] == spy.sounds[SoundKey.FIGHT_LOOP]


def test_winning_resolves_battle_music_as_won() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=overwhelming, strain_queue=[Strain.BEATLE])
    encounter = _encounter(generation)
    spy = build_spy_audio_manager()
    scene = CombatScene(generation, encounter, build_placeholder_atlas(), spy.manager)

    _drive_to_transition(scene)

    assert spy.battle_result.played == [(spy.sounds[SoundKey.FIGHT_WON], 0, 1000)]


def test_losing_resolves_battle_music_as_lost() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=fragile, character=Character(current_hp=5, max_hp=5), strain_queue=[Strain.BEATLE])
    encounter = _encounter(generation)
    spy = build_spy_audio_manager()
    scene = CombatScene(generation, encounter, build_placeholder_atlas(), spy.manager)

    _drive_to_transition(scene)

    assert spy.battle_result.played == [(spy.sounds[SoundKey.FIGHT_LOST], 0, 1000)]


def test_a_draw_resolves_battle_music_as_lost() -> None:
    # A draw is not a win (ADR 0018), and it is the one outcome no full-battle test above can set
    # up reliably -- driven straight off the event instead, the same way the scene builds its
    # phases. Without this, `won=winner is not self._battle.enemy` plays the fanfare on a draw and
    # every other audio test stays green.
    generation = _generation(strain_queue=[Strain.BEATLE])
    encounter = _encounter(generation)
    spy = build_spy_audio_manager()
    scene = CombatScene(generation, encounter, build_placeholder_atlas(), spy.manager)

    scene._phases_for(BattleEnded(winner=None))[0].on_start()

    assert spy.battle_result.played == [(spy.sounds[SoundKey.FIGHT_LOST], 0, 1000)]


def test_battle_music_resolves_as_the_result_banner_appears_not_when_the_scene_concludes() -> None:
    # Resolving from _conclude() instead would land a full announcement hold (plus any death
    # pose) after "You win!" is already standing on screen.
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=overwhelming, strain_queue=[Strain.BEATLE])
    encounter = _encounter(generation)
    spy = build_spy_audio_manager()
    scene = CombatScene(generation, encounter, build_placeholder_atlas(), spy.manager)

    resolved_at: int | None = None
    concluded_at: int | None = None
    for frame in range(2000):
        _press(scene, ACTION_KEYS[0])
        transition = scene.update(0.016)
        if resolved_at is None and spy.battle_result.played:
            resolved_at = frame
        if isinstance(transition, BattleConcluded):
            concluded_at = frame
            break

    assert resolved_at is not None
    assert concluded_at is not None
    # Strictly earlier, not merely "by the time it concluded" -- resolving from _conclude() lands
    # both on the same frame and would satisfy the two win/loss tests above unchanged.
    assert resolved_at < concluded_at


def test_displayed_state_from_seeds_remaining_turns_as_none_for_a_preexisting_lifespan_effect() -> None:
    # A fresh Battle can only start with pre-existing Lifespan effects -- Battle-scoped ones are
    # only ever granted by events during this battle -- and Lifespan always displays blank, so the
    # seed is correct without reading the live effect's actual remaining_turns.
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)
    encounter = _encounter(generation)

    scene = CombatScene(generation, encounter, build_placeholder_atlas(), audio=_audio())

    key = (EffectCategory.LIFESPAN, EffectName.FIBROUS)
    assert key in scene._player_displayed.active_effects
    assert scene._player_displayed.remaining_turns[key] is None


def test_handle_pygame_event_ignores_non_keydown() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)  # advance to AWAITING_PLAYER_ACTION

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=ACTION_KEYS[0]))

    assert scene._pending_action_index is None


def test_handle_pygame_event_ignores_a_key_when_no_action_is_pending() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    _press(scene, ACTION_KEYS[0])  # no update() yet, so no PlayerTurnNeedsAction is pending

    assert scene._pending_action_index is None


def test_handle_pygame_event_ignores_an_index_beyond_the_available_actions() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)  # advance to AWAITING_PLAYER_ACTION with exactly two available actions

    _press(scene, ACTION_KEYS[2])

    assert scene._pending_action_index is None


def test_handle_pygame_event_accepts_a_valid_action_index() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)

    _press(scene, ACTION_KEYS[1])

    assert scene._pending_action_index == 1


def test_handle_pygame_event_moves_the_cursor_down_and_wraps() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)

    _press(scene, pygame.K_DOWN)
    assert scene._cursor_index == 1

    _press(scene, pygame.K_DOWN)
    assert scene._cursor_index == 0


def test_handle_pygame_event_moves_the_cursor_up_and_wraps() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)

    _press(scene, pygame.K_UP)

    assert scene._cursor_index == 1  # wraps from 0 to the last available index


def test_handle_pygame_event_enter_selects_the_cursor_position() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)

    _press(scene, pygame.K_DOWN)
    _press(scene, pygame.K_RETURN)

    assert scene._pending_action_index == 1


def test_advance_query_resets_the_cursor_for_a_new_pending_query() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)  # first AWAITING_PLAYER_ACTION query, cursor at 0
    _press(scene, pygame.K_DOWN)
    assert scene._cursor_index == 1
    _press(scene, pygame.K_RETURN)

    # A generous budget: animation-driven swing/tween phases (ADR 0013) give HitLanded/
    # SelfDamageTaken real duration, so several update() calls are needed before the next query
    # can appear.
    for _ in range(200):
        while scene._narration.queue.is_active:  # e.g. FIRST_ATTACK, on the player's first hit
            scene._narration.queue.dismiss()
        scene.update(0.016)
        if scene._pending_query is not None:
            break
    else:
        raise AssertionError("did not reach the next player-action query")

    assert scene._cursor_index == 0


def test_tick_displayed_battle_effect_durations_decrements_only_finite_battle_scoped_entries() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.remaining_turns = {
        (EffectCategory.BATTLE, EffectName.FIBROUS): 3,
        (EffectCategory.BATTLE, EffectName.ADRENALINE): None,  # until battle ends -- untouched
        (EffectCategory.LIFESPAN, EffectName.RESONANCE): None,  # Lifespan never ticks -- untouched
    }

    scene._tick_displayed_battle_effect_durations()

    assert scene._player_displayed.remaining_turns == {
        (EffectCategory.BATTLE, EffectName.FIBROUS): 2,
        (EffectCategory.BATTLE, EffectName.ADRENALINE): None,
        (EffectCategory.LIFESPAN, EffectName.RESONANCE): None,
    }


def test_resolve_enemy_turn_ticks_the_displayed_battle_effect_durations_by_one_per_round() -> None:
    # Battle._expire_battle_effects() -- the domain's own once-per-round tick -- is only ever
    # called from resolve_enemy_turn(), so this pins the one call site
    # _tick_displayed_battle_effect_durations must stay wired to (eye/gui/scenes/combat.py's
    # update()) to stay in sync with the domain's actual cadence.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    key = (EffectCategory.BATTLE, EffectName.FIBROUS)
    scene._player_displayed.remaining_turns[key] = 3
    scene.update(0.016)  # first AWAITING_PLAYER_ACTION query
    _press(scene, ACTION_KEYS[0])

    for _ in range(200):
        while scene._narration.queue.is_active:  # e.g. FIRST_ATTACK, on the player's first hit
            scene._narration.queue.dismiss()
        scene.update(0.016)
        if scene._pending_query is not None:
            break
    else:
        raise AssertionError("did not reach the next player-action query")

    assert scene._player_displayed.remaining_turns[key] == 2


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
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    scene.update(0.016)

    assert scene._battle.turn_phase is TurnPhase.AWAITING_PLAYER_ACTION


def test_win_finishes_the_battle_and_reports_a_bare_battle_concluded() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=overwhelming)
    encounter = _encounter(generation)
    scene = CombatScene(generation, encounter, build_placeholder_atlas(), audio=_audio())

    transition = _drive_to_transition(scene)

    assert transition == BattleConcluded()
    assert generation.died is False
    assert generation.spores_gained == BESTIARY[encounter.strain].spore_award


def test_loss_finishes_the_battle_and_reports_a_bare_battle_concluded() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = Character(current_hp=5, max_hp=5)
    generation = _generation(stats=fragile, character=character)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    transition = _drive_to_transition(scene)

    assert transition == BattleConcluded()
    assert generation.died is True


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)  # reach AWAITING_PLAYER_ACTION so the action menu also renders

    scene.draw(pygame.Surface(surface_size))


def test_draw_anchors_the_player_left_and_the_enemy_right(monkeypatch: pytest.MonkeyPatch) -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    surface = pygame.Surface((800, 600))
    surface.fill("black")
    _keep_background_black(monkeypatch)

    scene.draw(surface)

    player_sprite = scene._player_static_sprite
    enemy_sprite = scene._enemy_static_sprite
    # Placeholder sprites fill their bounding box, so the outermost non-black column is a panel's
    # edge. Banded to the sprites' own rows so the bottom-anchored menu/log can't mask a regression.
    black = pygame.Color("black")
    sprite_height = max(player_sprite.get_height(), enemy_sprite.get_height())
    sprite_top = surface.get_height() // 2 - sprite_height // 2
    panel_band = range(sprite_top, sprite_top + sprite_height)
    non_black_columns = [
        x for x in range(surface.get_width()) if any(surface.get_at((x, y)) != black for y in panel_band)
    ]
    assert non_black_columns, "expected the combat scene to draw something"
    player_x = surface.get_width() // 4 - player_sprite.get_width() // 2
    enemy_x = surface.get_width() // 4 * 3 - enemy_sprite.get_width() // 2
    assert min(non_black_columns) == player_x
    assert max(non_black_columns) == enemy_x + enemy_sprite.get_width() - 1


def test_draw_keeps_the_enemys_buff_icon_row_from_overflowing_the_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    # SpriteBuffIcon (the default factory) renders every icon at a fixed size regardless of the
    # effect's label, so these three aren't chosen for label width -- just to populate
    # DisplayedCombatantState (ADR 0013) directly rather than live Combatant.effects.
    for effect in (EffectName.RUNT, EffectName.WILTY, EffectName.FIBROUS):
        scene._enemy_displayed.active_effects.add((EffectCategory.BATTLE, effect))
    surface = pygame.Surface((800, 600))
    surface.fill("black")
    _keep_background_black(monkeypatch)

    scene.draw(surface)

    # The mirrored row anchors at bar_right, which is not where the enemy sprite sits.
    icon_row_x = _combatant_layout(surface, mirrored=True).bar_right
    icon_row_top = _MARGIN + _FONT_SIZE + _BAR_HEIGHT + _METER_HEIGHT + _GAP * 2
    # A generous band around the icon row's y-position, well clear of the menu/log which anchor
    # to the bottom of the surface -- isolates the icon row from the sprite/bars drawn above it.
    icon_band = range(icon_row_top, icon_row_top + _FONT_SIZE * 2)
    black = pygame.Color("black")
    icon_columns = [x for x in range(surface.get_width()) if any(surface.get_at((x, y)) != black for y in icon_band)]

    assert icon_columns, "expected the enemy's buff icons to render"
    assert max(icon_columns) < surface.get_width()
    # The mirrored row's own right edge lands exactly flush at icon_row_x -- deterministic since
    # SpriteBuffIcon blits a hard-edged sprite, not anti-aliased text.
    assert max(icon_columns) == icon_row_x - 1


def test_combatant_layout_hangs_a_mirrored_panel_off_the_opposite_edge() -> None:
    surface = pygame.Surface((800, 600))

    player = _combatant_layout(surface, mirrored=False)
    enemy = _combatant_layout(surface, mirrored=True)

    gutter = _BAR_ICON_SIZE + _GAP
    assert player == CombatantLayout(
        mirrored=False,
        sprite_center=(surface.get_width() // 4, surface.get_height() // 2),
        bar_left=_MARGIN + _GAP + gutter,
        bar_right=_MARGIN + _GAP + gutter + _BAR_WIDTH,
        bar_icon_left=_MARGIN + _GAP,
    )
    assert enemy == CombatantLayout(
        mirrored=True,
        sprite_center=(surface.get_width() // 4 * 3, surface.get_height() // 2),
        bar_left=surface.get_width() - _MARGIN - _GAP - gutter - _BAR_WIDTH,
        bar_right=surface.get_width() - _MARGIN - _GAP - gutter,
        bar_icon_left=surface.get_width() - _MARGIN - _GAP - _BAR_ICON_SIZE,
    )


def test_combatant_layout_centers_each_frame_on_the_sprite_anchor() -> None:
    layout = _combatant_layout(pygame.Surface((800, 600)), mirrored=False)

    assert layout.sprite_topleft(pygame.Surface((40, 30))) == (200 - 20, 300 - 15)
    assert layout.sprite_topleft(pygame.Surface((60, 30))) == (200 - 30, 300 - 15)


def _hud_bar_rects(layout: CombatantLayout) -> tuple[pygame.Rect, pygame.Rect]:
    hp_rect = pygame.Rect(layout.bar_left, _MARGIN + _FONT_SIZE, _BAR_WIDTH, _BAR_HEIGHT)
    return hp_rect, pygame.Rect(layout.bar_left, hp_rect.bottom + _GAP, _BAR_WIDTH, _METER_HEIGHT)


def _bar_icon_boxes(layout: CombatantLayout) -> tuple[pygame.Rect, pygame.Rect]:
    def centred_on(bar: pygame.Rect) -> pygame.Rect:
        top = bar.top + (bar.height - _BAR_ICON_SIZE) // 2
        return pygame.Rect(layout.bar_icon_left, top, _BAR_ICON_SIZE, _BAR_ICON_SIZE)

    hp_rect, meter_rect = _hud_bar_rects(layout)
    return centred_on(hp_rect), centred_on(meter_rect)


@pytest.mark.parametrize("mirrored", [False, True])
def test_each_bar_is_labelled_by_its_own_borderless_icon_scaled_into_the_gutter_box(mirrored: bool) -> None:
    # The real art, not a fixture: build_placeholder_atlas() is 32x32 for every key and the
    # tmp_path helpers write 4x4, so only a 210x210 source can catch an unscaled blit.
    atlas = build_art_atlas(Path("eye/gui/sprites"))
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)
    layout = _combatant_layout(surface, mirrored=mirrored)

    scene._draw_combatant(
        surface,
        scene._battle.enemy if mirrored else scene._battle.player,
        scene._enemy_displayed if mirrored else scene._player_displayed,
        layout,
    )

    for key, box in zip((SpriteKey.ICON_HEALTH, SpriteKey.EFFECT_RESONANCE), _bar_icon_boxes(layout), strict=True):
        expected = pygame.Surface(_WINDOW_SIZE)
        expected.fill(_UNDRAWN)
        SpriteIcon(atlas, key, IconVariant.BORDERLESS).render(expected, pygame.Vector2(box.topleft), _BAR_ICON_SIZE)

        assert pygame.image.tobytes(surface.subsurface(box), "RGBA") == pygame.image.tobytes(
            expected.subsurface(box), "RGBA"
        ), key


@pytest.mark.parametrize("mirrored", [False, True])
def test_the_bar_icons_stay_in_the_gutter_outboard_of_the_rest_of_the_panel(mirrored: bool) -> None:
    # An icon painted over a bar hides the fill exactly when the fill is short.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_art_atlas(Path("eye/gui/sprites")), audio=_audio())
    combatant = scene._battle.enemy if mirrored else scene._battle.player
    displayed = scene._enemy_displayed if mirrored else scene._player_displayed
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)
    layout = _combatant_layout(surface, mirrored=mirrored)
    hp_rect, meter_rect = _hud_bar_rects(layout)
    hp_box, meter_box = _bar_icon_boxes(layout)

    scene._draw_combatant(surface, combatant, displayed, layout)

    # The band outboard of the bars, down to the buff row: nothing but the bar icons is drawn here.
    icon_row_top = meter_rect.bottom + _GAP
    gutter = (
        pygame.Rect(layout.bar_right, 0, surface.get_width() - layout.bar_right, icon_row_top)
        if mirrored
        else pygame.Rect(0, 0, layout.bar_left, icon_row_top)
    )
    band = surface.subsurface(gutter)
    band.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only what was drawn
    drawn = band.get_bounding_rect().move(gutter.topleft)
    font = get_font(GameFont.ITHACA, _FONT_SIZE)
    hp_label = pygame.Rect(0, hp_rect.top, *font.size(f"{round(displayed.hp)}/{combatant.base_stats.max_hp}"))
    if mirrored:
        hp_label.right = hp_rect.left - _GAP
    else:
        hp_label.left = hp_rect.right + _GAP
    # The row's whole allowance, hop headroom included.
    buff_row = pygame.Rect(
        layout.bar_left,
        icon_row_top - _BUFF_ICON_HOP_CEILING,
        _BAR_WIDTH,
        _BUFF_ICON_SIZE + _BUFF_ICON_HOP_CEILING,
    )

    assert drawn.size != (0, 0)  # an empty rect is inside everything, and would prove nothing
    assert hp_box.union(meter_box).contains(drawn)
    assert surface.get_rect().contains(drawn)
    for box in (hp_box, meter_box):
        assert surface.get_rect().contains(box)
        assert not box.colliderect(hp_rect)
        assert not box.colliderect(meter_rect)
        assert not box.colliderect(hp_label)
        assert not box.colliderect(buff_row)
        outboard_of_the_bars = box.left >= layout.bar_right if mirrored else box.right <= layout.bar_left
        assert outboard_of_the_bars


_ANIMATION_DRIVEN_EVENT_TYPES = (Death, Revive, HitLanded)
_TWEEN_ONLY_EVENT_TYPES = (MeterFilled, MeterConsumed)
_ANNOUNCEMENT_EVENT_TYPES = (EffectApplied, EffectExpired, TurnSkipped, ExtraActionTriggered, BattleEnded)
_OVERLAY_EVENT_TYPES = (DotTicked, HealApplied, HitReflected, SelfDamageTaken)
_EVENT_TYPES_WITH_REAL_PHASES = (
    _ANIMATION_DRIVEN_EVENT_TYPES + _TWEEN_ONLY_EVENT_TYPES + _ANNOUNCEMENT_EVENT_TYPES + _OVERLAY_EVENT_TYPES
)


def test_phases_for_is_exhaustive_over_every_battle_event_variant() -> None:
    # No crash for any variant is the exhaustiveness check itself -- assert_never() would raise.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    for event in _ONE_OF_EACH_BATTLE_EVENT:
        scene._phases_for(event)


def test_phases_for_returns_no_phases_only_for_action_chosen() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    phase_less = [event for event in _ONE_OF_EACH_BATTLE_EVENT if scene._phases_for(event) == []]

    assert [type(event) for event in phase_less] == [ActionChosen]


def test_phases_for_returns_real_phases_for_every_animated_or_tweened_event() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    for event in _ONE_OF_EACH_BATTLE_EVENT:
        if isinstance(event, _EVENT_TYPES_WITH_REAL_PHASES):
            assert scene._phases_for(event) != []


def test_exactly_the_overlay_events_raise_an_overlay() -> None:
    # Keeps _OVERLAY_EVENT_TYPES honest: an event that gains or loses the treatment moves there too.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    raised: set[type[object]] = set()
    for event in _ONE_OF_EACH_BATTLE_EVENT:
        scene._overlay = None
        for phase in scene._phases_for(event):
            phase.on_start()
        if scene._overlay is not None:
            raised.add(type(event))

    assert raised == set(_OVERLAY_EVENT_TYPES)


def test_advance_phases_blocks_a_real_duration_phase_across_calls() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
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
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
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
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
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
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
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
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    turn_phase_before = scene._battle.turn_phase
    scene._current_phases = deque([Phase(duration_seconds=1.0)])

    result = scene.update(0.016)

    assert result is None
    assert scene._battle.turn_phase == turn_phase_before
    assert scene._pending_query is None


def test_update_withholds_battle_concluded_while_phases_are_pending() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._battle.enemy.current_hp = 0  # forces is_over True without going through _conclude()
    scene._current_phases = deque([Phase(duration_seconds=1.0)])

    result = scene.update(0.016)

    assert result is None


def test_handle_pygame_event_withholds_input_while_phases_are_pending() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)  # reach AWAITING_PLAYER_ACTION with a pending query
    assert scene._pending_query is not None
    scene._current_phases = deque([Phase(duration_seconds=1.0)])

    _press(scene, ACTION_KEYS[0])

    assert scene._pending_action_index is None


def test_log_records_every_event_unbounded_and_is_never_drawn() -> None:
    # _generation()'s default stats (not overwhelming) take the fight several rounds, producing
    # more events than any small display-oriented cap could plausibly hold.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    _drive_to_transition(scene)

    assert len(scene._log) > 4  # log has no cap; a bounded log would fail this
    assert not hasattr(scene, "_draw_log")
    scene.draw(pygame.Surface((800, 600)))  # must not raise now that draw() has no log panel


def test_build_combat_animator_returns_none_for_a_key_with_no_animation_clips() -> None:
    assert _build_combat_animator(build_placeholder_atlas(), SpriteKey.BEATLE) is None


def test_build_combat_animator_scales_every_frame_by_scale_factor(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value)  # 4x4 test clip frames
    atlas = build_art_atlas(tmp_path)

    animator = _build_combat_animator(atlas, SpriteKey.BEATLE, scale_factor=3)

    assert animator is not None
    for state in CombatAnimationState:
        animator.set_state(state)
        assert animator.current_frame().get_size() == (12, 12)


def test_combat_scene_scales_player_and_enemy_animators_by_combatant_scale_factor(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)  # 4x4 test clip frames
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value)
    atlas = build_art_atlas(tmp_path)
    generation = _generation(strain_queue=[Strain.BEATLE])

    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())

    assert scene._player_animator is not None
    assert scene._enemy_animator is not None
    frame_size = round(4 * _COMBATANT_SCALE_FACTOR)
    assert scene._player_animator.current_frame().get_size() == (frame_size, frame_size)
    assert scene._enemy_animator.current_frame().get_size() == (frame_size, frame_size)


def test_combat_scene_scales_static_fallback_sprites_by_combatant_scale_factor() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    assert scene._player_animator is None
    assert scene._enemy_animator is None

    sprite_size = round(PLACEHOLDER_SPRITE_SIZE * _COMBATANT_SCALE_FACTOR)
    assert scene._player_static_sprite.get_size() == (sprite_size, sprite_size)
    assert scene._enemy_static_sprite.get_size() == (sprite_size, sprite_size)


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
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    assert scene._battle.player.current_meter > 0  # start() already mutated live Combatant state
    assert scene._player_displayed.meter == 0  # but the seeded snapshot predates that mutation


def test_a_resonance_consumed_by_battle_start_clears_from_the_displayed_active_effects() -> None:
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    assert (EffectCategory.LIFESPAN, EffectName.RESONANCE) in scene._player_displayed.active_effects

    while scene._current_phases or scene._pending_events:
        scene._advance_phases(60.0)

    assert (EffectCategory.LIFESPAN, EffectName.RESONANCE) not in scene._player_displayed.active_effects


def test_a_lifespan_debuff_cleared_by_a_revive_clears_from_the_displayed_active_effects() -> None:
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.WILTY, EffectCategory.LIFESPAN, None))
    character.effects.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character, rng=_AlwaysRolling([EncounterKind.ENEMY]))
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    assert (EffectCategory.LIFESPAN, EffectName.WILTY) in scene._player_displayed.active_effects

    _drive_to_next_player_query(scene)
    while scene._current_phases or scene._pending_events:
        scene._advance_phases(60.0)

    assert scene._battle.player.current_hp == ADRENALINE_REVIVE_HP  # the Wilty roll killed and revived
    assert (EffectCategory.LIFESPAN, EffectName.WILTY) not in scene._player_displayed.active_effects


def test_death_phase_holds_for_the_tuned_duration_and_sets_the_dead_state(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)
    atlas = build_art_atlas(tmp_path)
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())

    phases = scene._phases_for(Death(combatant=scene._battle.player))

    assert len(phases) == 1
    assert phases[0].duration_seconds == BATTLE_DEATH_POSE_HOLD_SECONDS
    phases[0].on_start()
    assert scene._player_animator is not None
    assert scene._player_animator.state == CombatAnimationState.DEAD


def test_death_phase_duration_is_divided_by_the_combat_speed_multiplier() -> None:
    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), combat_speed_multiplier=2.0, audio=_audio()
    )

    phases = scene._phases_for(Death(combatant=scene._battle.player))

    assert phases[0].duration_seconds == BATTLE_DEATH_POSE_HOLD_SECONDS / 2.0


def test_death_phase_defensively_snaps_hp_with_no_preceding_tween() -> None:
    # A Wilty-triggered death sets current_hp directly with no preceding damage event at all --
    # Death's on_start must not assume some earlier phase already tweened displayed.hp to match.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
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


def test_hp_tween_phase_duration_is_divided_by_the_combat_speed_multiplier() -> None:
    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), combat_speed_multiplier=2.0, audio=_audio()
    )

    phases = scene._phases_for(_hit_landed(scene))

    assert phases[1].duration_seconds == BATTLE_VALUE_TWEEN_SECONDS / 2.0


def test_hit_landed_phase_duration_is_the_targets_clip_when_it_is_slower(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value, attack_fps=8)  # 2/8 = 0.25s
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value, hit_fps=2)  # 2/2 = 1.0s
    atlas = build_art_atlas(tmp_path)
    generation = _generation(strain_queue=[Strain.BEATLE])
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())

    phases = scene._phases_for(_hit_landed(scene))

    assert phases[0].duration_seconds == pytest.approx(1.0)


def test_hit_landed_phase_duration_is_the_sources_clip_when_it_is_slower(tmp_path: Path) -> None:
    # The companion to the test above, with the slower clip on the opposite side -- together they
    # rule out an implementation that just always returns one side's duration.
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value, attack_fps=2)  # 2/2 = 1.0s
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value, hit_fps=8)  # 2/8 = 0.25s
    atlas = build_art_atlas(tmp_path)
    generation = _generation(strain_queue=[Strain.BEATLE])
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())

    phases = scene._phases_for(_hit_landed(scene))

    assert phases[0].duration_seconds == pytest.approx(1.0)


def test_swing_phase_drives_source_attack_and_target_hit_then_resets_both_to_idle(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)
    _write_full_combat_sprite_set(tmp_path / SpriteKey.BEATLE.value)
    atlas = build_art_atlas(tmp_path)
    generation = _generation(strain_queue=[Strain.BEATLE])
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())
    assert scene._player_animator is not None
    assert scene._enemy_animator is not None

    swing = scene._phases_for(_hit_landed(scene))[0]
    swing.on_start()
    player_state: CombatAnimationState = scene._player_animator.state
    enemy_state: CombatAnimationState = scene._enemy_animator.state
    assert player_state == CombatAnimationState.ATTACK
    assert enemy_state == CombatAnimationState.HIT

    swing.on_complete()
    assert scene._player_animator.state == CombatAnimationState.IDLE
    assert scene._enemy_animator.state == CombatAnimationState.IDLE


def test_reaction_phase_drives_hit_then_resets_to_idle(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)
    atlas = build_art_atlas(tmp_path)
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())
    assert scene._player_animator is not None

    reaction = scene._reaction_phase(scene._battle.player, HitValence.DAMAGE)
    reaction.on_start()
    player_state: CombatAnimationState = scene._player_animator.state
    assert player_state == CombatAnimationState.HIT

    reaction.on_complete()
    assert scene._player_animator.state == CombatAnimationState.IDLE


def _dot_ticked(scene: CombatScene, damage: int = 3) -> DotTicked:
    return DotTicked(
        target=scene._battle.player,
        effect=EffectName.TOXICITY,
        damage=damage,
        target_hp_after=scene._battle.player.current_hp - damage,
    )


def test_overlay_phase_drives_the_targets_hit_state_then_resets_it_to_idle(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)
    atlas = build_art_atlas(tmp_path)
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())
    assert scene._player_animator is not None

    overlay_phase = scene._phases_for(_dot_ticked(scene))[0]
    overlay_phase.on_start()
    player_state: CombatAnimationState = scene._player_animator.state
    assert player_state == CombatAnimationState.HIT

    overlay_phase.on_complete()
    assert scene._player_animator.state == CombatAnimationState.IDLE


def test_overlay_phase_lasts_exactly_the_targets_own_hit_clip(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value, hit_fps=2)
    atlas = build_art_atlas(tmp_path)
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())

    phases = scene._phases_for(_dot_ticked(scene))

    assert phases[0].duration_seconds == pytest.approx(1.0)


def test_overlay_phase_shows_the_effect_at_the_target_on_start_and_clears_it_on_complete() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    phases = scene._phases_for(_dot_ticked(scene))
    assert scene._overlay is None

    phases[0].on_start()
    assert scene._overlay == Overlay(
        target=scene._battle.player,
        source=EffectName.TOXICITY,
        label="Toxicity",
        hp_delta=-3,
        valence=HitValence.DAMAGE,
    )

    phases[0].on_complete()
    assert scene._overlay is None


def test_dot_ticked_tweens_the_targets_displayed_hp_down_after_its_overlay() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    hp_before = scene._player_displayed.hp
    event = _dot_ticked(scene, damage=4)

    phases = scene._phases_for(event)

    assert len(phases) == 2
    assert phases[1].duration_seconds == BATTLE_VALUE_TWEEN_SECONDS
    phases[1].on_progress(0.5)
    assert event.target_hp_after < scene._player_displayed.hp < hp_before
    phases[1].on_complete()
    assert scene._player_displayed.hp == float(event.target_hp_after)


def test_heal_applied_tweens_the_targets_displayed_hp_up_after_its_overlay() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.hp = 5.0
    event = HealApplied(target=scene._battle.player, effect=EffectName.NOURISHED, amount=4, target_hp_after=9)

    phases = scene._phases_for(event)

    assert len(phases) == 2
    phases[0].on_start()
    assert scene._overlay == Overlay(
        target=scene._battle.player,
        source=EffectName.NOURISHED,
        label="Nourished",
        hp_delta=4,
        valence=HitValence.HEALING,
    )
    phases[1].on_progress(0.5)
    assert scene._player_displayed.hp == pytest.approx(7.0)
    phases[1].on_complete()
    assert scene._player_displayed.hp == 9.0


@pytest.mark.parametrize("mirrored", [False, True])
def test_draw_renders_the_overlay_icon_above_the_targets_own_sprite(mirrored: bool) -> None:
    render_calls: list[tuple[pygame.Vector2, int]] = []

    class _SpyIcon:
        def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
            render_calls.append((pos, size))

    def _spy_factory(source: IconSource) -> BuffIcon:
        return _SpyIcon()

    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), buff_icon_factory=_spy_factory, audio=_audio()
    )
    target = scene._battle.enemy if mirrored else scene._battle.player
    scene._overlay = Overlay(
        target=target, source=EffectName.TOXICITY, label="Toxicity", hp_delta=-2, valence=HitValence.DAMAGE
    )
    surface = pygame.Surface((800, 600))

    scene.draw(surface)

    layout = _combatant_layout(surface, mirrored=mirrored)
    sprite = scene._enemy_static_sprite if mirrored else scene._player_static_sprite
    font = get_font(GameFont.ITHACA, _OVERLAY_LABEL_FONT_SIZE)
    text_width = max(font.size(line)[0] for line in _overlay_label_lines(scene._overlay))
    block_width = _OVERLAY_ICON_SIZE + _GAP + text_width
    expected_pos = pygame.Vector2(
        layout.sprite_center[0] - block_width // 2,
        layout.sprite_topleft(sprite)[1] - _GAP - _OVERLAY_ICON_SIZE,
    )
    assert render_calls == [(expected_pos, _OVERLAY_ICON_SIZE)]
    # Target-local, not the Announcement's center-screen block (ADR 0013).
    assert expected_pos.x != surface.get_width() // 2 - block_width // 2


def _heal_applied(scene: CombatScene, amount: int = 2) -> HealApplied:
    return HealApplied(
        target=scene._battle.enemy,
        effect=EffectName.NOURISHED,
        amount=amount,
        target_hp_after=scene._battle.enemy.current_hp + amount,
    )


def test_overlay_carries_the_hp_its_event_moved_signed_by_direction() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    scene._phases_for(_dot_ticked(scene, damage=3))[0].on_start()
    assert scene._overlay == Overlay(
        target=scene._battle.player,
        source=EffectName.TOXICITY,
        label="Toxicity",
        hp_delta=-3,
        valence=HitValence.DAMAGE,
    )

    scene._phases_for(_heal_applied(scene, amount=2))[0].on_start()
    assert scene._overlay == Overlay(
        target=scene._battle.enemy,
        source=EffectName.NOURISHED,
        label="Nourished",
        hp_delta=2,
        valence=HitValence.HEALING,
    )


def test_the_overlay_label_reports_the_movement_a_capped_heal_actually_makes() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    player = scene._battle.player
    scene._player_displayed.hp = float(player.base_stats.max_hp - 1)
    event = HealApplied(target=player, effect=EffectName.NOURISHED, amount=3, target_hp_after=player.base_stats.max_hp)

    scene._phases_for(event)[0].on_start()

    assert scene._overlay is not None
    assert scene._overlay.hp_delta == 1
    assert _overlay_label_lines(scene._overlay)[1] == "+1 HP"


def test_the_overlay_label_reports_the_movement_an_overkill_tick_actually_makes() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.hp = 2.0
    event = DotTicked(target=scene._battle.player, effect=EffectName.TOXICITY, damage=5, target_hp_after=-3)

    scene._phases_for(event)[0].on_start()

    assert scene._overlay is not None
    assert scene._overlay.hp_delta == -2
    assert _overlay_label_lines(scene._overlay)[1] == "-2 HP"


def test_recoil_raises_a_recoil_overlay_on_the_combatant_that_dealt_it() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    player = scene._battle.player
    event = SelfDamageTaken(combatant=player, damage=4, combatant_hp_after=player.current_hp - 4)

    scene._phases_for(event)[0].on_start()

    assert scene._overlay == Overlay(
        target=player, source=NonEffectIcon.RECOIL, label="Recoil", hp_delta=-4, valence=HitValence.DAMAGE
    )
    assert scene._player_displayed.hit_flash is not None
    assert scene._player_displayed.hit_flash.valence is HitValence.DAMAGE


def test_a_lethal_recoil_reports_the_movement_its_bar_actually_makes() -> None:
    # Recoil is subtracted with no floor, as a DoT tick is, so a lethal one goes negative.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.hp = 3.0
    event = SelfDamageTaken(combatant=scene._battle.player, damage=6, combatant_hp_after=-3)

    scene._phases_for(event)[0].on_start()

    assert scene._overlay is not None
    assert scene._overlay.hp_delta == -3
    assert _overlay_label_lines(scene._overlay)[1] == "-3 HP"


def test_a_reflect_raises_its_overlay_on_the_attacker_and_not_on_the_spiky_skin_holder() -> None:
    # HitReflected.source is the Spiky Skin holder; .target is the attacker taking the damage back.
    # The overlay lands on .target, who does not wear the effect -- hence "Reflected" as the label.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    reflector, attacker = scene._battle.enemy, scene._battle.player
    event = HitReflected(source=reflector, target=attacker, damage=2, target_hp_after=attacker.current_hp - 2)

    scene._phases_for(event)[0].on_start()

    assert scene._overlay == Overlay(
        target=attacker, source=EffectName.SPIKY_SKIN, label="Reflected", hp_delta=-2, valence=HitValence.DAMAGE
    )
    # The flash follows the same side: the reflector gives the damage, it does not take it.
    assert scene._player_displayed.hit_flash is not None
    assert scene._player_displayed.hit_flash.valence is HitValence.DAMAGE
    assert scene._enemy_displayed.hit_flash is None


def test_a_lethal_reflect_reports_the_movement_its_bar_actually_makes() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.hp = 1.0
    event = HitReflected(source=scene._battle.enemy, target=scene._battle.player, damage=5, target_hp_after=-4)

    scene._phases_for(event)[0].on_start()

    assert scene._overlay is not None
    assert scene._overlay.hp_delta == -1
    assert _overlay_label_lines(scene._overlay)[1] == "-1 HP"


@pytest.mark.parametrize(
    ("source", "label", "hp_delta", "expected"),
    [
        (EffectName.TOXICITY, "Toxicity", -2, ("Toxicity", "-2 HP")),
        (EffectName.NOURISHED, "Nourished", 3, ("Nourished", "+3 HP")),
        # A label that is not its icon's own name: a reflect borrows Spiky Skin's art.
        (EffectName.SPIKY_SKIN, "Reflected", -5, ("Reflected", "-5 HP")),
    ],
)
def test_overlay_label_names_what_moved_the_bar_and_the_signed_hp(
    source: IconSource, label: str, hp_delta: int, expected: tuple[str, str]
) -> None:
    overlay = Overlay(target=_combatant(), source=source, label=label, hp_delta=hp_delta, valence=HitValence.DAMAGE)

    assert _overlay_label_lines(overlay) == expected


def test_the_default_icon_factory_resolves_a_source_with_no_effect_behind_it() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    assert isinstance(scene._buff_icon_factory(NonEffectIcon.RECOIL), SpriteBuffIcon)


def test_a_non_effect_overlay_icon_comes_from_the_scenes_own_factory_too() -> None:
    asked: list[IconSource] = []

    class _SilentIcon:
        def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
            return None

    def _spy_factory(source: IconSource) -> BuffIcon:
        asked.append(source)
        return _SilentIcon()

    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), buff_icon_factory=_spy_factory, audio=_audio()
    )
    scene._overlay = Overlay(
        target=scene._battle.player, source=NonEffectIcon.RECOIL, label="Recoil", hp_delta=-3, valence=HitValence.DAMAGE
    )
    surface = pygame.Surface((800, 600))

    scene._draw_overlay(surface, _combatant_layout(surface, mirrored=False), _combatant_layout(surface, mirrored=True))

    assert asked == [NonEffectIcon.RECOIL]


def test_draw_lays_the_overlay_label_beside_its_icon_vertically_centered_against_it() -> None:
    class _SilentIcon:
        def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
            return None

    generation = _generation()
    scene = CombatScene(
        generation,
        _encounter(generation),
        build_placeholder_atlas(),
        buff_icon_factory=lambda effect: _SilentIcon(),
        audio=_audio(),
    )
    scene._overlay = Overlay(
        target=scene._battle.player,
        source=EffectName.TOXICITY,
        label="Toxicity",
        hp_delta=-2,
        valence=HitValence.DAMAGE,
    )
    surface = pygame.Surface((800, 600))
    surface.fill(_UNDRAWN)

    scene._draw_overlay(surface, _combatant_layout(surface, mirrored=False), _combatant_layout(surface, mirrored=True))

    surface.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only the label
    drawn = surface.get_bounding_rect()
    layout = _combatant_layout(surface, mirrored=False)
    icon_top = layout.sprite_topleft(scene._player_static_sprite)[1] - _GAP - _OVERLAY_ICON_SIZE
    font = get_font(GameFont.ITHACA, _OVERLAY_LABEL_FONT_SIZE)
    text_width = max(font.size(line)[0] for line in _overlay_label_lines(scene._overlay))
    block_left = layout.sprite_center[0] - (_OVERLAY_ICON_SIZE + _GAP + text_width) // 2

    assert drawn.left == block_left + _OVERLAY_ICON_SIZE + _GAP
    icon_rows = pygame.Rect(drawn.left, icon_top, drawn.width, _OVERLAY_ICON_SIZE)
    assert icon_rows.contains(drawn)
    assert drawn.top - icon_top == pytest.approx(icon_rows.bottom - drawn.bottom, abs=1)


@pytest.mark.parametrize("effect", list(EffectName))
@pytest.mark.parametrize("mirrored", [False, True])
def test_every_overlay_block_clears_the_hud_panel_of_the_real_window(effect: EffectName, mirrored: bool) -> None:
    # The real art, not build_placeholder_atlas(): that is 32x32 for every key, so it would miss
    # the enemy's 64px frame, which is what leaves the overlay only a few pixels under the HUD.
    generation = _generation(strain_queue=[Strain.BEATLE])
    scene = CombatScene(generation, _encounter(generation), build_art_atlas(Path("eye/gui/sprites")), audio=_audio())
    target = scene._battle.enemy if mirrored else scene._battle.player
    scene._overlay = Overlay(
        target=target, source=effect, label=_label(effect), hp_delta=-99, valence=HitValence.DAMAGE
    )
    surface = pygame.Surface(_WINDOW_SIZE)
    # _UNDRAWN is not a colour the icon art paints, or the colourkey would key it back out.
    surface.fill(_UNDRAWN)

    scene._draw_overlay(surface, _combatant_layout(surface, mirrored=False), _combatant_layout(surface, mirrored=True))

    surface.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only what was drawn
    drawn = surface.get_bounding_rect()
    hud_bottom = _MARGIN + _FONT_SIZE + _BAR_HEIGHT + _GAP + _METER_HEIGHT + _GAP + _BUFF_ICON_SIZE

    assert drawn.size != (0, 0), effect  # an empty rect clears everything and proves nothing
    assert surface.get_rect().contains(drawn), effect
    assert drawn.top >= hud_bottom, effect


@pytest.mark.parametrize("strain", ENCOUNTERABLE_STRAINS)
def test_every_encounterable_strain_leaves_the_overlay_block_clear_of_the_hud(strain: Strain) -> None:
    # A future strain shipped with a taller frame should fail here, not quietly eat the clearance.
    generation = _generation(strain_queue=[strain])
    scene = CombatScene(generation, _encounter(generation), build_art_atlas(Path("eye/gui/sprites")), audio=_audio())
    scene._overlay = Overlay(
        target=scene._battle.enemy, source=EffectName.TOXICITY, label="Toxicity", hp_delta=-2, valence=HitValence.DAMAGE
    )
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)

    scene._draw_overlay(surface, _combatant_layout(surface, mirrored=False), _combatant_layout(surface, mirrored=True))

    surface.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only what was drawn
    drawn = surface.get_bounding_rect()
    hud_bottom = _MARGIN + _FONT_SIZE + _BAR_HEIGHT + _GAP + _METER_HEIGHT + _GAP + _BUFF_ICON_SIZE

    assert drawn.size != (0, 0), strain  # an empty rect clears everything and proves nothing
    assert drawn.top >= hud_bottom, strain


def test_a_dot_tick_hops_only_the_ticking_effects_icon_in_that_row() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.active_effects.update(
        {(EffectCategory.BATTLE, EffectName.TOXICITY), (EffectCategory.BATTLE, EffectName.FIBROUS)}
    )

    scene._phases_for(_dot_ticked(scene))[0].on_start()
    scene._elapsed_seconds += BATTLE_BUFF_ICON_HOP_DURATION_SECONDS / 2

    assert scene._buff_icon_hop_offset(scene._player_displayed, EffectName.TOXICITY) > 0
    assert scene._buff_icon_hop_offset(scene._player_displayed, EffectName.FIBROUS) == 0


def test_a_dot_tick_leaves_the_other_combatants_icon_of_the_same_effect_at_rest() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    for displayed in (scene._player_displayed, scene._enemy_displayed):
        displayed.active_effects.add((EffectCategory.BATTLE, EffectName.TOXICITY))

    scene._phases_for(_dot_ticked(scene))[0].on_start()
    scene._elapsed_seconds += BATTLE_BUFF_ICON_HOP_DURATION_SECONDS / 2

    assert scene._buff_icon_hop_offset(scene._player_displayed, EffectName.TOXICITY) > 0
    assert scene._buff_icon_hop_offset(scene._enemy_displayed, EffectName.TOXICITY) == 0


def test_a_heal_hops_the_healing_effects_icon_on_the_combatant_it_heals() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._enemy_displayed.active_effects.add((EffectCategory.BATTLE, EffectName.NOURISHED))

    scene._phases_for(_heal_applied(scene))[0].on_start()
    scene._elapsed_seconds += BATTLE_BUFF_ICON_HOP_DURATION_SECONDS / 2

    assert scene._buff_icon_hop_offset(scene._enemy_displayed, EffectName.NOURISHED) > 0
    assert scene._buff_icon_hop_offset(scene._player_displayed, EffectName.NOURISHED) == 0


def test_a_reflect_leaves_the_victims_own_spiky_skin_icon_at_rest() -> None:
    # A reflect's damage is credited to the *other* side's Spiky Skin, and both can wear it at once
    # (PROJECT_BRIEF.md 5.6), so the victim's own copy did nothing here and must not hop.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    attacker = scene._battle.player
    scene._player_displayed.active_effects.add((EffectCategory.BATTLE, EffectName.SPIKY_SKIN))
    event = HitReflected(source=scene._battle.enemy, target=attacker, damage=2, target_hp_after=attacker.current_hp - 2)

    scene._phases_for(event)[0].on_start()
    scene._elapsed_seconds += BATTLE_BUFF_ICON_HOP_DURATION_SECONDS / 2

    assert scene._overlay is not None
    assert scene._overlay.source is EffectName.SPIKY_SKIN  # the overlay really does name that icon
    assert scene._buff_icon_hop_offset(scene._player_displayed, EffectName.SPIKY_SKIN) == 0


def test_the_icon_hop_leaves_the_row_and_settles_back_within_its_own_duration() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    displayed = scene._player_displayed
    # The hop moves this combatant's own row entry, so the tick's effect has to be in it.
    displayed.active_effects.add((EffectCategory.BATTLE, EffectName.TOXICITY))
    assert scene._buff_icon_hop_offset(displayed, EffectName.TOXICITY) == 0  # at rest before the tick

    phase = scene._phases_for(_dot_ticked(scene))[0]
    phase.on_start()
    assert scene._buff_icon_hop_offset(displayed, EffectName.TOXICITY) == 0  # the arc starts on the ground

    scene._elapsed_seconds += BATTLE_BUFF_ICON_HOP_DURATION_SECONDS / 2
    assert scene._buff_icon_hop_offset(displayed, EffectName.TOXICITY) == min(
        BATTLE_BUFF_ICON_HOP_PIXELS, _BUFF_ICON_HOP_CEILING
    )

    scene._elapsed_seconds += BATTLE_BUFF_ICON_HOP_DURATION_SECONDS / 2
    assert scene._buff_icon_hop_offset(displayed, EffectName.TOXICITY) == 0

    phase.on_complete()
    assert EffectName.TOXICITY not in displayed.effect_tick_started_at


def test_draw_lifts_the_hopping_icon_and_leaves_its_neighbour_where_it_was() -> None:
    row_renders: list[tuple[EffectName, pygame.Vector2]] = []

    class _SpyIcon:
        def __init__(self, effect: EffectName) -> None:
            self.effect = effect

        def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
            # The overlay above the sprite renders through this same factory at its own size.
            if size == _BUFF_ICON_SIZE:
                row_renders.append((self.effect, pygame.Vector2(pos)))

    def _spy_factory(source: IconSource) -> BuffIcon:
        assert isinstance(source, EffectName)  # nothing under test here names a non-effect icon
        return _SpyIcon(source)

    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), buff_icon_factory=_spy_factory, audio=_audio()
    )
    scene._player_displayed.active_effects.update(
        {(EffectCategory.BATTLE, EffectName.TOXICITY), (EffectCategory.BATTLE, EffectName.FIBROUS)}
    )
    surface = pygame.Surface((800, 600))
    scene.draw(surface)
    at_rest = dict(row_renders)
    row_renders.clear()

    scene._phases_for(_dot_ticked(scene))[0].on_start()
    scene._elapsed_seconds += BATTLE_BUFF_ICON_HOP_DURATION_SECONDS / 2
    scene.draw(surface)
    mid_hop = dict(row_renders)

    assert mid_hop[EffectName.TOXICITY].x == at_rest[EffectName.TOXICITY].x
    assert mid_hop[EffectName.TOXICITY].y < at_rest[EffectName.TOXICITY].y
    assert mid_hop[EffectName.FIBROUS] == at_rest[EffectName.FIBROUS]


def test_draw_keeps_a_hopping_icon_flush_inside_the_mirrored_rows_right_edge() -> None:
    # The hop is purely vertical, so the mirrored side's right-edge anchoring is unaffected.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    for effect in (EffectName.RUNT, EffectName.TOXICITY):
        scene._enemy_displayed.active_effects.add((EffectCategory.BATTLE, effect))
    event = DotTicked(
        target=scene._battle.enemy,
        effect=EffectName.TOXICITY,
        damage=1,
        target_hp_after=scene._battle.enemy.current_hp - 1,
    )
    scene._phases_for(event)[0].on_start()
    scene._elapsed_seconds += BATTLE_BUFF_ICON_HOP_DURATION_SECONDS / 2
    surface = pygame.Surface((800, 600))
    surface.fill("black")

    scene.draw(surface)

    hop = scene._buff_icon_hop_offset(scene._enemy_displayed, EffectName.TOXICITY)
    assert hop > 0, "expected the icon to be off the ground"
    layout = _combatant_layout(surface, mirrored=True)
    icon_row_x = layout.bar_right
    icon_row_top = _MARGIN + _FONT_SIZE + _BAR_HEIGHT + _METER_HEIGHT + _GAP * 2
    # Sampled from the icon's lifted top, so the rows the hop moves it into are inside the band.
    icon_band = range(icon_row_top - hop, icon_row_top + _FONT_SIZE * 2)
    black = pygame.Color("black")
    # Scanned inboard of the icon gutter: the meter bar's icon reaches into this band and would
    # otherwise be the rightmost column found.
    icon_columns = [x for x in range(icon_row_x) if any(surface.get_at((x, y)) != black for y in icon_band)]

    assert icon_columns, "expected the enemy's buff icons to render"
    assert max(icon_columns) == icon_row_x - 1


@pytest.mark.parametrize("mirrored", [False, True])
def test_a_hopping_icon_never_climbs_into_the_meter_bar_above_its_row(mirrored: bool) -> None:
    # Comparing the meter bar's own rows before and after, so the icon's peak isn't pinned down.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    target = scene._battle.enemy if mirrored else scene._battle.player
    displayed = scene._enemy_displayed if mirrored else scene._player_displayed
    displayed.active_effects.add((EffectCategory.BATTLE, EffectName.TOXICITY))
    meter_top = _MARGIN + _FONT_SIZE + _BAR_HEIGHT + _GAP
    meter_rows = range(meter_top, meter_top + _METER_HEIGHT)
    surface = pygame.Surface((800, 600))

    surface.fill("black")
    scene.draw(surface)
    at_rest = [[surface.get_at((x, y)) for x in range(surface.get_width())] for y in meter_rows]

    event = DotTicked(target=target, effect=EffectName.TOXICITY, damage=1, target_hp_after=target.current_hp - 1)
    scene._phases_for(event)[0].on_start()
    scene._elapsed_seconds += BATTLE_BUFF_ICON_HOP_DURATION_SECONDS / 2
    surface.fill("black")
    scene.draw(surface)
    mid_hop = [[surface.get_at((x, y)) for x in range(surface.get_width())] for y in meter_rows]

    assert scene._buff_icon_hop_offset(displayed, EffectName.TOXICITY) > 0  # really at the arc's peak
    assert mid_hop == at_rest


def test_advance_phases_leaves_displayed_hp_strictly_between_before_and_after_mid_tween() -> None:
    # The central claim of ADR 0013: DisplayedCombatantState reflects only fully-completed phases,
    # never the live Combatant -- which Battle has, per its own contract, already fully resolved
    # by the time any of its events reach the GUI.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
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
    phase = _hp_tween_phase(displayed, 60, 1.0)

    phase.on_progress(0.5)
    assert displayed.hp == pytest.approx(80.0)

    phase.on_complete()
    assert displayed.hp == 60.0


def test_combat_scene_defaults_to_sprite_buff_icon_when_no_factory_is_given() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    icon = scene._buff_icon_factory(EffectName.FIBROUS)

    assert isinstance(icon, SpriteBuffIcon)


def test_buff_icon_row_renders_the_displayed_snapshot_not_live_combatant_state() -> None:
    # The buff row now reads DisplayedCombatantState.active_effects (ADR 0013), kept in sync by
    # _effect_announcement_phase's on_start -- mirrors
    # test_meter_bar_renders_the_displayed_snapshot_not_live_combatant_state's shape for the
    # analogous HP/meter case. Recording which EffectName values actually get rendered (rather
    # than only inspecting the snapshot, which no drawing code reads) is what makes this catch a
    # regression to reading live Combatant state instead.
    rendered: list[EffectName] = []

    def _spy_factory(source: IconSource) -> BuffIcon:
        assert isinstance(source, EffectName)  # nothing under test here names a non-effect icon
        rendered.append(source)
        return TextBuffIcon(source)

    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), buff_icon_factory=_spy_factory, audio=_audio()
    )
    scene._battle.player.effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.BATTLE, 3))  # live only

    scene.draw(pygame.Surface((800, 600)))
    assert EffectName.FIBROUS not in rendered  # displayed snapshot hasn't been told about it yet

    scene._player_displayed.active_effects.add((EffectCategory.BATTLE, EffectName.FIBROUS))
    scene.draw(pygame.Surface((800, 600)))

    assert EffectName.FIBROUS in rendered


def test_draw_buff_icons_shows_the_remaining_turns_number_in_the_icons_top_right_corner() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.active_effects.add((EffectCategory.BATTLE, EffectName.FIBROUS))
    scene._player_displayed.remaining_turns[(EffectCategory.BATTLE, EffectName.FIBROUS)] = 3
    surface = pygame.Surface((800, 600))
    surface.fill("black")

    scene.draw(surface)

    # Mirrors _draw_combatant's own icon-row geometry for the (non-mirrored) player side --
    # the first icon starts exactly at (bar_left, icon_row_top), per _draw_buff_icons.
    bar_left = _combatant_layout(surface, mirrored=False).bar_left
    icon_row_top = _MARGIN + _FONT_SIZE + _BAR_HEIGHT + _METER_HEIGHT + _GAP * 2
    white = pygame.Color("white")
    assert any(
        surface.get_at((x, y)) == white
        for x in range(bar_left, bar_left + _BUFF_ICON_SIZE)
        for y in range(icon_row_top, icon_row_top + _BUFF_ICON_DURATION_FONT_SIZE)
    )


def test_draw_buff_icons_shows_no_number_for_an_indefinite_effect() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.active_effects.add((EffectCategory.LIFESPAN, EffectName.FIBROUS))
    scene._player_displayed.remaining_turns[(EffectCategory.LIFESPAN, EffectName.FIBROUS)] = None
    surface = pygame.Surface((800, 600))
    surface.fill("black")

    scene.draw(surface)

    bar_left = _combatant_layout(surface, mirrored=False).bar_left
    icon_row_top = _MARGIN + _FONT_SIZE + _BAR_HEIGHT + _METER_HEIGHT + _GAP * 2
    white = pygame.Color("white")
    assert not any(
        surface.get_at((x, y)) == white
        for x in range(bar_left, bar_left + _BUFF_ICON_SIZE)
        for y in range(icon_row_top, icon_row_top + _BUFF_ICON_DURATION_FONT_SIZE)
    )


def test_effect_applied_phase_adds_to_the_displayed_active_effects_on_start() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    event = EffectApplied(
        target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE, remaining_turns=3
    )
    key = (EffectCategory.BATTLE, EffectName.FIBROUS)
    assert key not in scene._player_displayed.active_effects

    scene._phases_for(event)[0].on_start()

    assert key in scene._player_displayed.active_effects


def test_effect_applied_phase_sets_the_displayed_remaining_turns_on_start() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    event = EffectApplied(
        target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE, remaining_turns=3
    )
    key = (EffectCategory.BATTLE, EffectName.FIBROUS)

    scene._phases_for(event)[0].on_start()

    assert scene._player_displayed.remaining_turns[key] == 3


def test_effect_applied_phase_refreshes_remaining_turns_on_a_suppressed_reapplication() -> None:
    # PROJECT_BRIEF.md §5.6's refresh-not-stack rule resets duration domain-side without an
    # announcement -- the HUD countdown must follow that silent reset too, not just active_effects.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    key = (EffectCategory.BATTLE, EffectName.RUNT)
    scene._player_displayed.active_effects.add(key)
    scene._player_displayed.remaining_turns[key] = 1
    event = EffectApplied(
        target=scene._battle.player, effect=EffectName.RUNT, category=EffectCategory.BATTLE, remaining_turns=3
    )

    phases = scene._phases_for(event)

    assert phases == []
    assert scene._player_displayed.remaining_turns[key] == 3


def test_effect_expired_phase_discards_from_the_displayed_active_effects_on_start() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    key = (EffectCategory.BATTLE, EffectName.FIBROUS)
    scene._player_displayed.active_effects.add(key)
    event = EffectExpired(target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE)

    scene._phases_for(event)[0].on_start()

    assert key not in scene._player_displayed.active_effects


def test_effect_expired_phase_discards_the_displayed_remaining_turns_on_start() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    key = (EffectCategory.BATTLE, EffectName.FIBROUS)
    scene._player_displayed.active_effects.add(key)
    scene._player_displayed.remaining_turns[key] = 1
    event = EffectExpired(target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE)

    scene._phases_for(event)[0].on_start()

    assert key not in scene._player_displayed.remaining_turns


def test_effect_applied_phase_is_not_suppressed_for_a_different_category_of_the_same_effect() -> None:
    # PROJECT_BRIEF.md §5.6: refresh-not-stack is scoped *per category* -- a Lifespan Fibrous
    # already active does not suppress a genuinely new Battle-scoped Fibrous application (the
    # brief's own worked example: both apply at once and combine additively).
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.active_effects.add((EffectCategory.LIFESPAN, EffectName.FIBROUS))
    event = EffectApplied(
        target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE, remaining_turns=3
    )

    phases = scene._phases_for(event)

    assert len(phases) == 1
    phases[0].on_start()
    assert scene._player_displayed.active_effects == {
        (EffectCategory.LIFESPAN, EffectName.FIBROUS),
        (EffectCategory.BATTLE, EffectName.FIBROUS),
    }


def test_effect_expired_phase_only_discards_the_battle_scoped_key() -> None:
    # A Lifespan instance of the same effect name must survive a Battle instance's expiry -- the
    # HUD icon (keyed by name only, see _draw_buff_icons) stays showing for as long as any
    # category-scoped instance remains.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.active_effects = {
        (EffectCategory.LIFESPAN, EffectName.FIBROUS),
        (EffectCategory.BATTLE, EffectName.FIBROUS),
    }
    event = EffectExpired(target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE)

    scene._phases_for(event)[0].on_start()

    assert scene._player_displayed.active_effects == {(EffectCategory.LIFESPAN, EffectName.FIBROUS)}


def test_a_lifespan_effect_expired_phase_only_discards_the_lifespan_scoped_key() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.active_effects = {
        (EffectCategory.LIFESPAN, EffectName.RESONANCE),
        (EffectCategory.BATTLE, EffectName.RESONANCE),
    }
    event = EffectExpired(target=scene._battle.player, effect=EffectName.RESONANCE, category=EffectCategory.LIFESPAN)

    scene._phases_for(event)[0].on_start()

    assert scene._player_displayed.active_effects == {(EffectCategory.BATTLE, EffectName.RESONANCE)}


def test_meter_bar_renders_the_displayed_snapshot_not_live_combatant_state() -> None:
    # MeterFilled/MeterConsumed now tween DisplayedCombatantState.meter (same as HP), so the drawn
    # bar must track that snapshot, not the live Combatant, while a tween is mid-flight. Recording
    # the actual ratio _draw_bar is called with (rather than only inspecting the snapshot) is what
    # makes this catch a regression to reading live state instead.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.meter = 42  # simulates a tween mid-flight
    scene._battle.player.current_meter = 99  # already fully resolved live, per Battle's contract
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


def test_meter_tween_phase_duration_is_divided_by_the_combat_speed_multiplier() -> None:
    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), combat_speed_multiplier=2.0, audio=_audio()
    )

    phases = scene._phases_for(MeterFilled(combatant=scene._battle.player, amount=50, meter_after=50))

    assert phases[0].duration_seconds == BATTLE_VALUE_TWEEN_SECONDS / 2.0


def test_meter_filled_and_meter_consumed_tween_the_displayed_meter_over_the_hp_tween_duration() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    displayed = scene._player_displayed
    displayed.meter = 0.0

    filled_phase = scene._phases_for(MeterFilled(combatant=scene._battle.player, amount=50, meter_after=50))
    assert len(filled_phase) == 1
    assert filled_phase[0].duration_seconds == BATTLE_VALUE_TWEEN_SECONDS
    filled_phase[0].on_progress(0.5)
    assert displayed.meter == pytest.approx(25.0)
    filled_phase[0].on_complete()
    assert displayed.meter == 50.0

    consumed_phase = scene._phases_for(MeterConsumed(combatant=scene._battle.player, meter_after=0))
    assert len(consumed_phase) == 1
    assert consumed_phase[0].duration_seconds == BATTLE_VALUE_TWEEN_SECONDS
    consumed_phase[0].on_complete()
    assert displayed.meter == 0.0


def test_effect_applied_announcement_duration_is_divided_by_the_combat_speed_multiplier() -> None:
    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), combat_speed_multiplier=2.0, audio=_audio()
    )
    event = EffectApplied(
        target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE, remaining_turns=3
    )

    phases = scene._phases_for(event)

    assert phases[0].duration_seconds == BATTLE_ANNOUNCEMENT_HOLD_SECONDS / 2.0


def test_effect_applied_phase_sets_an_effect_card_announcement_with_title_and_subtitle() -> None:
    rendered_icons: list[BuffIcon] = []

    def _spy_factory(source: IconSource) -> BuffIcon:
        assert isinstance(source, EffectName)  # nothing under test here names a non-effect icon
        icon = TextBuffIcon(source)
        rendered_icons.append(icon)
        return icon

    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), buff_icon_factory=_spy_factory, audio=_audio()
    )
    event = EffectApplied(
        target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE, remaining_turns=3
    )

    phases = scene._phases_for(event)

    assert len(phases) == 1
    assert phases[0].duration_seconds == BATTLE_ANNOUNCEMENT_HOLD_SECONDS
    assert scene._announcement is None  # not set until on_start actually fires
    phases[0].on_start()
    assert scene._announcement == Announcement(
        card=AnchoredCard(
            card=Card(
                title="Fibrous",
                icon=rendered_icons[0],
                description=EFFECT_DESCRIPTIONS[EffectName.FIBROUS],
                subtitle="Player — 3 turns",
            ),
            target=scene._battle.player,
        )
    )
    phases[0].on_complete()
    assert scene._announcement is None


def test_effect_applied_phase_subtitles_a_lifespan_effect_and_an_indefinite_battle_effect() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    lifespan_event = EffectApplied(
        target=scene._battle.player, effect=EffectName.RESONANCE, category=EffectCategory.LIFESPAN, remaining_turns=None
    )
    scene._phases_for(lifespan_event)[0].on_start()
    assert scene._announcement is not None
    assert scene._announcement.card is not None
    assert scene._announcement.card.card.subtitle == "Player — This generation"

    indefinite_event = EffectApplied(
        target=scene._battle.player, effect=EffectName.ADRENALINE, category=EffectCategory.BATTLE, remaining_turns=None
    )
    scene._phases_for(indefinite_event)[0].on_start()
    assert scene._announcement is not None
    assert scene._announcement.card is not None
    assert scene._announcement.card.card.subtitle == "Player — Until battle ends"


def test_effect_applied_phase_is_suppressed_when_the_effect_is_already_active_in_the_same_category() -> None:
    # PROJECT_BRIEF.md §5.6: reapplying an already-active effect refreshes it rather than
    # stacking -- repeatedly triggering the same debuff (e.g. Barbed Struggle every turn) must not
    # re-announce it each time, only the first time it actually becomes active in that category.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.active_effects.add((EffectCategory.BATTLE, EffectName.RUNT))
    event = EffectApplied(
        target=scene._battle.player, effect=EffectName.RUNT, category=EffectCategory.BATTLE, remaining_turns=3
    )

    assert scene._phases_for(event) == []


def test_effect_expired_phase_sets_an_effect_card_announcement_with_a_wears_off_subtitle() -> None:
    rendered_icons: list[BuffIcon] = []

    def _spy_factory(source: IconSource) -> BuffIcon:
        assert isinstance(source, EffectName)  # nothing under test here names a non-effect icon
        icon = TextBuffIcon(source)
        rendered_icons.append(icon)
        return icon

    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), buff_icon_factory=_spy_factory, audio=_audio()
    )
    assert not scene._battle.is_over  # the announcing case
    event = EffectExpired(target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE)

    phases = scene._phases_for(event)
    phases[0].on_start()

    assert scene._announcement == Announcement(
        card=AnchoredCard(
            card=Card(
                title="Fibrous",
                icon=rendered_icons[0],
                description=EFFECT_DESCRIPTIONS[EffectName.FIBROUS],
                subtitle="Player — Wears off",
            ),
            target=scene._battle.player,
        )
    )


def test_effect_expiry_from_end_of_battle_cleanup_clears_the_display_without_announcing() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    key = (EffectCategory.BATTLE, EffectName.FIBROUS)
    scene._player_displayed.active_effects.add(key)
    scene._player_displayed.remaining_turns[key] = 2
    scene._battle.enemy.current_hp = 0
    event = EffectExpired(target=scene._battle.player, effect=EffectName.FIBROUS, category=EffectCategory.BATTLE)

    phases = scene._phases_for(event)

    assert len(phases) == 1
    # A silent phase that still held would read as dead air.
    assert phases[0].duration_seconds == 0.0
    phases[0].on_start()
    assert scene._announcement is None
    assert key not in scene._player_displayed.active_effects
    assert key not in scene._player_displayed.remaining_turns
    phases[0].on_complete()
    assert scene._announcement is None


def test_describe_event_addresses_the_player_directly_on_a_win() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    event = BattleEnded(winner=scene._battle.player)

    assert _describe_event(event, scene._battle.player) == "You win!"


def test_describe_event_addresses_the_player_directly_on_a_loss() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    event = BattleEnded(winner=scene._battle.enemy)

    assert _describe_event(event, scene._battle.player) == "You lose!"


def test_describe_event_keeps_the_impersonal_wording_for_a_draw() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    assert _describe_event(BattleEnded(winner=None), scene._battle.player) == "The battle ends in a draw."


def test_turn_skipped_extra_action_and_battle_ended_announcements_have_no_card() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    events: tuple[BattleEvent, ...] = (
        TurnSkipped(combatant=scene._battle.player),
        ExtraActionTriggered(actor=scene._battle.player, extra_action_index=0),
        BattleEnded(winner=scene._battle.player),
    )

    for event in events:
        phases = scene._phases_for(event)
        assert len(phases) == 1
        phases[0].on_start()
        assert scene._announcement == Announcement(text=_describe_event(event, scene._battle.player))
        phases[0].on_complete()
        assert scene._announcement is None


def test_plain_announcement_phase_duration_is_divided_by_the_combat_speed_multiplier() -> None:
    # _announcement_phase (plain text, e.g. TurnSkipped/BattleEnded) is a distinct Phase(...)
    # literal from _effect_announcement_phase (EffectApplied/EffectExpired, already covered above)
    # -- both need their own coverage at a non-default multiplier.
    generation = _generation()
    scene = CombatScene(
        generation, _encounter(generation), build_placeholder_atlas(), combat_speed_multiplier=2.0, audio=_audio()
    )
    event = TurnSkipped(combatant=scene._battle.player)

    phases = scene._phases_for(event)

    assert phases[0].duration_seconds == BATTLE_ANNOUNCEMENT_HOLD_SECONDS / 2.0


def test_announcement_phase_holds_for_the_tuned_duration_via_the_driver() -> None:
    # Drives the real _advance_phases loop (not just calling on_start/on_complete directly), so it
    # also exercises the announcement's real duration, not only its callbacks' effects.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    event = TurnSkipped(combatant=scene._battle.player)
    scene._queue_events([event])

    scene._advance_phases(0.0)  # the first event of a batch reveals immediately (ADR 0013)
    assert scene._announcement == Announcement(text=_describe_event(event, scene._battle.player))

    scene._advance_phases(BATTLE_ANNOUNCEMENT_HOLD_SECONDS / 2)
    assert scene._announcement is not None  # still holding, short of the full duration

    scene._advance_phases(BATTLE_ANNOUNCEMENT_HOLD_SECONDS / 2)
    assert scene._announcement is None


def test_announcement_hold_timer_is_frozen_while_narration_is_active() -> None:
    # Regression: update() previously ran the phase pipeline unconditionally, so a timed
    # announcement's hold could elapse -- and clear itself -- while narration was up hiding it from
    # ever being drawn (_draw_announcement's succession guard hides it, it doesn't pause it).
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    event = TurnSkipped(combatant=scene._battle.player)
    scene._queue_events([event])
    scene.update(0.0)  # the first event of a batch reveals immediately (ADR 0013)
    assert scene._announcement == Announcement(text=_describe_event(event, scene._battle.player))

    scene._narration.fire(NarrationTrigger.FIRST_ATTACK, "msg", "sub")
    for _ in range(200):
        scene.update(0.016)  # comfortably more real time than the hold needs, if it were ticking

    assert scene._announcement is not None  # still holding: narration froze the timer

    scene._narration.queue.dismiss()
    scene.update(BATTLE_ANNOUNCEMENT_HOLD_SECONDS)

    assert scene._announcement is None  # resumes and completes once narration clears


def test_draw_does_not_raise_with_a_plain_announcement_set() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._announcement = Announcement(text="Test announcement")

    scene.draw(pygame.Surface((800, 600)))


def test_announcement_is_not_drawn_while_narration_is_active() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._announcement = Announcement(text="Test announcement")
    scene._narration.fire(NarrationTrigger.FIRST_ATTACK, "msg", "sub")

    surface = pygame.Surface((800, 600))
    surface.fill(_UNDRAWN)
    scene._draw_announcement(
        surface, _combatant_layout(surface, mirrored=False), _combatant_layout(surface, mirrored=True)
    )
    surface.set_colorkey(_UNDRAWN)

    assert surface.get_bounding_rect().size == (0, 0)


def test_draw_does_not_raise_with_an_effect_card_announcement_set() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._announcement = Announcement(
        card=AnchoredCard(
            card=Card(
                title="Runt",
                icon=TextBuffIcon(EffectName.RUNT),
                description="Lowers attack",
                subtitle="Player — 3 turns",
            ),
            target=scene._battle.player,
        )
    )

    scene.draw(pygame.Surface((800, 600)))


def test_draw_anchors_the_effect_card_over_its_own_combatants_half() -> None:
    render_calls: list[tuple[pygame.Vector2, int]] = []

    class _SpyIcon:
        def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
            render_calls.append((pos, size))

    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    surface = pygame.Surface((800, 600))

    for target, mirrored in ((scene._battle.player, False), (scene._battle.enemy, True)):
        render_calls.clear()
        scene._announcement = Announcement(
            card=AnchoredCard(
                card=Card(title="Runt", icon=_SpyIcon(), description="Lowers attack", subtitle="Player — 3 turns"),
                target=target,
            )
        )

        scene.draw(surface)

        # The scene's only share of the placement is which half the card centers over; the block's
        # own geometry is asserted in tests/gui/test_card.py.
        assert len(render_calls) == 1
        pos, size = render_calls[0]
        assert pos.x + size // 2 == _combatant_layout(surface, mirrored=mirrored).sprite_center[0]


def test_every_effect_card_stays_inside_its_combatants_half_of_the_real_window() -> None:
    # Every label and description is measured on both sides: character count doesn't predict
    # rendered width in a proportional font, and the mirrored side anchors from a different origin.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    width, height = _WINDOW_SIZE
    halves = (
        (scene._battle.player, pygame.Rect(0, 0, width // 2, height)),
        (scene._battle.enemy, pygame.Rect(width // 2, 0, width // 2, height)),
    )

    for effect in EffectName:
        for target, half in halves:
            surface = pygame.Surface((width, height))
            # Not black: the card's backdrop panel is black too, and would be keyed straight out.
            surface.fill(_UNDRAWN)
            scene._announcement = Announcement(
                card=AnchoredCard(
                    card=Card(
                        title=_label(effect),
                        icon=scene._buff_icon_factory(effect),
                        description=EFFECT_DESCRIPTIONS[effect],
                        # The longest duration phrasing _duration_subtitle can produce.
                        subtitle=f"{target.name} — Until battle ends",
                    ),
                    target=target,
                )
            )

            scene._draw_announcement(
                surface, _combatant_layout(surface, mirrored=False), _combatant_layout(surface, mirrored=True)
            )

            surface.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only what was drawn
            drawn = surface.get_bounding_rect()

            # An empty rect is contained by any half, so containment alone would pass on nothing.
            assert drawn.size != (0, 0), (_label(effect), target.name)
            assert half.contains(drawn), (_label(effect), target.name)


def test_swing_phase_focuses_the_source_as_acting_and_the_target_as_receiving() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    swing = scene._phases_for(_hit_landed(scene))[0]
    assert scene._phase_focus is None  # not set until on_start actually fires

    swing.on_start()

    assert scene._phase_focus == PhaseFocus(acting=scene._battle.player, receiving=scene._battle.enemy)
    assert scene._highlight_color_for(scene._battle.player) == BATTLE_ACTING_HIGHLIGHT_COLOR
    assert scene._highlight_color_for(scene._battle.enemy) == BATTLE_RECEIVING_HIGHLIGHT_COLOR


def test_reaction_phase_focuses_only_the_receiving_combatant() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    scene._reaction_phase(scene._battle.player, HitValence.DAMAGE).on_start()

    assert scene._phase_focus == PhaseFocus(receiving=scene._battle.player)
    assert scene._highlight_color_for(scene._battle.enemy) is None


def test_overlay_phase_focuses_the_target_as_receiving() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    scene._phases_for(_dot_ticked(scene))[0].on_start()

    assert scene._phase_focus == PhaseFocus(receiving=scene._battle.player)


def test_focus_outlives_the_animation_phase_that_set_it_and_covers_the_trailing_hp_tween() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    hp_before = scene._enemy_displayed.hp
    event = _hit_landed(scene)
    scene._queue_events([event])

    scene._advance_phases(0.0)  # the zero-length placeholder swing completes; its hp tween begins
    assert scene._current_phases[0].duration_seconds == BATTLE_VALUE_TWEEN_SECONDS
    assert scene._phase_focus == PhaseFocus(acting=scene._battle.player, receiving=scene._battle.enemy)

    scene._advance_phases(BATTLE_VALUE_TWEEN_SECONDS / 2)
    assert event.target_hp_after < scene._enemy_displayed.hp < hp_before  # the bar really is moving
    assert scene._phase_focus == PhaseFocus(acting=scene._battle.player, receiving=scene._battle.enemy)


def test_focus_clears_when_the_next_event_concerns_nobody() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    meter_filled = MeterFilled(combatant=scene._battle.player, amount=10, meter_after=10)
    scene._queue_events([_hit_landed(scene), meter_filled])

    scene._advance_phases(0.0)
    scene._advance_phases(BATTLE_VALUE_TWEEN_SECONDS)  # finishes the hit, starts the meter tween

    assert scene._current_phases
    assert scene._phase_focus is None


def test_the_next_events_focus_is_established_by_the_same_call_that_drains_the_previous() -> None:
    # The two hits run in opposite directions, so the focus that comes back can only be the second's.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    player, enemy = scene._battle.player, scene._battle.enemy
    riposte = HitLanded(
        source=enemy,
        target=player,
        action=ActionKind.STRUGGLE,
        hit_index=0,
        hit_count=1,
        damage=4,
        target_hp_after=player.current_hp - 4,
    )
    scene._queue_events([_hit_landed(scene), riposte])

    scene._advance_phases(0.0)
    assert scene._phase_focus == PhaseFocus(acting=player, receiving=enemy)

    scene._advance_phases(BATTLE_VALUE_TWEEN_SECONDS)  # drains the first hit and takes up the second

    assert scene._phase_focus == PhaseFocus(acting=enemy, receiving=player)


def test_death_focuses_the_fallen_combatant_for_its_whole_pose() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._queue_events([Death(combatant=scene._battle.player)])

    scene._advance_phases(0.0)

    assert scene._current_phases[0].duration_seconds == BATTLE_DEATH_POSE_HOLD_SECONDS
    assert scene._phase_focus == PhaseFocus(receiving=scene._battle.player)


def test_revive_focus_covers_the_hp_climb_that_follows_its_state_switch() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._player_displayed.hp = 0.0
    scene._queue_events([Revive(combatant=scene._battle.player, revived_hp=10)])

    scene._advance_phases(0.0)  # the zero-length state switch completes; the hp tween begins
    assert scene._current_phases[0].duration_seconds == BATTLE_VALUE_TWEEN_SECONDS
    assert scene._phase_focus == PhaseFocus(receiving=scene._battle.player)

    scene._advance_phases(BATTLE_VALUE_TWEEN_SECONDS / 2)
    assert 0.0 < scene._player_displayed.hp < 10.0  # the bar really is climbing
    assert scene._phase_focus == PhaseFocus(receiving=scene._battle.player)


def test_role_highlight_colors_do_not_collide_with_the_bars_they_tint() -> None:
    # Compared as resolved channels so respelling a colour can't slip a collision past this.
    panel_colors = [tuple(pygame.Color(_HP_COLOR)), tuple(pygame.Color(_METER_COLOR))]
    acting = tuple(pygame.Color(BATTLE_ACTING_HIGHLIGHT_COLOR))
    receiving = tuple(pygame.Color(BATTLE_RECEIVING_HIGHLIGHT_COLOR))

    assert acting not in panel_colors
    assert receiving not in panel_colors
    assert acting != receiving


def test_focus_clears_once_the_reveal_queue_drains() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._queue_events([_hit_landed(scene)])

    scene._advance_phases(0.0)
    scene._advance_phases(BATTLE_VALUE_TWEEN_SECONDS)

    assert not scene._current_phases
    assert not scene._pending_events
    assert scene._phase_focus is None


def test_update_advances_the_scene_clock_by_the_frames_delta() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    scene.update(0.016)
    scene.update(0.016)

    assert scene._elapsed_seconds == pytest.approx(0.032)


def test_pulse_is_driven_by_the_scene_clock_not_the_in_flight_phases_own_elapsed_time() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    at_rest = scene._pulse_mix()
    scene._elapsed_seconds = BATTLE_HIGHLIGHT_PULSE_PERIOD_SECONDS / 4

    assert scene._phase_elapsed == 0.0
    assert scene._pulse_mix() != at_rest


def test_draw_does_not_raise_while_a_swing_highlight_is_active() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._phases_for(_hit_landed(scene))[0].on_start()
    scene._elapsed_seconds = BATTLE_HIGHLIGHT_PULSE_PERIOD_SECONDS / 2  # peak of the pulse

    scene.draw(pygame.Surface((800, 600)))


def test_swing_phase_flashes_the_target_only_and_clears_it_when_the_swing_completes() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    swing = scene._phases_for(_hit_landed(scene))[0]
    assert scene._enemy_displayed.hit_flash is None  # not set until on_start actually fires

    swing.on_start()
    assert scene._enemy_displayed.hit_flash == HitFlash(scene._elapsed_seconds, HitValence.DAMAGE)
    assert scene._player_displayed.hit_flash is None  # the attacker is not being hit

    swing.on_complete()
    assert scene._enemy_displayed.hit_flash is None


def test_reaction_phase_flashes_the_flinching_combatant() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    reaction = scene._reaction_phase(scene._battle.player, HitValence.DAMAGE)
    reaction.on_start()
    assert scene._player_displayed.hit_flash == HitFlash(scene._elapsed_seconds, HitValence.DAMAGE)
    assert scene._enemy_displayed.hit_flash is None

    reaction.on_complete()
    assert scene._player_displayed.hit_flash is None


def test_overlay_phase_inherits_the_reactions_flash() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    overlay_phase = scene._phases_for(_dot_ticked(scene))[0]
    overlay_phase.on_start()
    assert scene._player_displayed.hit_flash == HitFlash(scene._elapsed_seconds, HitValence.DAMAGE)

    overlay_phase.on_complete()
    assert scene._player_displayed.hit_flash is None


_FLASH_VALENCE_BY_EVENT_TYPE: Mapping[type[object], HitValence] = {
    HitLanded: HitValence.DAMAGE,
    HitReflected: HitValence.DAMAGE,
    SelfDamageTaken: HitValence.DAMAGE,
    DotTicked: HitValence.DAMAGE,
    HealApplied: HitValence.HEALING,
    Revive: HitValence.HEALING,
}


def test_only_the_events_that_move_hp_flash_and_each_carries_its_own_valence() -> None:
    # Driven off the one-of-each list, so a new event variant has to declare whether it flashes.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    flashed: dict[type[object], HitValence] = {}
    for event in _ONE_OF_EACH_BATTLE_EVENT:
        scene._enemy_displayed.hit_flash = None
        for phase in scene._phases_for(event):
            phase.on_start()
        flash = scene._enemy_displayed.hit_flash
        if flash is not None:
            flashed[type(event)] = flash.valence

    assert flashed == _FLASH_VALENCE_BY_EVENT_TYPE


_MIN_TINT_CHANNEL_LEAD = 128  # in 0-255 units, so the multiply half of the flash has something to suppress
_MIN_HUE_SEPARATION_DEGREES = 20.0


def _channel_lead(color: pygame.Color, channel: int) -> int:
    """How far `channel` (0 red, 1 green, 2 blue) leads the other two in `color`, in 0-255 units."""
    return color[channel] - max(value for index, value in enumerate(color[:3]) if index != channel)


def _hue_separation_degrees(one: pygame.typing.ColorLike, other: pygame.typing.ColorLike) -> float:
    """The shorter way round the hue circle between two colours, in degrees."""
    gap = abs(pygame.Color(one).hsva[0] - pygame.Color(other).hsva[0]) % 360.0
    return min(gap, 360.0 - gap)


def test_both_flash_tints_lead_hard_on_their_own_channel() -> None:
    damage = pygame.Color(BATTLE_HIT_FLASH_DAMAGE_COLOR)
    healing = pygame.Color(BATTLE_HIT_FLASH_HEALING_COLOR)

    assert _channel_lead(damage, 0) >= _MIN_TINT_CHANNEL_LEAD
    assert _channel_lead(healing, 1) >= _MIN_TINT_CHANNEL_LEAD


def test_the_damage_tint_keeps_clear_of_the_receiving_roles_highlight_hue() -> None:
    # The struck combatant's HP bar and name label pulse the receiving colour inches away at the
    # same moment, and both are saturated, so hue is all that separates them.
    separation = _hue_separation_degrees(BATTLE_HIT_FLASH_DAMAGE_COLOR, BATTLE_RECEIVING_HIGHLIGHT_COLOR)

    assert separation >= _MIN_HUE_SEPARATION_DEGREES


def test_an_overlay_and_the_flash_beneath_it_read_the_same_valence() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    for event, expected in ((_dot_ticked(scene), HitValence.DAMAGE), (_heal_applied(scene), HitValence.HEALING)):
        scene._phases_for(event)[0].on_start()

        flash = scene._displayed_for(event.target).hit_flash
        assert flash is not None
        assert scene._overlay is not None
        assert flash.valence is expected
        assert scene._overlay.valence is expected


@pytest.mark.parametrize("valence", list(HitValence))
def test_the_overlays_hp_amount_is_printed_in_its_valences_colour(valence: HitValence) -> None:
    class _SilentIcon:
        def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
            return None

    generation = _generation()
    scene = CombatScene(
        generation,
        _encounter(generation),
        build_placeholder_atlas(),
        buff_icon_factory=lambda effect: _SilentIcon(),
        audio=_audio(),
    )
    scene._overlay = Overlay(
        target=scene._battle.player, source=EffectName.TOXICITY, label="Toxicity", hp_delta=-2, valence=valence
    )
    surface = pygame.Surface((400, 300))
    surface.fill("black")

    scene._draw_overlay(surface, _combatant_layout(surface, mirrored=False), _combatant_layout(surface, mirrored=True))

    painted = {
        tuple(surface.get_at((x, y)))[:3] for x in range(surface.get_width()) for y in range(surface.get_height())
    }
    opposite = next(other for other in HitValence if other is not valence)
    assert tuple(pygame.Color(_valence_color(valence)))[:3] in painted
    assert tuple(pygame.Color(_valence_color(opposite)))[:3] not in painted
    assert tuple(pygame.Color(_TEXT_COLOR))[:3] in painted  # the name stays neutral


def test_hit_flash_peaks_on_impact_and_decays_over_its_own_duration() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    displayed = scene._player_displayed
    assert scene._hit_flash_strength(displayed) == 0.0  # nothing lit before a hit lands

    scene._reaction_phase(scene._battle.player, HitValence.DAMAGE).on_start()
    assert scene._hit_flash_strength(displayed) == pytest.approx(BATTLE_HIT_FLASH_STRENGTH)

    scene._elapsed_seconds += BATTLE_HIT_FLASH_DURATION_SECONDS / 2
    assert 0.0 < scene._hit_flash_strength(displayed) < BATTLE_HIT_FLASH_STRENGTH

    scene._elapsed_seconds += BATTLE_HIT_FLASH_DURATION_SECONDS / 2
    assert scene._hit_flash_strength(displayed) == 0.0


_MIN_LIT_CHANNEL_LEAD = 40  # _MIN_TINT_CHANNEL_LEAD's counterpart, measured on the lit pixel


@pytest.mark.parametrize(("valence", "channel"), [(HitValence.DAMAGE, 0), (HitValence.HEALING, 1)])
@pytest.mark.parametrize("pixel", [(255, 255, 255, 255), (220, 220, 220, 255)])
def test_a_flash_still_carries_its_valence_on_a_bright_sprite_pixel(
    valence: HitValence, channel: int, pixel: tuple[int, int, int, int]
) -> None:
    sprite = pygame.Surface((1, 1), pygame.SRCALPHA)
    sprite.fill(pixel)

    lit = _lit_by_hit_flash(sprite, BATTLE_HIT_FLASH_STRENGTH, valence)

    assert _channel_lead(lit.get_at((0, 0)), channel) >= _MIN_LIT_CHANNEL_LEAD


@pytest.mark.parametrize("valence", list(HitValence))
def test_a_flash_of_no_strength_leaves_every_channel_exactly_where_it_was(valence: HitValence) -> None:
    # A multiply that quantised even one step low would darken the sprite on every fading frame.
    sprite = pygame.Surface((256, 1), pygame.SRCALPHA)
    for x in range(256):
        sprite.set_at((x, 0), (x, 255 - x, (x * 7) % 256, 255))

    lit = _lit_by_hit_flash(sprite, 0.0, valence)

    assert [lit.get_at((x, 0)) for x in range(256)] == [sprite.get_at((x, 0)) for x in range(256)]


@pytest.mark.parametrize("valence", list(HitValence))
def test_a_flash_leaves_the_sprites_transparent_margin_transparent(valence: HitValence) -> None:
    sprite = pygame.Surface((2, 1), pygame.SRCALPHA)
    sprite.set_at((0, 0), (10, 20, 30, 0))
    sprite.set_at((1, 0), (10, 20, 30, 255))

    lit = _lit_by_hit_flash(sprite, 1.0, valence)

    assert lit.get_at((0, 0)).a == 0
    assert lit.get_at((1, 0)).a == 255


def test_drawing_a_hit_flash_leaves_the_animators_cached_frame_untouched(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)
    atlas = build_art_atlas(tmp_path)
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())
    scene._reaction_phase(scene._battle.player, HitValence.DAMAGE).on_start()
    frame = scene._current_sprite(scene._battle.player)
    pixels_before = pygame.image.tobytes(frame, "RGBA")

    scene.draw(pygame.Surface((800, 600)))

    assert scene._hit_flash_strength(scene._player_displayed) > 0.0  # the flash really was drawn
    assert pygame.image.tobytes(frame, "RGBA") == pixels_before


def test_drawing_a_dimmed_combatant_leaves_the_animators_cached_frame_untouched(tmp_path: Path) -> None:
    _write_full_combat_sprite_set(tmp_path / SpriteKey.PLAYER.value)
    atlas = build_art_atlas(tmp_path)
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), atlas, audio=_audio())
    scene._active_combatant = scene._battle.enemy  # leaves the player dimmed
    frame = scene._current_sprite(scene._battle.player)
    pixels_before = pygame.image.tobytes(frame, "RGBA")

    scene.draw(pygame.Surface((800, 600)))

    assert pixels_before != bytes(len(pixels_before))  # sanity: the sprite isn't already blank
    assert pygame.image.tobytes(frame, "RGBA") == pixels_before


def test_draw_does_not_raise_while_a_hit_flash_is_active() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._phases_for(_hit_landed(scene))[0].on_start()

    scene.draw(pygame.Surface((800, 600)))


def test_the_turn_banner_is_absent_before_the_first_turn() -> None:
    # start()'s Resonance prefill fills the whole first update(), so no turn is driven yet.
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)
    assert scene._turn_banner is None

    scene.update(0.016)
    scene._draw_turn_banner(surface)

    assert scene._current_phases or scene._pending_events  # start()'s own events are still playing
    assert scene._turn_banner is None
    surface.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only what was drawn
    assert surface.get_bounding_rect().size == (0, 0)


def test_the_turn_banner_names_the_player_while_the_action_menu_is_up() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    scene.update(0.016)
    assert scene._pending_query is not None
    assert scene._turn_banner == "Your turn"

    _press(scene, ACTION_KEYS[0])
    _drive_to_next_player_query(scene)

    latest_action_line = next(line for line in reversed(scene._log) if " uses " in line)
    assert latest_action_line.startswith(scene._battle.enemy.name)  # the newest ActionChosen is theirs
    assert scene._turn_banner == "Your turn"


def test_the_turn_banner_names_the_enemy_during_the_enemy_turn() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)
    _press(scene, ACTION_KEYS[0])

    for _ in range(400):
        while scene._narration.queue.is_active:  # e.g. FIRST_ATTACK, on the player's first hit
            scene._narration.queue.dismiss()
        scene.update(0.016)
        if scene._turn_banner != "Your turn":
            break
    else:
        raise AssertionError("the enemy's turn never came around")

    assert scene._turn_banner == f"{scene._battle.enemy.name}'s turn"


def test_a_skipped_player_turn_still_reads_as_the_players_own() -> None:
    # Vegetative concludes the turn inside query_player_turn() itself, with no action to choose.
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.VEGETATIVE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character, rng=_AlwaysRolling([EncounterKind.ENEMY]))
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    scene.update(0.016)

    assert scene._announcement == Announcement(text=f"{scene._battle.player.name}'s turn is skipped.")
    assert scene._turn_banner == "Your turn"


def test_an_extra_action_keeps_the_turn_banner_on_the_player() -> None:
    # An extra action drops turn_phase back to AWAITING_QUERY mid-round, latching again.
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.UPROOTED, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character, rng=_AlwaysRolling([EncounterKind.ENEMY]))
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    banners: list[str | None] = []

    for _ in range(400):
        _press(scene, ACTION_KEYS[0])
        scene.update(0.016)
        banners.append(scene._turn_banner)
        if any("acts again" in line for line in scene._log) and scene._pending_query is not None:
            break
    else:
        raise AssertionError("no extra action was triggered within the frame budget")

    assert scene._turn_banner == "Your turn"
    assert set(banners) == {"Your turn"}  # never handed to the enemy part-way through the round


def test_the_turn_banner_is_cleared_before_the_battle_result_is_announced() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=overwhelming)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    banners_over_the_result: list[str | None] = []

    for _ in range(2000):
        _press(scene, ACTION_KEYS[0])
        transition = scene.update(0.016)
        # No effect is ever in play, so the result is the only card-less announcement here.
        if scene._announcement is not None and scene._announcement.card is None:
            banners_over_the_result.append(scene._turn_banner)
        if transition is not None:
            break
    else:
        raise AssertionError("battle did not conclude within the frame budget")

    assert banners_over_the_result  # the result really was on screen to be measured
    assert set(banners_over_the_result) == {None}
    assert scene._turn_banner is None


@pytest.mark.parametrize("strain", ENCOUNTERABLE_STRAINS)
def test_the_turn_banner_clears_both_name_labels_at_the_real_window_size(strain: Strain) -> None:
    # Rendered width isn't predicted by character count in a proportional font, so every strain is
    # measured against the real font. Nothing sprite-derived, so the 32x32 placeholder atlas is fine.
    generation = _generation(strain_queue=[strain])
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._turn_banner = _turn_title(scene._battle.enemy)
    surface = pygame.Surface(_WINDOW_SIZE)
    surface.fill(_UNDRAWN)

    scene._draw_turn_banner(surface)

    surface.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only what was drawn
    drawn = surface.get_bounding_rect()
    font = get_font(GameFont.ITHACA, _FONT_SIZE)
    player_name = pygame.Rect(
        _combatant_layout(surface, mirrored=False).bar_left, _MARGIN, *font.size(scene._battle.player.name)
    )
    enemy_name = pygame.Rect(0, _MARGIN, *font.size(scene._battle.enemy.name))
    enemy_name.right = _combatant_layout(surface, mirrored=True).bar_right

    assert drawn.size != (0, 0), strain  # an empty rect collides with nothing, and would prove nothing
    # Sharing the row is the premise of the two checks below; off it they'd pass for free.
    assert pygame.Rect(0, player_name.top, surface.get_width(), player_name.height).contains(drawn), strain
    assert not drawn.colliderect(player_name), strain
    assert not drawn.colliderect(enemy_name), strain


def test_the_active_combatant_is_absent_before_the_first_turn() -> None:
    # Mirrors test_the_turn_banner_is_absent_before_the_first_turn -- same latch, same call sites.
    character = Character(current_hp=_STATS.max_hp, max_hp=_STATS.max_hp)
    character.effects.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    assert scene._active_combatant is None

    scene.update(0.016)

    assert scene._current_phases or scene._pending_events  # start()'s own events are still playing
    assert scene._active_combatant is None


def test_the_active_combatant_is_the_player_while_the_action_menu_is_up() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    scene.update(0.016)

    assert scene._pending_query is not None
    assert scene._active_combatant is scene._battle.player


def test_the_active_combatant_is_the_enemy_during_the_enemy_turn() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)
    _press(scene, ACTION_KEYS[0])

    for _ in range(400):
        while scene._narration.queue.is_active:  # e.g. FIRST_ATTACK, on the player's first hit
            scene._narration.queue.dismiss()
        scene.update(0.016)
        if scene._active_combatant is not scene._battle.player:
            break
    else:
        raise AssertionError("the enemy's turn never came around")

    assert scene._active_combatant is scene._battle.enemy


def test_the_active_combatant_is_cleared_before_the_battle_result_is_announced() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=overwhelming)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    active_over_the_result: list[Combatant | None] = []

    for _ in range(2000):
        _press(scene, ACTION_KEYS[0])
        transition = scene.update(0.016)
        # No effect is ever in play, so the result is the only card-less announcement here.
        if scene._announcement is not None and scene._announcement.card is None:
            active_over_the_result.append(scene._active_combatant)
        if transition is not None:
            break
    else:
        raise AssertionError("battle did not conclude within the frame budget")

    assert active_over_the_result  # the result really was on screen to be measured
    assert set(active_over_the_result) == {None}
    assert scene._active_combatant is None


def test_dimmed_darkens_every_rgb_channel_toward_black() -> None:
    sprite = pygame.Surface((1, 1), pygame.SRCALPHA)
    sprite.fill((200, 100, 50, 255))

    dimmed = _dimmed(sprite, 0.5)

    pixel = dimmed.get_at((0, 0))
    assert pixel.r < 200
    assert pixel.g < 100
    assert pixel.b < 50
    assert pixel.a == 255


def test_dimmed_at_factor_one_leaves_the_sprite_unchanged() -> None:
    sprite = pygame.Surface((256, 1), pygame.SRCALPHA)
    for x in range(256):
        sprite.set_at((x, 0), (x, 255 - x, (x * 7) % 256, 255))

    dimmed = _dimmed(sprite, 1.0)

    assert [dimmed.get_at((x, 0)) for x in range(256)] == [sprite.get_at((x, 0)) for x in range(256)]


def test_dimmed_at_factor_zero_blacks_out_rgb_but_keeps_alpha() -> None:
    sprite = pygame.Surface((1, 1), pygame.SRCALPHA)
    sprite.fill((200, 100, 50, 128))

    pixel = _dimmed(sprite, 0.0).get_at((0, 0))

    assert (pixel.r, pixel.g, pixel.b) == (0, 0, 0)
    assert pixel.a == 128


def test_dimmed_leaves_the_sprites_transparent_margin_transparent() -> None:
    sprite = pygame.Surface((2, 1), pygame.SRCALPHA)
    sprite.set_at((0, 0), (10, 20, 30, 0))
    sprite.set_at((1, 0), (10, 20, 30, 255))

    dimmed = _dimmed(sprite, BATTLE_INACTIVE_COMBATANT_DIM_FACTOR)

    assert dimmed.get_at((0, 0)).a == 0
    assert dimmed.get_at((1, 0)).a == 255


def _sprite_pixel(
    surface: pygame.Surface, scene: CombatScene, combatant: Combatant, layout: CombatantLayout
) -> pygame.Color:
    sprite = scene._current_sprite(combatant)
    topleft = layout.sprite_topleft(sprite)
    return surface.get_at((topleft[0] + sprite.get_width() // 2, topleft[1] + sprite.get_height() // 2))


def test_draw_combatant_dims_only_the_side_that_is_not_the_active_combatant() -> None:
    # Pixel-level, not a spy on _dimmed: the earlier version only proved the helper was *called*,
    # which stayed green even with the dim (and the hit-flash tint) dropped from the blit entirely.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    surface = pygame.Surface(_WINDOW_SIZE)
    player_layout = _combatant_layout(surface, mirrored=False)
    enemy_layout = _combatant_layout(surface, mirrored=True)

    scene._active_combatant = None
    scene._draw_combatant(surface, scene._battle.player, scene._player_displayed, player_layout)
    scene._draw_combatant(surface, scene._battle.enemy, scene._enemy_displayed, enemy_layout)
    baseline_player = _sprite_pixel(surface, scene, scene._battle.player, player_layout)
    baseline_enemy = _sprite_pixel(surface, scene, scene._battle.enemy, enemy_layout)

    scene._active_combatant = scene._battle.player
    scene._draw_combatant(surface, scene._battle.player, scene._player_displayed, player_layout)
    scene._draw_combatant(surface, scene._battle.enemy, scene._enemy_displayed, enemy_layout)
    player_pixel = _sprite_pixel(surface, scene, scene._battle.player, player_layout)
    dimmed_enemy = _sprite_pixel(surface, scene, scene._battle.enemy, enemy_layout)

    assert (player_pixel.r, player_pixel.g, player_pixel.b) == (baseline_player.r, baseline_player.g, baseline_player.b)
    assert dimmed_enemy.r <= baseline_enemy.r
    assert dimmed_enemy.g <= baseline_enemy.g
    assert dimmed_enemy.b <= baseline_enemy.b
    assert (dimmed_enemy.r, dimmed_enemy.g, dimmed_enemy.b) != (baseline_enemy.r, baseline_enemy.g, baseline_enemy.b)


def test_draw_combatant_dims_neither_side_before_a_turn_is_latched() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    assert scene._active_combatant is None
    surface = pygame.Surface(_WINDOW_SIZE)
    player_layout = _combatant_layout(surface, mirrored=False)
    enemy_layout = _combatant_layout(surface, mirrored=True)

    scene._draw_combatant(surface, scene._battle.player, scene._player_displayed, player_layout)
    scene._draw_combatant(surface, scene._battle.enemy, scene._enemy_displayed, enemy_layout)

    player_sprite = scene._current_sprite(scene._battle.player)
    enemy_sprite = scene._current_sprite(scene._battle.enemy)
    player_pixel = _sprite_pixel(surface, scene, scene._battle.player, player_layout)
    enemy_pixel = _sprite_pixel(surface, scene, scene._battle.enemy, enemy_layout)
    raw_player = player_sprite.get_at((player_sprite.get_width() // 2, player_sprite.get_height() // 2))
    raw_enemy = enemy_sprite.get_at((enemy_sprite.get_width() // 2, enemy_sprite.get_height() // 2))

    assert (player_pixel.r, player_pixel.g, player_pixel.b) == (raw_player.r, raw_player.g, raw_player.b)
    assert (enemy_pixel.r, enemy_pixel.g, enemy_pixel.b) == (raw_enemy.r, raw_enemy.g, raw_enemy.b)


def test_draw_does_not_raise_while_a_turn_is_latched() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)
    assert scene._active_combatant is not None

    scene.draw(pygame.Surface(_WINDOW_SIZE))


def test_draw_background_uses_the_resolved_biome_key(monkeypatch: pytest.MonkeyPatch) -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    seen_keys: list[SpriteKey] = []

    def _fake_crop_to_cover(surface: pygame.Surface, target_size: tuple[int, int]) -> pygame.Surface:
        return surface

    import eye.gui.scenes.combat as combat_module

    original_get = scene._atlas.get

    def _tracking_get(key: SpriteKey) -> pygame.Surface:
        if key in (SpriteKey.BIOME_TURF, SpriteKey.BIOME_DEAD_FOREST, SpriteKey.BIOME_FOREST):
            seen_keys.append(key)
        return original_get(key)

    monkeypatch.setattr(scene._atlas, "get", _tracking_get)
    monkeypatch.setattr(combat_module, "crop_to_cover", _fake_crop_to_cover)

    scene.draw(pygame.Surface(_WINDOW_SIZE))

    from eye.gui.biome import resolve_biome

    assert seen_keys == [resolve_biome(scene._generation.distance_from_home)]


def test_construction_does_not_fire_first_battle_narration() -> None:
    # FIRST_BATTLE fires in ExplorationScene, as soon as advance() reveals the encounter -- before
    # the player has walked up to it, not here once combat has already begun.
    generation = _generation()

    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    assert NarrationTrigger.FIRST_BATTLE not in scene._narration._seen
    assert scene._narration.queue.is_active is False


def test_fire_narration_for_a_player_hit_landed_fires_first_attack() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    event = HitLanded(
        source=scene._battle.player,
        target=scene._battle.enemy,
        action=ActionKind.STRUGGLE,
        hit_index=0,
        hit_count=1,
        damage=3,
        target_hp_after=17,
    )

    scene._fire_narration_for(event)

    assert NarrationTrigger.FIRST_ATTACK in scene._narration._seen


def test_fire_narration_for_an_enemy_hit_landed_does_not_fire_first_attack() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    event = HitLanded(
        source=scene._battle.enemy,
        target=scene._battle.player,
        action=ActionKind.STRUGGLE,
        hit_index=0,
        hit_count=1,
        damage=3,
        target_hp_after=17,
    )

    scene._fire_narration_for(event)

    assert NarrationTrigger.FIRST_ATTACK not in scene._narration._seen


def _give_player_a_meter_gated_action(scene: CombatScene) -> None:
    gated_action = ActionDefinition(kind=ActionKind.SWARM_ATTACK, name="Coordinated Strike", requires_full_meter=True)
    scene._battle.player.available_actions = (*scene._battle.player.available_actions, gated_action)


def test_fire_narration_for_the_players_meter_reaching_capacity_fires_first_meter_full() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    _give_player_a_meter_gated_action(scene)
    capacity = scene._battle.player.base_stats.meter_capacity
    event = MeterFilled(combatant=scene._battle.player, amount=10, meter_after=capacity)

    scene._fire_narration_for(event)

    assert NarrationTrigger.FIRST_METER_FULL in scene._narration._seen


def test_fire_narration_for_the_players_meter_below_capacity_does_not_fire_first_meter_full() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    _give_player_a_meter_gated_action(scene)
    below_capacity = scene._battle.player.base_stats.meter_capacity - 1
    event = MeterFilled(combatant=scene._battle.player, amount=10, meter_after=below_capacity)

    scene._fire_narration_for(event)

    assert NarrationTrigger.FIRST_METER_FULL not in scene._narration._seen


def test_fire_narration_for_a_full_meter_does_not_fire_without_a_meter_gated_action_available() -> None:
    # A full meter is reachable even with no SWARM/ATTACK node purchased yet -- the tutorial
    # promising "a new action has appeared" must not fire until one actually has.
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    capacity = scene._battle.player.base_stats.meter_capacity
    event = MeterFilled(combatant=scene._battle.player, amount=10, meter_after=capacity)

    scene._fire_narration_for(event)

    assert NarrationTrigger.FIRST_METER_FULL not in scene._narration._seen


def test_fire_narration_for_the_enemys_meter_filling_does_not_fire_first_meter_full() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    capacity = scene._battle.enemy.base_stats.meter_capacity
    event = MeterFilled(combatant=scene._battle.enemy, amount=10, meter_after=capacity)

    scene._fire_narration_for(event)

    assert NarrationTrigger.FIRST_METER_FULL not in scene._narration._seen


def test_fire_narration_for_the_players_real_death_fires_first_death() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._battle.player.current_hp = 0
    event = Death(combatant=scene._battle.player)

    scene._fire_narration_for(event)

    assert NarrationTrigger.FIRST_DEATH in scene._narration._seen


def test_fire_narration_for_the_players_death_followed_by_a_revive_does_not_fire_first_death() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    # Battle applies a Revive's HP synchronously before this event ever reveals (GOTCHAS.md), so a
    # real revive leaves current_hp positive by the time _fire_narration_for sees the Death.
    scene._battle.player.current_hp = 1
    event = Death(combatant=scene._battle.player)

    scene._fire_narration_for(event)

    assert NarrationTrigger.FIRST_DEATH not in scene._narration._seen


def test_fire_narration_for_the_enemys_death_does_not_fire_first_death() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._battle.enemy.current_hp = 0
    event = Death(combatant=scene._battle.enemy)

    scene._fire_narration_for(event)

    assert NarrationTrigger.FIRST_DEATH not in scene._narration._seen


def test_a_won_battle_fires_first_attack_narration_along_the_way() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=overwhelming)
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    _drive_to_transition(scene)

    assert NarrationTrigger.FIRST_ATTACK in scene._narration._seen


def test_a_lost_battle_fires_first_death_narration_along_the_way() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(stats=fragile, character=Character(current_hp=5, max_hp=5))
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())

    _drive_to_transition(scene)

    assert generation.died is True
    assert NarrationTrigger.FIRST_DEATH in scene._narration._seen


def test_a_shared_narration_instance_does_not_refire_first_battle_across_scenes() -> None:
    # Two battles within one generation's life (as GameDriver's shared NarrationTriggers sees
    # across successive CombatScene reconstructions), each needing its own Generation since a
    # Battle must be finished before the same Generation can start another.
    triggers = NarrationTriggers()
    first_generation = _generation()
    CombatScene(
        first_generation, _encounter(first_generation), build_placeholder_atlas(), narration=triggers, audio=_audio()
    )
    triggers.queue.dismiss()

    second_generation = _generation()
    CombatScene(
        second_generation, _encounter(second_generation), build_placeholder_atlas(), narration=triggers, audio=_audio()
    )

    assert triggers.queue.is_active is False


def test_narration_dismiss_withholds_the_input_it_shares_a_keypress_with() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene.update(0.016)  # reach AWAITING_PLAYER_ACTION
    assert scene._pending_query is not None
    scene._narration.queue.enqueue("test message", "test subtitle")  # e.g. FIRST_ATTACK, mid-battle
    assert scene._narration.queue.is_active is True

    _press(scene, ACTION_KEYS[0])

    assert scene._narration.queue.is_active is False  # dismissed
    assert scene._pending_action_index is None  # the same press did not also commit a menu action


def test_update_withholds_battle_concluded_while_the_narration_is_still_active() -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._battle.player.current_hp = 0  # forces is_over True without going through _conclude()
    scene._narration.queue.enqueue("test message", "test subtitle")  # e.g. FIRST_DEATH, still up

    result = scene.update(0.016)

    assert result is None
    assert scene._narration.queue.is_active is True

    scene._narration.queue.dismiss()
    result = scene.update(0.016)

    assert result == BattleConcluded()


def test_draw_renders_the_active_narration_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    scene._narration.queue.enqueue("test message", "test subtitle")  # e.g. FIRST_ATTACK, mid-battle
    drawn: list[NarrationEntry] = []
    import eye.gui.scenes.combat as combat_module

    monkeypatch.setattr(
        combat_module, "draw_narration", lambda surface, entry, *, center_x, column_width: drawn.append(entry)
    )

    scene.draw(pygame.Surface((800, 600)))

    assert drawn == [scene._narration.queue.current]


def _scene_at_the_action_menu() -> CombatScene:
    generation = _generation()
    scene = CombatScene(generation, _encounter(generation), build_placeholder_atlas(), audio=_audio())
    _drive_to_next_player_query(scene)
    return scene


def test_legend_key_opens_the_legend_while_the_action_menu_is_up() -> None:
    scene = _scene_at_the_action_menu()

    _press(scene, pygame.K_l)

    assert scene._legend_open is True


def test_the_open_legend_swallows_action_keys() -> None:
    scene = _scene_at_the_action_menu()
    _press(scene, pygame.K_l)

    _press(scene, ACTION_KEYS[0])
    _press(scene, pygame.K_RETURN)

    assert scene._pending_action_index is None
    assert scene._legend_open is True


@pytest.mark.parametrize("key", [pygame.K_l, pygame.K_ESCAPE])
def test_legend_closes_on_its_own_key_or_escape(key: int) -> None:
    scene = _scene_at_the_action_menu()
    _press(scene, pygame.K_l)

    _press(scene, key)

    assert scene._legend_open is False


def test_legend_key_is_ignored_while_a_reveal_is_playing() -> None:
    scene = _scene_at_the_action_menu()
    _press(scene, ACTION_KEYS[0])
    scene.update(0.016)
    assert scene._current_phases or scene._pending_events

    _press(scene, pygame.K_l)

    assert scene._legend_open is False


def test_draw_with_the_legend_open_does_not_raise() -> None:
    scene = _scene_at_the_action_menu()
    scene._player_displayed.active_effects.add((EffectCategory.BATTLE, EffectName.FIBROUS))
    _press(scene, pygame.K_l)

    scene.draw(pygame.Surface(_WINDOW_SIZE))


def test_legend_key_is_ignored_once_an_action_is_committed_in_the_same_frame() -> None:
    scene = _scene_at_the_action_menu()

    _press(scene, ACTION_KEYS[0])
    _press(scene, pygame.K_l)

    assert scene._legend_open is False
