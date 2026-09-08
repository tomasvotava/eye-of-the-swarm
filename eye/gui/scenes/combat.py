"""CombatScene: the first real consumer of `Battle.turn_phase` (ADR 0008/0009). A frame-based main
loop can't block on player input the way the TUI's `play_battle` does, so `update()` drives
whatever step `battle.turn_phase` is ready for on each call -- resolving automatic steps on its
own and surfacing an action menu only once the player actually needs to choose. On `battle.is_over`
it reports a bare `BattleConcluded()` and takes no further action -- `GameDriver` (ADR 0010) is the
one that reads `generation.died` and decides whether that means a return to exploration or a trip
to the skill tree, mirroring `eye/tui/combat.py::play_battle()`, which never decides that either.
"""

from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum, StrEnum
from typing import assert_never

import pygame
import pygame.typing

from eye.combat.battle import Battle, PlayerTurnNeedsAction, TurnPhase
from eye.combat.effects import EffectCategory, EffectName
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
from eye.combat.stats import Combatant
from eye.exploration.events import EnemyEncountered
from eye.gui.animation import AnimationClip, Animator, scale_clip, scale_sprite
from eye.gui.assets import SpriteAtlas, SpriteKey
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.play_scene import BattleConcluded, PlaySceneTransition
from eye.gui.tuning import BATTLE_DEATH_POSE_HOLD_SECONDS, BATTLE_VALUE_TWEEN_SECONDS
from eye.gui.widgets import BuffIcon, TextBuffIcon
from eye.session.generation import Generation

_FONT_SIZE = 20
_MARGIN = 8
_GAP = 4
_BAR_WIDTH = 230
_BAR_HEIGHT = 16
_METER_HEIGHT = 8
_BUFF_ICON_STEP = 90
_COMBATANT_SCALE_FACTOR = 3
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_BAR_BG_COLOR: pygame.typing.ColorLike = "dimgray"
_HP_COLOR: pygame.typing.ColorLike = "firebrick"
_METER_COLOR: pygame.typing.ColorLike = "gold"
_CURSOR_COLOR: pygame.typing.ColorLike = "slategray"  # matches SkillTreeScene's cursor highlight

# Direct numbered-key select, mirroring the TUI's numbered-menu convention (ADR 0009) -- unlike
# ExplorationScene/SkillTreeScene, the action set here is a variable-length list from the domain,
# not a fixed enum, so a static key->action-kind mapping doesn't fit. Up/Down + Enter (handled
# directly in handle_pygame_event()) offer the same choice via a cursor instead.
ACTION_KEYS: tuple[int, ...] = (
    pygame.K_1,
    pygame.K_2,
    pygame.K_3,
    pygame.K_4,
    pygame.K_5,
    pygame.K_6,
    pygame.K_7,
    pygame.K_8,
    pygame.K_9,
)


def _label(value: Enum) -> str:
    return value.name.replace("_", " ").title()


def _duration(category: EffectCategory, remaining_turns: int | None) -> str:
    if category is EffectCategory.LIFESPAN:
        return " for this generation"
    if remaining_turns is None:
        return " until the battle ends"
    return f" for {remaining_turns} turn{'s' if remaining_turns != 1 else ''}"


def _resolve_enemy_sprite_key(strain_name: str) -> SpriteKey:
    # Assumes a same-named SpriteKey per Strain -- ENCOUNTERABLE_STRAINS and SpriteKey's enemy
    # members must be kept in sync, or this needs a real Strain -> SpriteKey mapping instead.
    # Falls back to the "missing texture" placeholder rather than crashing the scene if the two
    # ever drift apart.
    try:
        return SpriteKey[strain_name]
    except KeyError:
        return SpriteKey.UNKNOWN


def _describe_event(event: BattleEvent) -> str:
    match event:
        case Death(combatant=combatant):
            return f"{combatant.name} falls."
        case Revive(combatant=combatant, revived_hp=revived_hp):
            return f"{combatant.name} revives with {revived_hp} HP!"
        case TurnSkipped(combatant=combatant):
            return f"{combatant.name}'s turn is skipped."
        case ActionChosen(actor=actor, action=action, was_swapped_by_clouded_judgement=swapped):
            suffix = " (clouded judgement!)" if swapped else ""
            return f"{actor.name} uses {_label(action)}{suffix}."
        case HitLanded(source=source, target=target, action=action, damage=damage, target_hp_after=target_hp_after):
            return f"{source.name}'s {_label(action)} hits {target.name} for {damage} -- {target_hp_after} HP left."
        case HitReflected(source=source, target=target, damage=damage, target_hp_after=target_hp_after):
            return f"{source.name} reflects {damage} back at {target.name} -- {target_hp_after} HP left."
        case SelfDamageTaken(combatant=combatant, damage=damage, combatant_hp_after=combatant_hp_after):
            return f"{combatant.name} takes {damage} recoil damage -- now at {combatant_hp_after} HP."
        case EffectApplied(target=target, effect=effect, category=category, remaining_turns=remaining_turns):
            return f"{target.name} is affected by {_label(effect)}{_duration(category, remaining_turns)}."
        case EffectExpired(target=target, effect=effect):
            return f"{_label(effect)} wears off {target.name}."
        case DotTicked(target=target, effect=effect, damage=damage, target_hp_after=target_hp_after):
            return f"{target.name} takes {damage} {_label(effect)} damage -- now at {target_hp_after} HP."
        case HealApplied(target=target, effect=effect, amount=amount, target_hp_after=target_hp_after):
            return f"{target.name} heals {amount} HP from {_label(effect)} -- now at {target_hp_after} HP."
        case ExtraActionTriggered(actor=actor):
            return f"{actor.name} acts again!"
        case MeterFilled(combatant=combatant, meter_after=meter_after):
            return f"{combatant.name}'s swarm meter fills (now {meter_after})."
        case MeterConsumed(combatant=combatant):
            return f"{combatant.name}'s swarm meter empties."
        case BattleEnded(winner=winner):
            return f"{winner.name} wins the battle!" if winner is not None else "The battle ends in a draw."
        case _:
            assert_never(event)


@dataclass(frozen=True, slots=True)
class Phase:
    """One step of a `BattleEvent`'s reveal (ADR 0013): `duration_seconds` of 0 completes in the
    same driver tick it starts, letting a batch of phase-less/instant events cascade through a
    single `update()` call for free, while a phase with real duration blocks across calls.
    """

    duration_seconds: float
    on_start: Callable[[], None] = lambda: None
    on_progress: Callable[[float], None] = lambda fraction: None
    on_complete: Callable[[], None] = lambda: None


class CombatAnimationState(StrEnum):
    """Combat-facing animation states (ADR 0013) -- distinct from `dev_assets.py`'s preview-only
    `EnemyAnimationState`, per that module's own docstring."""

    IDLE = "idle"
    ATTACK = "attack"
    HIT = "hit"
    DEAD = "dead"


class _LoadedCombatAnimationState(StrEnum):
    """The subset of `CombatAnimationState` backed by an actual animated clip on disk -- used only
    as the `state_type` argument to `atlas.get_animation_set()`, which is all-or-nothing (raises if
    any member has no matching clip). `DEAD` is deliberately excluded: it's a single static pose
    (`dead.png`, no `.json` manifest -- a still frame has no meaningful fps), loaded as a named
    variant instead and merged in separately by `_build_combat_animator`."""

    IDLE = "idle"
    ATTACK = "attack"
    HIT = "hit"


class _DeadVariant(StrEnum):
    """The single static-pose variant name `_build_combat_animator` resolves via
    `atlas.get_variant_set()` -- a one-member enum exists purely to satisfy that method's
    enum-typed contract."""

    DEAD = "dead"


def _build_combat_animator(
    atlas: SpriteAtlas, key: SpriteKey, scale_factor: float = 1
) -> Animator[CombatAnimationState] | None:
    """Returns `None` for a key with no animation clips at all -- the static-sprite fallback path
    BRAMBLE/UNKNOWN and any `build_placeholder_atlas()`-based test takes. Otherwise builds the
    full 4-state clip set: `IDLE`/`ATTACK`/`HIT` loaded from disk (with `loop=False` forced onto
    the one-shot `ATTACK`/`HIT` clips -- `build_art_atlas` itself only sets `loop=True` defaults,
    per ADR 0013), `DEAD` synthesized as a one-frame `loop=False` clip from the static `dead.png`
    variant. Every frame is scaled by `scale_factor` here, once, rather than on every draw() call.
    """
    if not atlas.has_animation_set(key):
        return None
    loaded = atlas.get_animation_set(key, _LoadedCombatAnimationState)
    clips: dict[CombatAnimationState, AnimationClip] = {
        CombatAnimationState.IDLE: loaded[_LoadedCombatAnimationState.IDLE],
        CombatAnimationState.ATTACK: replace(loaded[_LoadedCombatAnimationState.ATTACK], loop=False),
        CombatAnimationState.HIT: replace(loaded[_LoadedCombatAnimationState.HIT], loop=False),
    }
    dead_surface = atlas.get_variant_set(key, _DeadVariant)[_DeadVariant.DEAD]
    # frame_duration_seconds is otherwise inert for a single-frame clip (Animator.update() freezes
    # before ever comparing elapsed time against it) -- the real hold comes from Death's own Phase
    # duration (BATTLE_DEATH_POSE_HOLD_SECONDS). Any positive value satisfies AnimationClip here.
    clips[CombatAnimationState.DEAD] = AnimationClip(
        frames=(dead_surface,), frame_duration_seconds=BATTLE_DEATH_POSE_HOLD_SECONDS, loop=False
    )
    clips = {state: scale_clip(clip, scale_factor) for state, clip in clips.items()}
    return Animator(clips, initial_state=CombatAnimationState.IDLE)


@dataclass(slots=True)
class DisplayedCombatantState:
    """What `_draw_combatant` actually renders (ADR 0013) -- mutated only by `Phase` callbacks,
    never read live off `Combatant` once the battle is underway. Float `hp`/`meter` let `on_progress`
    interpolate smoothly; rounded only at draw time."""

    hp: float
    meter: float
    active_effects: set[EffectName] = field(default_factory=set)


def _displayed_state_from(combatant: Combatant) -> DisplayedCombatantState:
    return DisplayedCombatantState(
        hp=float(combatant.current_hp),
        meter=float(combatant.current_meter),
        active_effects={name for name in EffectName if combatant.effects.has(name)},
    )


def _hp_tween_phase(displayed: DisplayedCombatantState, end_hp: int) -> Phase:
    # start is captured eagerly here, not in on_start: _phases_for runs synchronously when the
    # triggering event is dequeued, by which point every earlier event's phases (including their
    # own tweens' on_complete snaps) have already fully run -- so displayed.hp is always accurate
    # at this exact moment. See ADR 0013 / CombatScene._advance_phases for why only one event's
    # phases are ever active at a time.
    start = displayed.hp
    end = float(end_hp)

    def on_progress(fraction: float) -> None:
        displayed.hp = start + (end - start) * fraction

    def on_complete() -> None:
        displayed.hp = end  # snap to the exact value; avoids float drift from interpolation

    return Phase(duration_seconds=BATTLE_VALUE_TWEEN_SECONDS, on_progress=on_progress, on_complete=on_complete)


def _meter_tween_phase(displayed: DisplayedCombatantState, end_meter: int) -> Phase:
    # Same shape and duration as _hp_tween_phase -- see that function's comment for why capturing
    # start eagerly here is safe.
    start = displayed.meter
    end = float(end_meter)

    def on_progress(fraction: float) -> None:
        displayed.meter = start + (end - start) * fraction

    def on_complete() -> None:
        displayed.meter = end  # snap to the exact value; avoids float drift from interpolation

    return Phase(duration_seconds=BATTLE_VALUE_TWEEN_SECONDS, on_progress=on_progress, on_complete=on_complete)


class CombatScene:
    def __init__(
        self,
        generation: Generation,
        encounter: EnemyEncountered,
        atlas: SpriteAtlas,
        buff_icon_factory: Callable[[EffectName], BuffIcon] = TextBuffIcon,
    ) -> None:
        self._generation = generation
        self._atlas = atlas
        self._buff_icon_factory = buff_icon_factory
        self._enemy_sprite_key = _resolve_enemy_sprite_key(encounter.strain.name)
        self._battle: Battle = generation.start_battle(encounter)
        self._pending_query: PlayerTurnNeedsAction | None = None
        self._pending_action_index: int | None = None
        self._cursor_index = 0
        self._log: list[str] = []
        self._pending_events: deque[BattleEvent] = deque()
        self._current_phases: deque[Phase] = deque()
        self._phase_elapsed: float = 0.0
        self._phase_started: bool = False
        self._player_animator = _build_combat_animator(atlas, SpriteKey.PLAYER, _COMBATANT_SCALE_FACTOR)
        self._enemy_animator = _build_combat_animator(atlas, self._enemy_sprite_key, _COMBATANT_SCALE_FACTOR)
        # Fallback for a key with no animation clips at all (e.g. BRAMBLE/UNKNOWN, or a
        # build_placeholder_atlas()-based test) -- scaled once here rather than on every draw().
        self._player_static_sprite = scale_sprite(atlas.get(SpriteKey.PLAYER), _COMBATANT_SCALE_FACTOR)
        self._enemy_static_sprite = scale_sprite(atlas.get(self._enemy_sprite_key), _COMBATANT_SCALE_FACTOR)
        # Seeded before battle.start()'s own events are queued (ADR 0013) -- displayed state must
        # reflect pre-battle values until start()'s events (e.g. a Resonance meter prefill) are
        # actually revealed, not whatever start() already mutated live Combatant state to.
        self._player_displayed = _displayed_state_from(self._battle.player)
        self._enemy_displayed = _displayed_state_from(self._battle.enemy)
        self._queue_events(self._battle.start())

    def _animator_for(self, combatant: Combatant) -> Animator[CombatAnimationState] | None:
        return self._player_animator if combatant is self._battle.player else self._enemy_animator

    def _displayed_for(self, combatant: Combatant) -> DisplayedCombatantState:
        return self._player_displayed if combatant is self._battle.player else self._enemy_displayed

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type != pygame.KEYDOWN or self._pending_query is None:
            return
        if self._current_phases or self._pending_events:
            return  # menu interactivity withheld while a reveal is still playing (ADR 0013)
        available = self._pending_query.available
        if pygame_event.key in ACTION_KEYS:
            index = ACTION_KEYS.index(pygame_event.key)
            if index < len(available):
                self._pending_action_index = index
        elif pygame_event.key == pygame.K_UP:
            self._cursor_index = (self._cursor_index - 1) % len(available)
        elif pygame_event.key == pygame.K_DOWN:
            self._cursor_index = (self._cursor_index + 1) % len(available)
        elif pygame_event.key == pygame.K_RETURN:
            self._pending_action_index = self._cursor_index

    def update(self, dt: float) -> PlaySceneTransition | None:
        # Ticks every real frame regardless of which phase (if any) is active (ADR 0013) -- not
        # folded into _advance_phases, which can run its zero-duration cascade loop more than once
        # per call and must not tick an animator's real elapsed time more than once per frame.
        if self._player_animator is not None:
            self._player_animator.update(dt)
        if self._enemy_animator is not None:
            self._enemy_animator.update(dt)
        self._advance_phases(dt)
        if self._current_phases or self._pending_events:
            # Gating invariant (ADR 0013): the next domain call and the BattleConcluded
            # transition are both withheld until everything already returned has been revealed.
            return None
        if self._battle.is_over:
            return self._conclude()
        turn_phase = self._battle.turn_phase
        if turn_phase is TurnPhase.AWAITING_QUERY:
            self._advance_query()
        elif turn_phase is TurnPhase.AWAITING_PLAYER_ACTION:
            self._resolve_pending_action()
        elif turn_phase is TurnPhase.AWAITING_ENEMY_TURN:
            self._queue_events(self._battle.resolve_enemy_turn())
        # Starts (without necessarily finishing) the freshly queued batch's first phase within
        # this same call, rather than needing a dedicated "first event reveals immediately" flag.
        self._advance_phases(0.0)
        return None

    def _advance_query(self) -> None:
        query = self._battle.query_player_turn()
        if isinstance(query, PlayerTurnNeedsAction):
            self._queue_events(query.pre_turn_events)
            self._pending_query = query
            self._cursor_index = 0
        else:
            self._queue_events(query.events)

    def _resolve_pending_action(self) -> None:
        if self._pending_query is None or self._pending_action_index is None:
            return
        action = self._pending_query.available[self._pending_action_index]
        self._pending_query = None
        self._pending_action_index = None
        self._queue_events(self._battle.resolve_player_turn(action))

    def _conclude(self) -> PlaySceneTransition:
        self._generation.finish_battle(self._battle)
        return BattleConcluded()

    def _queue_events(self, events: Sequence[BattleEvent]) -> None:
        self._pending_events.extend(events)

    def _start_next_event(self) -> None:
        event = self._pending_events.popleft()
        self._log.append(_describe_event(event))
        self._current_phases = deque(self._phases_for(event))

    def _advance_phases(self, dt: float) -> None:
        while True:
            if not self._current_phases:
                if not self._pending_events:
                    return
                self._start_next_event()
                # _phases_for(event) can legitimately return [] -- re-check from the top rather
                # than indexing into what may still be an empty deque, so an all-empty batch
                # cascades through pending_events in one call.
                continue
            phase = self._current_phases[0]
            if not self._phase_started:
                # A dedicated flag, not `self._phase_elapsed == 0.0` -- a phase that starts via
                # this same loop's leftover zeroed `dt` (see below) can still have zero elapsed
                # time when the *next* call re-enters here, which would re-fire on_start() for a
                # phase already in progress. The flag tracks "has on_start run", not "is elapsed
                # currently zero", so it can't be fooled by that coincidence.
                phase.on_start()
                self._phase_started = True
            self._phase_elapsed += dt
            fraction = 1.0 if phase.duration_seconds <= 0 else min(1.0, self._phase_elapsed / phase.duration_seconds)
            phase.on_progress(fraction)
            if self._phase_elapsed < phase.duration_seconds:
                return
            phase.on_complete()
            self._current_phases.popleft()
            self._phase_elapsed = 0.0
            self._phase_started = False
            dt = 0.0  # a completed phase's leftover time is not carried into the next one

    def _swing_phase(self, source: Combatant, target: Combatant) -> Phase:
        # Drives both animators from one Phase (ADR 0013) -- no separate "windup" event needed
        # even for a multi-hit combo, since animators tick unconditionally every frame regardless
        # of which phase is active.
        source_animator = self._animator_for(source)
        target_animator = self._animator_for(target)
        source_duration = source_animator.duration_of(CombatAnimationState.ATTACK) if source_animator else 0.0
        target_duration = target_animator.duration_of(CombatAnimationState.HIT) if target_animator else 0.0

        def on_start() -> None:
            if source_animator is not None:
                source_animator.set_state(CombatAnimationState.ATTACK)
            if target_animator is not None:
                target_animator.set_state(CombatAnimationState.HIT)

        def on_complete() -> None:
            if source_animator is not None:
                source_animator.set_state(CombatAnimationState.IDLE)
            if target_animator is not None:
                target_animator.set_state(CombatAnimationState.IDLE)

        return Phase(duration_seconds=max(source_duration, target_duration), on_start=on_start, on_complete=on_complete)

    def _reaction_phase(self, combatant: Combatant) -> Phase:
        # Target-only treatment for a reflect/recoil hit (ADR 0013) -- no attacker swing to drive.
        animator = self._animator_for(combatant)
        duration = animator.duration_of(CombatAnimationState.HIT) if animator else 0.0

        def on_start() -> None:
            if animator is not None:
                animator.set_state(CombatAnimationState.HIT)

        def on_complete() -> None:
            if animator is not None:
                animator.set_state(CombatAnimationState.IDLE)

        return Phase(duration_seconds=duration, on_start=on_start, on_complete=on_complete)

    def _phases_for(self, event: BattleEvent) -> list[Phase]:
        # EffectApplied/EffectExpired/TurnSkipped/ExtraActionTriggered/BattleEnded/DotTicked/
        # HealApplied are deliberately phase-less for now -- they get Announcement/Overlay
        # treatments per ADR 0013 once those land. ActionChosen is permanently phase-less.
        match event:
            case ActionChosen():
                return []
            case Death(combatant=combatant):
                animator = self._animator_for(combatant)
                displayed = self._displayed_for(combatant)

                def on_start() -> None:
                    # Defensive snap, not an assumption that a preceding event already tweened HP
                    # correctly -- a DotTicked- or Wilty-triggered death has no such predecessor
                    # (DotTicked's own phase is still [] here; Wilty sets current_hp with no event
                    # at all). _handle_potential_death only ever fires Death once current_hp <= 0.
                    displayed.hp = float(max(0, combatant.current_hp))
                    if animator is not None:
                        animator.set_state(CombatAnimationState.DEAD)

                return [Phase(duration_seconds=BATTLE_DEATH_POSE_HOLD_SECONDS, on_start=on_start)]
            case Revive(combatant=combatant, revived_hp=revived_hp):
                animator = self._animator_for(combatant)

                def on_start() -> None:
                    if animator is not None:
                        animator.set_state(CombatAnimationState.IDLE)

                return [
                    Phase(duration_seconds=0.0, on_start=on_start),
                    _hp_tween_phase(self._displayed_for(combatant), revived_hp),
                ]
            case TurnSkipped():
                return []
            case EffectApplied():
                return []
            case EffectExpired():
                return []
            case ExtraActionTriggered():
                return []
            case BattleEnded():
                return []
            case MeterFilled(combatant=combatant, meter_after=meter_after):
                return [_meter_tween_phase(self._displayed_for(combatant), meter_after)]
            case MeterConsumed(combatant=combatant, meter_after=meter_after):
                return [_meter_tween_phase(self._displayed_for(combatant), meter_after)]
            case HitLanded(source=source, target=target, target_hp_after=target_hp_after):
                return [
                    self._swing_phase(source, target),
                    _hp_tween_phase(self._displayed_for(target), target_hp_after),
                ]
            case HitReflected(target=target, target_hp_after=target_hp_after):
                return [self._reaction_phase(target), _hp_tween_phase(self._displayed_for(target), target_hp_after)]
            case SelfDamageTaken(combatant=combatant, combatant_hp_after=combatant_hp_after):
                return [
                    self._reaction_phase(combatant),
                    _hp_tween_phase(self._displayed_for(combatant), combatant_hp_after),
                ]
            case DotTicked():
                return []
            case HealApplied():
                return []
            case _:
                assert_never(event)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        self._draw_combatant(
            surface,
            self._battle.player,
            self._player_static_sprite,
            self._player_animator,
            self._player_displayed,
            mirrored=False,
        )
        self._draw_combatant(
            surface,
            self._battle.enemy,
            self._enemy_static_sprite,
            self._enemy_animator,
            self._enemy_displayed,
            mirrored=True,
        )
        self._draw_menu(surface)

    def _draw_combatant(
        self,
        surface: pygame.Surface,
        combatant: Combatant,
        static_sprite: pygame.Surface,
        animator: Animator[CombatAnimationState] | None,
        displayed: DisplayedCombatantState,
        *,
        mirrored: bool,
    ) -> None:
        # mirrored=True anchors the whole panel to the surface's right edge instead of the left,
        # so the player and enemy sit on opposite sides of the screen facing each other.
        font = get_font(GameFont.ITHACA, _FONT_SIZE)
        sprite = animator.current_frame() if animator is not None else static_sprite
        sprite_y = surface.height // 2 - sprite.height // 2
        top = _MARGIN
        if mirrored:
            sprite_x = surface.get_width() // 4 * 3 - sprite.width // 2
            bars_x = surface.get_width() - _MARGIN
            bar_right = bars_x - _GAP
            bar_left = bar_right - _BAR_WIDTH
        else:
            sprite_x = surface.get_width() // 4 - sprite.width // 2
            bars_x = _MARGIN
            bar_left = bars_x + _GAP
            bar_right = bar_left + _BAR_WIDTH
        surface.blit(sprite, (sprite_x, sprite_y))

        name = font.render(combatant.name, True, _TEXT_COLOR)
        name_x = bar_right - name.get_width() if mirrored else bar_left
        surface.blit(name, (name_x, top))

        current_hp = max(0.0, displayed.hp)
        hp_rect = pygame.Rect(bar_left, top + _FONT_SIZE, _BAR_WIDTH, _BAR_HEIGHT)
        self._draw_bar(surface, hp_rect, current_hp / combatant.base_stats.max_hp, _HP_COLOR)
        hp_label = font.render(f"{round(current_hp)}/{combatant.base_stats.max_hp}", True, _TEXT_COLOR)
        hp_label_x = hp_rect.left - _GAP - hp_label.get_width() if mirrored else hp_rect.right + _GAP
        surface.blit(hp_label, (hp_label_x, hp_rect.top))

        meter_rect = pygame.Rect(bar_left, hp_rect.bottom + _GAP, _BAR_WIDTH, _METER_HEIGHT)
        self._draw_bar(
            surface, meter_rect, max(0.0, displayed.meter) / combatant.base_stats.meter_capacity, _METER_COLOR
        )
        # Buff icons deliberately still read live Combatant state, not DisplayedCombatantState:
        # EffectApplied/EffectExpired are still phase-less (their Announcement treatment is
        # pending per ADR 0013), so switching this over now would freeze the row at its
        # construction-time snapshot for the whole battle -- worse than an always-live read.
        icon_row_x = bar_right if mirrored else bar_left
        self._draw_buff_icons(surface, combatant, (icon_row_x, meter_rect.bottom + _GAP), mirrored=mirrored)

    def _draw_bar(
        self, surface: pygame.Surface, rect: pygame.Rect, ratio: float, color: pygame.typing.ColorLike
    ) -> None:
        pygame.draw.rect(surface, _BAR_BG_COLOR, rect)
        filled = rect.copy()
        filled.width = round(rect.width * min(1.0, max(0.0, ratio)))
        pygame.draw.rect(surface, color, filled)

    def _draw_buff_icons(
        self, surface: pygame.Surface, combatant: Combatant, pos: tuple[int, int], *, mirrored: bool
    ) -> None:
        active = [name for name in EffectName if combatant.effects.has(name)]
        x, y = pos
        if mirrored:
            # pos.x is the row's right edge on the mirrored side; the BuffIcon protocol exposes
            # no width to right-align each icon individually, so shift the whole row's start left
            # by its total width instead and step forward as usual -- the row still ends flush at
            # pos.x rather than growing off the sprite/surface edge.
            x -= _BUFF_ICON_STEP * len(active)
        for name in active:
            self._buff_icon_factory(name).render(surface, pygame.Vector2(x, y))
            x += _BUFF_ICON_STEP

    def _draw_menu(self, surface: pygame.Surface) -> None:
        if self._pending_query is None:
            return
        font = get_font(GameFont.ITHACA, _FONT_SIZE)
        available = self._pending_query.available
        menu_height = (len(available) + 1) * _FONT_SIZE  # +1 for the control hint below the rows
        top = surface.get_height() - menu_height - _MARGIN
        for index, action in enumerate(available):
            row = pygame.Rect(_MARGIN, top + index * _FONT_SIZE, _BAR_WIDTH, _FONT_SIZE)
            if index == self._cursor_index:
                pygame.draw.rect(surface, _CURSOR_COLOR, row)
            label = f"{index + 1}) {action.name or action.kind.name.replace('_', ' ').title()}"
            surface.blit(font.render(label, True, _TEXT_COLOR), row.topleft)
        hint = font.render("1-9: choose   Up/Down + Enter: choose", True, _TEXT_COLOR)
        surface.blit(hint, (_MARGIN, top + len(available) * _FONT_SIZE))
