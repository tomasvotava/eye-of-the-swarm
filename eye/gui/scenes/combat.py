"""CombatScene: the first real consumer of `Battle.turn_phase` (ADR 0008/0009). A frame-based main
loop can't block on player input the way the TUI's `play_battle` does, so `update()` drives
whatever step `battle.turn_phase` is ready for on each call -- resolving automatic steps on its
own and surfacing an action menu only once the player actually needs to choose. On `battle.is_over`
it reports a bare `BattleConcluded()` and takes no further action -- `GameDriver` (ADR 0010) is the
one that reads `generation.died` and decides whether that means a return to exploration or a trip
to the skill tree, mirroring `eye/tui/combat.py::play_battle()`, which never decides that either.
"""

import math
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum, StrEnum, auto
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
from eye.gui.effect_card import EffectCard, card_column_width, draw_effect_card
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.play_scene import BattleConcluded, PlaySceneTransition
from eye.gui.tuning import (
    BATTLE_ACTING_HIGHLIGHT_COLOR,
    BATTLE_ANNOUNCEMENT_HOLD_SECONDS,
    BATTLE_BUFF_ICON_HOP_DURATION_SECONDS,
    BATTLE_BUFF_ICON_HOP_PIXELS,
    BATTLE_DEATH_POSE_HOLD_SECONDS,
    BATTLE_HIGHLIGHT_PULSE_PERIOD_SECONDS,
    BATTLE_HIGHLIGHT_PULSE_STRENGTH,
    BATTLE_HIT_FLASH_DAMAGE_COLOR,
    BATTLE_HIT_FLASH_DURATION_SECONDS,
    BATTLE_HIT_FLASH_HEALING_COLOR,
    BATTLE_HIT_FLASH_STRENGTH,
    BATTLE_RECEIVING_HIGHLIGHT_COLOR,
    BATTLE_VALUE_TWEEN_SECONDS,
)
from eye.gui.widgets import EFFECT_DESCRIPTIONS, BuffIcon, SpriteBuffIcon
from eye.session.generation import Generation

_FONT_SIZE = 20
# The single centered line of a plain announcement. Deliberately the same size as an effect card's
# description, so the two read at the same weight -- this one running the screen's width, the
# card's wrapped inside its column.
_ANNOUNCEMENT_FONT_SIZE = 28
_MARGIN = 8
_GAP = 4
_BAR_WIDTH = 230
_BAR_HEIGHT = 16
_METER_HEIGHT = 8
_BUFF_ICON_SIZE = 28
_BUFF_ICON_STEP = 36
_BUFF_ICON_DURATION_FONT_SIZE = 12
# The _GAP _draw_combatant leaves under the meter bar is all the headroom a hopping icon has, so
# raising BATTLE_BUFF_ICON_HOP_PIXELS past it is inert instead of a collision.
_BUFF_ICON_HOP_CEILING = _GAP
_OVERLAY_ICON_SIZE = 40
# _draw_overlay's layout needs both label lines plus their gap to fit inside _OVERLAY_ICON_SIZE.
_OVERLAY_LABEL_FONT_SIZE = 16
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


def _duration_subtitle(category: EffectCategory, remaining_turns: int | None) -> str:
    # Standalone phrasing for the effect-announcement card's subtitle line, as opposed to
    # _duration()'s mid-sentence connective form used by _describe_event's log line.
    if category is EffectCategory.LIFESPAN:
        return "This generation"
    if remaining_turns is None:
        return "Until battle ends"
    return f"{remaining_turns} turn{'s' if remaining_turns != 1 else ''}"


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
    variant. Every frame is scaled by `scale_factor` up front, once, since an entity's scale is
    fixed for the animator's lifetime.
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


class HitValence(Enum):
    """Whether the moment landing on a combatant helped or hurt them. Taken from the event, never
    from `EFFECT_POLARITY`: Spiky Skin is a buff whose `HitReflected` damages the combatant flashed."""

    DAMAGE = auto()
    HEALING = auto()


@dataclass(frozen=True, slots=True)
class HitFlash:
    """A sprite flash in flight: when the blow landed, and which way it went."""

    started_at: float
    valence: HitValence


def _valence_color(valence: HitValence) -> pygame.typing.ColorLike:
    """The colour a `HitValence` speaks in, read by both the sprite flash and the overlay label."""
    match valence:
        case HitValence.DAMAGE:
            return BATTLE_HIT_FLASH_DAMAGE_COLOR
        case HitValence.HEALING:
            return BATTLE_HIT_FLASH_HEALING_COLOR
        case _:
            assert_never(valence)


@dataclass(slots=True)
class DisplayedCombatantState:
    """What `_draw_combatant` actually renders (ADR 0013) -- mutated only by `Phase` callbacks,
    never read live off `Combatant` once the battle is underway. Float `hp`/`meter` let `on_progress`
    interpolate smoothly; rounded only at draw time."""

    hp: float
    meter: float
    # Keyed by (category, name), not just name: PROJECT_BRIEF.md §5.6's refresh-not-stack rule is
    # scoped per category -- a Lifespan Fibrous and a Battle Fibrous are tracked (and can both be
    # active) independently, so a name-only set would conflate them.
    active_effects: set[tuple[EffectCategory, EffectName]] = field(default_factory=set)
    # HUD-row countdown display, same keying as active_effects. None means "no number" (Lifespan,
    # or an indefinite Battle effect) -- not "unknown". A GUI-side approximation, not read from
    # Battle: the domain reports an effect's *expiry* (EffectExpired) but never "still active, N
    # turns left" for one that isn't expiring, so _tick_displayed_battle_effect_durations mirrors
    # the one call site (Battle.resolve_enemy_turn) where the domain actually ticks Battle-scoped
    # durations, rather than reading Combatant.effects live (ADR 0013's invariant).
    remaining_turns: dict[tuple[EffectCategory, EffectName], int | None] = field(default_factory=dict)
    # The last impact and what it did, or None while nothing flashes. Per-combatant because
    # PhaseFocus.receiving also covers heals, revives and deaths, which are not impacts.
    hit_flash: HitFlash | None = None
    # Scene-clock reading of each effect's tick hop; an absent key means that icon is at rest.
    # Keyed by EffectName alone to match the row, which draws one icon per name whatever category.
    effect_tick_started_at: dict[EffectName, float] = field(default_factory=dict)


def _displayed_state_from(combatant: Combatant) -> DisplayedCombatantState:
    active_effects = {
        (category, name)
        for category in EffectCategory
        for name in EffectName
        if combatant.effects.has(name, category=category)
    }
    return DisplayedCombatantState(
        hp=float(combatant.current_hp),
        meter=float(combatant.current_meter),
        active_effects=active_effects,
        # Seeded None for every key, not read off the live effect: correct as-is, not just
        # expedient -- a fresh Battle can only start with pre-existing Lifespan effects (Battle
        # effects are only ever granted by events during this battle, none can predate it), and
        # Lifespan always displays blank (per _duration_subtitle), so no seeded key ever needs a
        # real number.
        remaining_turns=dict.fromkeys(active_effects),
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


def _discard_displayed_effect(displayed: DisplayedCombatantState, key: tuple[EffectCategory, EffectName]) -> None:
    displayed.active_effects.discard(key)
    displayed.remaining_turns.pop(key, None)


@dataclass(frozen=True, slots=True)
class CombatantLayout:
    """Where one combatant's sprite and HUD panel sit on a surface.

    `mirrored` says which of `bar_left`/`bar_right` is the panel's outer edge, and so which way
    content anchored to the panel grows.
    """

    mirrored: bool
    sprite_center: tuple[int, int]
    bar_left: int
    bar_right: int

    def sprite_topleft(self, sprite: pygame.Surface) -> tuple[int, int]:
        """Blit position that centers `sprite` on `sprite_center`."""
        return (self.sprite_center[0] - sprite.width // 2, self.sprite_center[1] - sprite.height // 2)


def _combatant_layout(surface: pygame.Surface, *, mirrored: bool) -> CombatantLayout:
    # mirrored=True hangs the panel off the right edge, so the two sides face each other.
    if mirrored:
        sprite_center_x = surface.get_width() // 4 * 3
        bars_x = surface.get_width() - _MARGIN
        bar_right = bars_x - _GAP
        bar_left = bar_right - _BAR_WIDTH
    else:
        sprite_center_x = surface.get_width() // 4
        bars_x = _MARGIN
        bar_left = bars_x + _GAP
        bar_right = bar_left + _BAR_WIDTH
    return CombatantLayout(
        mirrored=mirrored,
        sprite_center=(sprite_center_x, surface.get_height() // 2),
        bar_left=bar_left,
        bar_right=bar_right,
    )


def _lit_by_hit_flash(sprite: pygame.Surface, strength: float, valence: HitValence) -> pygame.Surface:
    """A copy of `sprite` with `strength` (0-1) of `valence`'s tint driven into its pixels.
    Copied because an animator's frames are shared by every draw of that clip."""
    color = pygame.Color(_valence_color(valence))
    lit = sprite.copy()
    # Multiply before adding: addition alone can only brighten, so on a light pixel every channel
    # clips and the hue is lost. White is the multiply's neutral, so strength 0 is an identity.
    multiplier = pygame.Color("white").lerp(color, strength)
    # RGB, not RGBA, on both fills: alpha too would light up the sprite's transparent margin.
    lit.fill((multiplier.r, multiplier.g, multiplier.b), special_flags=pygame.BLEND_RGB_MULT)
    lit.fill(
        (round(color.r * strength), round(color.g * strength), round(color.b * strength)),
        special_flags=pygame.BLEND_RGB_ADD,
    )
    return lit


@dataclass(frozen=True, slots=True)
class AnchoredCard:
    """An `EffectCard` and the combatant it landed on, carried as one value: draw() picks the half
    to centre the card over by that combatant's identity, so a card without one would anchor over
    the wrong side instead of failing."""

    card: EffectCard
    target: Combatant


@dataclass(frozen=True, slots=True)
class Announcement:
    """Icon + short text treatment (ADR 0013). Doubles as both a Phase's payload and
    `CombatScene`'s displayed announcement state -- mirrors `DisplayedCombatantState`'s dual role
    as "what a phase mutates" and "what draw() reads", just replaced wholesale on each transition
    rather than tweened field-by-field, since an announcement has no partial-progress value.

    `text` is the sole line for a plain announcement (`card` is `None`); `card` is the anchored
    effect-card block, drawn over its own combatant's half instead.
    """

    text: str = ""
    card: AnchoredCard | None = None


@dataclass(frozen=True, slots=True)
class Overlay:
    """The target-local counterpart to `Announcement` (ADR 0013): an icon and label drawn at `target`.
    `valence` is the same value the target's sprite flash uses, since a clamped hp_delta of 0 has no
    sign to colour by."""

    target: Combatant
    effect: EffectName
    hp_delta: int
    valence: HitValence


def _overlay_label_lines(overlay: Overlay) -> tuple[str, str]:
    return (_label(overlay.effect), f"{overlay.hp_delta:+d} HP")


@dataclass(frozen=True, slots=True)
class PhaseFocus:
    """Which combatants the in-flight phase concerns. Scoped to a whole `BattleEvent`, so a hit's
    highlight covers the HP tween trailing its swing. Never derived from `Battle.turn_phase`, which
    already describes whoever acts next, not whoever the player is watching (ADR 0013).
    """

    acting: Combatant | None = None
    receiving: Combatant | None = None


class CombatScene:
    def __init__(
        self,
        generation: Generation,
        encounter: EnemyEncountered,
        atlas: SpriteAtlas,
        buff_icon_factory: Callable[[EffectName], BuffIcon] | None = None,
    ) -> None:
        self._generation = generation
        if buff_icon_factory is not None:
            self._buff_icon_factory = buff_icon_factory
        else:
            # Built once per effect, not per render() call: SpriteBuffIcon caches its scaled
            # surfaces on itself, which only pays off if the same instance is reused across
            # frames rather than reconstructed from the atlas every time (ADR 0011's
            # scale_sprite precedent -- a fixed scale is computed once, not every draw() call).
            sprite_icons = {effect: SpriteBuffIcon(atlas, effect) for effect in EffectName}
            self._buff_icon_factory = sprite_icons.__getitem__
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
        self._announcement: Announcement | None = None
        self._overlay: Overlay | None = None
        self._phase_focus: PhaseFocus | None = None
        # Scene-wide, unlike _phase_elapsed, so the pulse never restarts at a phase boundary.
        self._elapsed_seconds: float = 0.0
        self._player_animator = _build_combat_animator(atlas, SpriteKey.PLAYER, _COMBATANT_SCALE_FACTOR)
        self._enemy_animator = _build_combat_animator(atlas, self._enemy_sprite_key, _COMBATANT_SCALE_FACTOR)
        # Fallback for a key with no animation clips at all -- BRAMBLE/UNKNOWN, or any
        # build_placeholder_atlas()-based test, since a placeholder atlas has no animation data.
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
        self._elapsed_seconds += dt
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
            self._tick_displayed_battle_effect_durations()
        # Starts (without necessarily finishing) the freshly queued batch's first phase within
        # this same call, rather than needing a dedicated "first event reveals immediately" flag.
        self._advance_phases(0.0)
        return None

    def _tick_displayed_battle_effect_durations(self) -> None:
        # Mirrors EffectRegistry.tick_battle_effects()'s once-per-round decrement -- its only
        # caller is Battle._expire_battle_effects(), itself only ever called from
        # resolve_enemy_turn() (never resolve_player_turn() or query_player_turn()), so this is
        # exact, not a heuristic, as long as it's called from that exact site. Deliberately eager,
        # not phase-gated (see DisplayedCombatantState.remaining_turns): the HUD number can update
        # a beat before that round's own animations finish playing.
        for displayed in (self._player_displayed, self._enemy_displayed):
            for key, remaining in displayed.remaining_turns.items():
                if key[0] is EffectCategory.BATTLE and remaining is not None:
                    displayed.remaining_turns[key] = remaining - 1

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
                # The only point with nothing in flight, so the only point a focus expires.
                self._phase_focus = None
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

        target_displayed = self._displayed_for(target)

        def on_start() -> None:
            self._phase_focus = PhaseFocus(acting=source, receiving=target)
            target_displayed.hit_flash = HitFlash(started_at=self._elapsed_seconds, valence=HitValence.DAMAGE)
            if source_animator is not None:
                source_animator.set_state(CombatAnimationState.ATTACK)
            if target_animator is not None:
                target_animator.set_state(CombatAnimationState.HIT)

        def on_complete() -> None:
            target_displayed.hit_flash = None
            if source_animator is not None:
                source_animator.set_state(CombatAnimationState.IDLE)
            if target_animator is not None:
                target_animator.set_state(CombatAnimationState.IDLE)

        return Phase(duration_seconds=max(source_duration, target_duration), on_start=on_start, on_complete=on_complete)

    def _reaction_phase(self, combatant: Combatant, valence: HitValence) -> Phase:
        # Target-only treatment for a reflect/recoil hit (ADR 0013) -- no attacker swing to drive.
        animator = self._animator_for(combatant)
        duration = animator.duration_of(CombatAnimationState.HIT) if animator else 0.0
        displayed = self._displayed_for(combatant)

        def on_start() -> None:
            self._phase_focus = PhaseFocus(receiving=combatant)
            displayed.hit_flash = HitFlash(started_at=self._elapsed_seconds, valence=valence)
            if animator is not None:
                animator.set_state(CombatAnimationState.HIT)

        def on_complete() -> None:
            displayed.hit_flash = None
            if animator is not None:
                animator.set_state(CombatAnimationState.IDLE)

        return Phase(duration_seconds=duration, on_start=on_start, on_complete=on_complete)

    def _overlay_phase(self, target: Combatant, effect: EffectName, hp_after: int, valence: HitValence) -> Phase:
        # Wraps _reaction_phase so the overlay holds for exactly the target's own flinch clip, and
        # so the label and the tint behind it name the same direction.
        reaction = self._reaction_phase(target, valence)
        displayed = self._displayed_for(target)
        # The bar's actual movement, not the event's nominal damage/amount: the domain caps a heal
        # at max_hp and applies no floor to a tick.
        hp_delta = round(max(0, hp_after) - max(0.0, displayed.hp))
        overlay = Overlay(target=target, effect=effect, hp_delta=hp_delta, valence=valence)

        def on_start() -> None:
            reaction.on_start()
            self._overlay = overlay
            displayed.effect_tick_started_at[effect] = self._elapsed_seconds

        def on_complete() -> None:
            reaction.on_complete()
            self._overlay = None
            displayed.effect_tick_started_at.pop(effect, None)

        return replace(reaction, on_start=on_start, on_complete=on_complete)

    def _announcement_phase(self, announcement: Announcement) -> Phase:
        # A bound method, not a free function taking a passed-in mutable object like
        # _hp_tween_phase/_meter_tween_phase -- those are parameterized per-combatant, but there's
        # only ever one announcement in flight for the whole scene, so this closes over
        # self._announcement directly (same shape as _swing_phase/_reaction_phase closing over
        # self._animator_for).
        def on_start() -> None:
            self._announcement = announcement

        def on_complete() -> None:
            self._announcement = None

        return Phase(duration_seconds=BATTLE_ANNOUNCEMENT_HOLD_SECONDS, on_start=on_start, on_complete=on_complete)

    def _effect_announcement_phase(self, event: EffectApplied | EffectExpired) -> list[Phase]:
        # Toggles DisplayedCombatantState.active_effects/remaining_turns in the same on_start that
        # reveals the announcement, not on_complete -- the HUD buff-icon row and the "is affected
        # by"/"wears off" popup must change in the same frame, since both are announcing the same
        # event.
        displayed = self._displayed_for(event.target)
        if isinstance(event, EffectApplied):
            key = (event.category, event.effect)
            if key in displayed.active_effects:
                # A reapplication (PROJECT_BRIEF.md §5.6's refresh-not-stack rule, scoped per
                # category) of an effect already showing in this same category -- the icon stays
                # put and its duration silently resets domain-side; announcing it again every time
                # (e.g. repeated Barbed Struggle uses) would spam the same popup. A different
                # category's instance of the same effect name is a genuinely new application (the
                # brief's own Lifespan-Fibrous-plus-Battle-Fibrous example), not a reapplication.
                # The HUD countdown still refreshes here, silently, matching the domain's own
                # silent duration reset -- no announcement plays, so this isn't phase-gated.
                displayed.remaining_turns[key] = event.remaining_turns
                return []
            duration = _duration_subtitle(event.category, event.remaining_turns)
            remaining_turns = event.remaining_turns
        else:
            # EffectExpired carries no category (only ever fired for a Battle-scoped effect today
            # -- Battle._expire_battle_effects/_clear_battle_effects both filter to
            # EffectCategory.BATTLE), so the key to discard is inferred rather than read off the
            # event. This breaks if a future domain change ever expires a Lifespan effect this way.
            key = (EffectCategory.BATTLE, event.effect)
            if self._battle.is_over:
                # End-of-battle cleanup expires every effect at once, so a card apiece would bury
                # the fight's own result. is_over is exact here: update() withholds every domain
                # call while phases or events are pending, so it cannot flip mid-batch.
                return [Phase(duration_seconds=0.0, on_start=lambda: _discard_displayed_effect(displayed, key))]
            duration = "Wears off"
            remaining_turns = None
        # Player and enemy both hold every effect type (PROJECT_BRIEF.md §5.6), so the subtitle
        # names who it's on, not just how long -- otherwise a Runt on the enemy and a Runt on the
        # player are visually indistinguishable while the card is up.
        subtitle = f"{event.target.name} — {duration}"
        card = EffectCard(
            title=_label(event.effect),
            icon=self._buff_icon_factory(event.effect),
            description=EFFECT_DESCRIPTIONS[event.effect],
            subtitle=subtitle,
        )
        announcement = Announcement(card=AnchoredCard(card=card, target=event.target))
        applied = isinstance(event, EffectApplied)

        def on_start() -> None:
            self._announcement = announcement
            if applied:
                displayed.active_effects.add(key)
                displayed.remaining_turns[key] = remaining_turns
            else:
                _discard_displayed_effect(displayed, key)

        def on_complete() -> None:
            self._announcement = None

        return [Phase(duration_seconds=BATTLE_ANNOUNCEMENT_HOLD_SECONDS, on_start=on_start, on_complete=on_complete)]

    def _phases_for(self, event: BattleEvent) -> list[Phase]:
        # ActionChosen is the one variant with nothing of its own to reveal (ADR 0013).
        match event:
            case ActionChosen():
                return []
            case Death(combatant=combatant):
                animator = self._animator_for(combatant)
                displayed = self._displayed_for(combatant)

                def on_start() -> None:
                    self._phase_focus = PhaseFocus(receiving=combatant)
                    # Defensive snap: a Wilty-triggered death sets current_hp directly and emits
                    # no event for the GUI to tween against.
                    displayed.hp = float(max(0, combatant.current_hp))
                    if animator is not None:
                        animator.set_state(CombatAnimationState.DEAD)

                return [Phase(duration_seconds=BATTLE_DEATH_POSE_HOLD_SECONDS, on_start=on_start)]
            case Revive(combatant=combatant, revived_hp=revived_hp):
                animator = self._animator_for(combatant)
                displayed = self._displayed_for(combatant)

                def on_start() -> None:
                    # Set on the instant state switch rather than the tween that follows, so the
                    # focus and the flash are already standing when the bar starts climbing.
                    self._phase_focus = PhaseFocus(receiving=combatant)
                    # Left to decay: this phase is zero-duration, so an on_complete clearing the
                    # flash would fire in the same tick.
                    displayed.hit_flash = HitFlash(started_at=self._elapsed_seconds, valence=HitValence.HEALING)
                    if animator is not None:
                        animator.set_state(CombatAnimationState.IDLE)

                return [
                    Phase(duration_seconds=0.0, on_start=on_start),
                    _hp_tween_phase(self._displayed_for(combatant), revived_hp),
                ]
            case EffectApplied() | EffectExpired():
                return self._effect_announcement_phase(event)
            case TurnSkipped() | ExtraActionTriggered() | BattleEnded():
                return [self._announcement_phase(Announcement(text=_describe_event(event)))]
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
                # DAMAGE even though Spiky Skin is a buff -- the flash lands on whoever it hits.
                return [
                    self._reaction_phase(target, HitValence.DAMAGE),
                    _hp_tween_phase(self._displayed_for(target), target_hp_after),
                ]
            case SelfDamageTaken(combatant=combatant, combatant_hp_after=combatant_hp_after):
                return [
                    self._reaction_phase(combatant, HitValence.DAMAGE),
                    _hp_tween_phase(self._displayed_for(combatant), combatant_hp_after),
                ]
            case DotTicked(target=target, effect=effect, target_hp_after=target_hp_after):
                return [
                    self._overlay_phase(target, effect, target_hp_after, HitValence.DAMAGE),
                    _hp_tween_phase(self._displayed_for(target), target_hp_after),
                ]
            case HealApplied(target=target, effect=effect, target_hp_after=target_hp_after):
                return [
                    self._overlay_phase(target, effect, target_hp_after, HitValence.HEALING),
                    _hp_tween_phase(self._displayed_for(target), target_hp_after),
                ]
            case _:
                assert_never(event)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        player_layout = _combatant_layout(surface, mirrored=False)
        enemy_layout = _combatant_layout(surface, mirrored=True)
        self._draw_combatant(surface, self._battle.player, self._player_displayed, player_layout)
        self._draw_combatant(surface, self._battle.enemy, self._enemy_displayed, enemy_layout)
        self._draw_menu(surface)
        self._draw_overlay(surface, player_layout, enemy_layout)
        self._draw_announcement(surface, player_layout, enemy_layout)

    def _current_sprite(self, combatant: Combatant) -> pygame.Surface:
        animator = self._animator_for(combatant)
        if animator is not None:
            return animator.current_frame()
        return self._player_static_sprite if combatant is self._battle.player else self._enemy_static_sprite

    def _highlight_color_for(self, combatant: Combatant) -> pygame.typing.ColorLike | None:
        """The colour for `combatant`'s role in the phase on screen, or `None`. Receiving wins over
        acting when a combatant is somehow both."""
        if self._phase_focus is None:
            return None
        if combatant is self._phase_focus.receiving:
            return BATTLE_RECEIVING_HIGHLIGHT_COLOR
        if combatant is self._phase_focus.acting:
            return BATTLE_ACTING_HIGHLIGHT_COLOR
        return None

    def _hit_flash_strength(self, displayed: DisplayedCombatantState) -> float:
        """How hard `displayed`'s sprite is lit this frame: peaks on impact, falls linearly to 0."""
        if displayed.hit_flash is None:
            return 0.0
        elapsed = self._elapsed_seconds - displayed.hit_flash.started_at
        if elapsed >= BATTLE_HIT_FLASH_DURATION_SECONDS:
            return 0.0
        return BATTLE_HIT_FLASH_STRENGTH * (1.0 - elapsed / BATTLE_HIT_FLASH_DURATION_SECONDS)

    def _buff_icon_hop_offset(self, displayed: DisplayedCombatantState, effect: EffectName) -> int:
        """How many pixels above its resting place `effect`'s icon sits this frame, 0 when at rest."""
        started_at = displayed.effect_tick_started_at.get(effect)
        if started_at is None:
            return 0
        elapsed = self._elapsed_seconds - started_at
        if elapsed >= BATTLE_BUFF_ICON_HOP_DURATION_SECONDS:
            return 0
        peak = min(BATTLE_BUFF_ICON_HOP_PIXELS, _BUFF_ICON_HOP_CEILING)
        phase = math.pi * elapsed / BATTLE_BUFF_ICON_HOP_DURATION_SECONDS
        return round(peak * math.sin(phase))

    def _pulse_mix(self) -> float:
        """How far a highlighted HP bar's fill sits toward its role colour this frame."""
        cycles = self._elapsed_seconds / BATTLE_HIGHLIGHT_PULSE_PERIOD_SECONDS
        return BATTLE_HIGHLIGHT_PULSE_STRENGTH * (1.0 - math.cos(math.tau * cycles)) / 2.0

    def _draw_combatant(
        self,
        surface: pygame.Surface,
        combatant: Combatant,
        displayed: DisplayedCombatantState,
        layout: CombatantLayout,
    ) -> None:
        font = get_font(GameFont.ITHACA, _FONT_SIZE)
        sprite = self._current_sprite(combatant)
        top = _MARGIN
        flash = displayed.hit_flash
        flash_strength = self._hit_flash_strength(displayed)
        drawn_sprite = sprite
        if flash is not None and flash_strength > 0.0:
            drawn_sprite = _lit_by_hit_flash(sprite, flash_strength, flash.valence)
        surface.blit(drawn_sprite, layout.sprite_topleft(sprite))

        # Steady on the name (who), pulsing on the HP bar (the value about to move).
        highlight = self._highlight_color_for(combatant)
        name = font.render(combatant.name, True, highlight if highlight is not None else _TEXT_COLOR)
        name_x = layout.bar_right - name.get_width() if layout.mirrored else layout.bar_left
        surface.blit(name, (name_x, top))

        current_hp = max(0.0, displayed.hp)
        hp_rect = pygame.Rect(layout.bar_left, top + _FONT_SIZE, _BAR_WIDTH, _BAR_HEIGHT)
        hp_color = _HP_COLOR if highlight is None else pygame.Color(_HP_COLOR).lerp(highlight, self._pulse_mix())
        self._draw_bar(surface, hp_rect, current_hp / combatant.base_stats.max_hp, hp_color)
        hp_label = font.render(f"{round(current_hp)}/{combatant.base_stats.max_hp}", True, _TEXT_COLOR)
        hp_label_x = hp_rect.left - _GAP - hp_label.get_width() if layout.mirrored else hp_rect.right + _GAP
        surface.blit(hp_label, (hp_label_x, hp_rect.top))

        meter_rect = pygame.Rect(layout.bar_left, hp_rect.bottom + _GAP, _BAR_WIDTH, _METER_HEIGHT)
        self._draw_bar(
            surface, meter_rect, max(0.0, displayed.meter) / combatant.base_stats.meter_capacity, _METER_COLOR
        )
        icon_row_x = layout.bar_right if layout.mirrored else layout.bar_left
        self._draw_buff_icons(surface, displayed, (icon_row_x, meter_rect.bottom + _GAP), mirrored=layout.mirrored)

    def _draw_bar(
        self, surface: pygame.Surface, rect: pygame.Rect, ratio: float, color: pygame.typing.ColorLike
    ) -> None:
        pygame.draw.rect(surface, _BAR_BG_COLOR, rect)
        filled = rect.copy()
        filled.width = round(rect.width * min(1.0, max(0.0, ratio)))
        pygame.draw.rect(surface, color, filled)

    def _draw_buff_icons(
        self, surface: pygame.Surface, displayed: DisplayedCombatantState, pos: tuple[int, int], *, mirrored: bool
    ) -> None:
        # Reads DisplayedCombatantState, not live Combatant.effects (ADR 0013) -- kept in sync by
        # _effect_announcement_phase's on_start, so the icon appears/disappears in step with its
        # own "is affected by"/"wears off" announcement rather than jumping ahead.
        # One icon per name regardless of category -- the row shows *whether* an effect is active,
        # not how many category-scoped instances back it (a Lifespan Fibrous plus a Battle Fibrous
        # both active still shows a single Fibrous icon). The countdown prefers the Battle-scoped
        # remaining_turns when both categories are active on the same name, since Lifespan's is
        # always None (blank) -- same "Battle over Lifespan" precedent as Adrenaline's trigger
        # preference (PROJECT_BRIEF.md §5.6), for the same reason: it's the one still ticking.
        active_names = {name for _, name in displayed.active_effects}
        active = [name for name in EffectName if name in active_names]
        x, y = pos
        if mirrored:
            # pos.x is the row's right edge on the mirrored side -- shift the whole row's start
            # left so the last icon's own right edge (start + (n-1) steps + one icon's width)
            # lands exactly at pos.x, then step forward as usual.
            x -= _BUFF_ICON_STEP * (len(active) - 1) + _BUFF_ICON_SIZE
        duration_font = get_font(GameFont.ITHACA, _BUFF_ICON_DURATION_FONT_SIZE)
        for name in active:
            # Only y moves: x stays on the row's fixed step, and the countdown rides along.
            icon_y = y - self._buff_icon_hop_offset(displayed, name)
            self._buff_icon_factory(name).render(surface, pygame.Vector2(x, icon_y), _BUFF_ICON_SIZE)
            remaining = displayed.remaining_turns.get((EffectCategory.BATTLE, name))
            if remaining is not None:
                label = duration_font.render(str(max(0, remaining)), True, _TEXT_COLOR)
                surface.blit(label, (x + _BUFF_ICON_SIZE - label.get_width(), icon_y))
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

    def _draw_overlay(
        self, surface: pygame.Surface, player_layout: CombatantLayout, enemy_layout: CombatantLayout
    ) -> None:
        if self._overlay is None:
            return
        target = self._overlay.target
        layout = player_layout if target is self._battle.player else enemy_layout
        font = get_font(GameFont.ITHACA, _OVERLAY_LABEL_FONT_SIZE)
        # Only the amount is tinted, so the block keeps a neutral half to read it against.
        effect_text, amount_text = _overlay_label_lines(self._overlay)
        lines = [
            font.render(effect_text, True, _TEXT_COLOR),
            font.render(amount_text, True, _valence_color(self._overlay.valence)),
        ]
        label_height = sum(line.height for line in lines) + _GAP
        # Beside the icon, not stacked: the HUD panel ends about a dozen pixels above the 64px-framed
        # enemy sprite, so a stack runs into it at any legible font size.
        block_width = _OVERLAY_ICON_SIZE + _GAP + max(line.width for line in lines)
        left = layout.sprite_center[0] - block_width // 2
        top = layout.sprite_topleft(self._current_sprite(target))[1] - _GAP - _OVERLAY_ICON_SIZE
        self._buff_icon_factory(self._overlay.effect).render(surface, pygame.Vector2(left, top), _OVERLAY_ICON_SIZE)
        line_y = top + (_OVERLAY_ICON_SIZE - label_height) // 2
        for line in lines:
            surface.blit(line, (left + _OVERLAY_ICON_SIZE + _GAP, line_y))
            line_y += line.height + _GAP

    def _draw_announcement(
        self, surface: pygame.Surface, player_layout: CombatantLayout, enemy_layout: CombatantLayout
    ) -> None:
        if self._announcement is None:
            return
        anchored = self._announcement.card
        if anchored is None:
            # A plain announcement concerns the fight, not one side of it, so it keeps the centre.
            self._draw_plain_announcement(surface, self._announcement)
            return
        # draw() is the single place a side's left/right anchoring is decided, as for _draw_overlay.
        layout = player_layout if anchored.target is self._battle.player else enemy_layout
        draw_effect_card(
            surface,
            anchored.card,
            center_x=layout.sprite_center[0],
            column_width=card_column_width(surface),
        )

    def _draw_plain_announcement(self, surface: pygame.Surface, announcement: Announcement) -> None:
        font = get_font(GameFont.ITHACA, _ANNOUNCEMENT_FONT_SIZE)
        text_surface = font.render(announcement.text, True, _TEXT_COLOR)
        text_pos = (surface.get_width() // 2 - text_surface.get_width() // 2, surface.get_height() // 2)
        surface.blit(text_surface, text_pos)
