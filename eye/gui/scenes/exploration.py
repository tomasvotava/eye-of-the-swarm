"""ExplorationScene: the screen-by-screen driver for the Seed/Turf loop (ADR 0009,
PROJECT_BRIEF.md §6), walked visibly across three fixed x-positions per screen -- entry, encounter
marker, exit -- per ADR 0012. `generation.advance()` still fires exactly once per screen, as early
as when the screen loads (once at construction for the first screen via `for_new_generation()`, at
every `WALKING_TO_EXIT` arrival after that); only the GUI's reveal of that call's outcome is
deferred until the player's sprite reaches the marker. Owned and routed by `GameDriver` (ADR 0010),
never constructs a sibling scene itself.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Mapping, Sequence
from enum import Enum, StrEnum, auto
from typing import TYPE_CHECKING, assert_never

import pygame

from eye.combat.effects import EffectName
from eye.combat.tuning import PROXIMITY_FALLOFF_RANGE
from eye.exploration.encounters import ResourceKind
from eye.exploration.events import EffectGranted, EnemyEncountered, NothingHappened, ResourceGranted, SeedPlanted
from eye.gui.animation import Animator, crop_to_cover, scale_clip, scale_sprite
from eye.gui.assets import SpriteAtlas, SpriteKey
from eye.gui.audio import AudioManager, SoundKey
from eye.gui.biome import resolve_biome
from eye.gui.card import Card, card_column_width, draw_card
from eye.gui.effect_legend import LEGEND_CLOSE_KEYS, LEGEND_HINT, LEGEND_KEY, draw_effect_legend
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.narration import NarrationTrigger, NarrationTriggers, draw_narration
from eye.gui.play_scene import EnterCombat, OpenSettings, PlaySceneTransition
from eye.gui.props import resolve_prop_sampling
from eye.gui.tuning import (
    ENCOUNTER_ENEMY_SCALE_FACTOR,
    ENCOUNTER_PICKUP_SCALE_FACTOR,
    ENCOUNTER_X_FRACTION,
    ENTRY_X_FRACTION,
    EXIT_X_FRACTION,
    EXPLORATION_GROUND_Y_FRACTION,
    PROP_SCALE_FACTOR,
    PROP_Y_BAND_MAX_FRACTION,
    PROP_Y_BAND_MIN_FRACTION,
    WALK_TO_ENCOUNTER_DURATION_SECONDS,
    WALK_TO_EXIT_DURATION_SECONDS,
)
from eye.gui.widgets import (
    EFFECT_DESCRIPTIONS,
    BuffIcon,
    SpriteBuffIcon,
    SpriteIcon,
    borderless_icon,
    effect_label,
)
from eye.session.events import SessionEvent
from eye.session.game import Game
from eye.session.generation import Generation

if TYPE_CHECKING:
    import pygame.typing

_FONT_SIZE = 20
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_HUD_MARGIN = 8
_ICON_MARGIN = 8
_PLAYER_SCALE_FACTOR = 3.0
_BUFF_ICON_SIZE = 28
_BUFF_ICON_STEP = 36
_STATUS_ICON_KEYS = (SpriteKey.SEED, SpriteKey.TURF)  # in the order of appearance
_SPORES_ICON_SIZE = _BUFF_ICON_SIZE
_SPORES_LABEL_GAP = 4
_TURF_DISTANCE_FONT_SIZE = 14
_TURF_DISTANCE_PLATE_COLOR = pygame.Color("black")
_TURF_DISTANCE_PLATE_PADDING = 1
# Lerped from near to far across PROXIMITY_FALLOFF_RANGE; out of range once swarm help is gone.
_TURF_DISTANCE_NEAR_COLOR = pygame.Color("white")
_TURF_DISTANCE_FAR_COLOR = pygame.Color("orange")
_TURF_DISTANCE_OUT_OF_RANGE_COLOR = pygame.Color("orangered")
# Fixed: EffectGranted carries no category, and every effect a pickup grants is Lifespan-scoped.
_EFFECT_CARD_SUBTITLE = "This generation"
_CARD_FOOTER = "(press any key to close)"

# PROJECT_BRIEF.md §6: what each resource pickup does.
RESOURCE_DESCRIPTIONS: Mapping[ResourceKind, str] = {
    ResourceKind.HEAL: "Restores some HP",
    ResourceKind.SPORES: "Currency for the skill tree",
    ResourceKind.SEED_GROWTH: "Jumps the seed's growth meter",
    # PROJECT_BRIEF.md §6 rules this find out of Seed growth, so "in battle" has to stay.
    ResourceKind.DISTANCE_DISCOUNT: "Makes the hive feel closer in battle",
}

# The bordered sprite.png, so a resource card's icon looks like an effect card's.
_RESOURCE_SPRITE_KEYS: Mapping[ResourceKind, SpriteKey] = {
    ResourceKind.HEAL: SpriteKey.ICON_HEALTH,
    ResourceKind.SPORES: SpriteKey.ICON_SPORES,
    ResourceKind.SEED_GROWTH: SpriteKey.ICON_SEED_GROWTH,
    ResourceKind.DISTANCE_DISCOUNT: SpriteKey.ICON_DISTANCE_DISCOUNT,
}

# One-time opening lore, shown ahead of FIRST_EXPLORATION on a brand-new save only (INTRO_LORE is a
# persisted trigger, PROJECT_BRIEF.md §9.8) -- no subtitle line, these read as a single beat rather
# than instruction-plus-hint like the rest of the narration set.
_INTRO_LORE: tuple[tuple[str, str], ...] = (
    ("You are not the first to wear this shape.", ""),
    ("Every generation before you walked out, fought, and fell - and gave what it found to the swarm.", ""),
    ("Their spores became your strength. Their planted ground became your home.", ""),
    ("Now it's your turn. Walk out. Bring back what you can.", ""),
)

type _ScreenEvent = EffectGranted | ResourceGranted | NothingHappened


class PlayerAnimationState(StrEnum):
    """The player's animation states (ADR 0011)."""

    IDLE = "idle"
    WALK = "walk"


class ExplorationAction(Enum):
    ADVANCE = auto()
    PLANT_SEED = auto()
    OPEN_SETTINGS = auto()
    OPEN_LEGEND = auto()


# Never forwarded from the keypress that dismisses narration.
_OVERLAY_ACTIONS = frozenset({ExplorationAction.OPEN_SETTINGS, ExplorationAction.OPEN_LEGEND})

# pygame key -> ExplorationAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, ExplorationAction] = {
    pygame.K_SPACE: ExplorationAction.ADVANCE,
    pygame.K_RETURN: ExplorationAction.ADVANCE,
    pygame.K_p: ExplorationAction.PLANT_SEED,
    pygame.K_ESCAPE: ExplorationAction.OPEN_SETTINGS,
    LEGEND_KEY: ExplorationAction.OPEN_LEGEND,
}


class _Phase(Enum):
    """The screen-walk cycle (ADR 0012):

    RESOLVED --[ADVANCE]--> WALKING_TO_EXIT --[arrival]--> AT_ENTRY --[ADVANCE]-->
    WALKING_TO_ENCOUNTER --[arrival]--> RESOLVED (next screen)

    RESOLVED is the only phase where planting is legal -- the player sits at the marker with the
    current screen's outcome already known and applied.
    """

    RESOLVED = auto()
    WALKING_TO_EXIT = auto()
    AT_ENTRY = auto()
    WALKING_TO_ENCOUNTER = auto()


def _animation_state_for_phase(phase: _Phase) -> PlayerAnimationState:
    match phase:
        case _Phase.WALKING_TO_EXIT | _Phase.WALKING_TO_ENCOUNTER:
            return PlayerAnimationState.WALK
        case _Phase.RESOLVED | _Phase.AT_ENTRY:
            return PlayerAnimationState.IDLE
        case _:
            assert_never(phase)


def _resource_label(kind: ResourceKind) -> str:
    return kind.name.replace("_", " ").title()


def _describe_screen_event(event: _ScreenEvent) -> str:
    if isinstance(event, EffectGranted):
        return f"You feel {effect_label(event.effect)} take hold."
    if isinstance(event, ResourceGranted):
        return f"You gain {event.amount} ({_resource_label(event.kind)})."
    return "Nothing happens here."


def _resolve_enemy_sprite_key(strain_name: str) -> SpriteKey:
    # Mirrors CombatScene's own helper (eye/gui/scenes/combat.py) rather than importing it --
    # exploration.py and combat.py deliberately never reference each other (see play_scene.py's
    # docstring), and this is too small a duplicate to justify breaking that seam for.
    try:
        return SpriteKey[strain_name]
    except KeyError:
        return SpriteKey.UNKNOWN


def _turf_distance_label(distance: float) -> str:
    """Whole screens to the nearest matured turf, capped at the range where swarm help runs out."""
    if distance >= PROXIMITY_FALLOFF_RANGE:
        return f"{math.floor(PROXIMITY_FALLOFF_RANGE)}+"
    return str(math.floor(distance))


def _turf_distance_color(distance: float) -> pygame.Color:
    if distance >= PROXIMITY_FALLOFF_RANGE:
        return _TURF_DISTANCE_OUT_OF_RANGE_COLOR
    return _TURF_DISTANCE_NEAR_COLOR.lerp(_TURF_DISTANCE_FAR_COLOR, distance / PROXIMITY_FALLOFF_RANGE)


def _status_icon_row_right(atlas: SpriteAtlas) -> int:
    """The x of the next drawable element, calculated based on the widest the status row can ever get"""
    right = _ICON_MARGIN
    for key in _STATUS_ICON_KEYS:
        right += atlas.get(key).get_width() + _ICON_MARGIN
    return right - _ICON_MARGIN


def _resolve_encounter_sprite_key(events: Sequence[SessionEvent]) -> SpriteKey | None:
    """What stands at the marker for a not-yet-triggered encounter (ADR 0012: "an enemy sprite
    standing there, etc -- nothing about what it is stays secret"). `None` means the screen is
    genuinely empty -- there's nothing to reveal, not something being hidden."""
    for event in events:
        if isinstance(event, EnemyEncountered):
            return _resolve_enemy_sprite_key(event.strain.name)
        if isinstance(event, EffectGranted):
            return SpriteKey.EFFECT_PICKUP
        if isinstance(event, ResourceGranted):
            return SpriteKey.RESOURCE_PICKUP
    return None


def _fire_narration_for_advance(narration: NarrationTriggers, events: Sequence[SessionEvent]) -> None:
    """The heads-up for whatever `generation.advance()` just produced, fired as soon as the screen
    loads rather than once the player's sprite has walked up and revealed it -- ADR 0012 only
    defers the visual reveal, not the outcome itself, so the warning can arrive before the danger
    does."""
    if any(isinstance(event, EnemyEncountered) for event in events):
        # No control hint here: this fires well before the combat menu exists to describe, on the
        # walk up to the encounter, not once the player is looking at it.
        narration.fire(
            NarrationTrigger.FIRST_BATTLE,
            "A hostile strain blocks your path.",
            "Ready your swarm. A fight is close.",
        )
    if any(isinstance(event, EffectGranted) for event in events):
        narration.fire(
            NarrationTrigger.FIRST_PICKUP,
            "Something ahead will change you.",
            "For good or ill - and it stays with you until this life ends.",
        )


_PICKUP_MARKER_KEYS = (SpriteKey.EFFECT_PICKUP, SpriteKey.RESOURCE_PICKUP)


def _encounter_scale_factor(key: SpriteKey) -> float:
    # UNKNOWN falls out of the enemy branch of _resolve_encounter_sprite_key (a Strain with no
    # matching SpriteKey), never the pickup one, so it belongs on the enemy side here too.
    return ENCOUNTER_PICKUP_SCALE_FACTOR if key in _PICKUP_MARKER_KEYS else ENCOUNTER_ENEMY_SCALE_FACTOR


class EncounterAnimationState(StrEnum):
    """The marker's only animated state -- an unresolved encounter never fights (ADR 0011)."""

    IDLE = "idle"


def _build_encounter_animator(
    atlas: SpriteAtlas, key: SpriteKey, scale_factor: float
) -> Animator[EncounterAnimationState] | None:
    """`None` for a key with no animation clips at all -- the pickup markers, BRAMBLE/UNKNOWN, or
    any `build_placeholder_atlas()`-based test -- which draws `_encounter_static_sprite` instead."""
    if not atlas.has_animation_set(key):
        return None
    clips = {
        state: scale_clip(clip, scale_factor)
        for state, clip in atlas.get_animation_set(key, EncounterAnimationState).items()
    }
    return Animator(clips, initial_state=EncounterAnimationState.IDLE)


class ExplorationScene:
    def __init__(
        self,
        generation: Generation,
        game: Game,
        atlas: SpriteAtlas,
        buff_icon_factory: Callable[[EffectName], BuffIcon] | None = None,
        *,
        starting_phase: _Phase,
        pending_events: Sequence[SessionEvent] = (),
        narration: NarrationTriggers | None = None,
        displayed_turf_distance: float | None = None,
    ) -> None:
        self._generation = generation
        self._game = game
        self._atlas = atlas
        self._narration = narration if narration is not None else NarrationTriggers()
        if buff_icon_factory is not None:
            self._buff_icon_factory = buff_icon_factory
        else:
            # One instance per effect: SpriteBuffIcon caches its scaled surfaces on itself.
            sprite_icons = {effect: SpriteBuffIcon(atlas, effect) for effect in EffectName}
            self._buff_icon_factory = sprite_icons.__getitem__
        # Not routed through buff_icon_factory: that seam is keyed by EffectName.
        self._resource_icons = {kind: SpriteIcon(atlas, key) for kind, key in _RESOURCE_SPRITE_KEYS.items()}
        self._spores_icon = borderless_icon(atlas, SpriteKey.ICON_SPORES)
        self._spores_counter_left = _status_icon_row_right(atlas) + _ICON_MARGIN
        self._phase = starting_phase
        self._pending_events = pending_events
        self._encounter_animator: Animator[EncounterAnimationState] | None = None
        self._encounter_static_sprite: pygame.Surface | None = None
        self._rebuild_encounter_visuals()
        self._walk_elapsed_seconds = 0.0
        self._pending_action: ExplorationAction | None = None
        self._last_message = "You explore outward from the hive."
        # Refreshed only at a marker arrival, never read live: pending_events is this screen's
        # outcome, already applied by advance() but not revealed until the walk reaches the marker
        # (ADR 0012).
        unrevealed = {event.effect for event in pending_events if isinstance(event, EffectGranted)}
        self._displayed_effects = tuple(
            effect for effect in generation.active_lifespan_effects if effect not in unrevealed
        )
        # snapshotted value so that it only advances when collected
        self._displayed_spores = generation.spores_gained - sum(
            event.amount
            for event in pending_events
            if isinstance(event, ResourceGranted) and event.kind is ResourceKind.SPORES
        )
        # Same reveal rule: a distance-discount pickup lowers the live value before it's revealed.
        self._displayed_turf_distance = (
            displayed_turf_distance
            if displayed_turf_distance is not None
            else generation.distance_to_nearest_matured_turf
        )
        self._card: Card | None = None
        self._dismiss_card = False
        self._legend_open = False

        # None when the atlas has no player animation data (e.g. build_placeholder_atlas()) --
        # mirrors DevAssetViewerScene's identical guard for this identical key/enum (ADR 0011).
        self._player_animator: Animator[PlayerAnimationState] | None = None
        if atlas.has_animation_set(SpriteKey.PLAYER):
            clips = {
                state: scale_clip(clip, _PLAYER_SCALE_FACTOR)
                for state, clip in atlas.get_animation_set(SpriteKey.PLAYER, PlayerAnimationState).items()
            }
            self._player_animator = Animator(clips, initial_state=_animation_state_for_phase(starting_phase))
        # Fallback for a placeholder atlas with no player animation data (same guard as above).
        self._player_static_sprite = scale_sprite(atlas.get(SpriteKey.PLAYER), _PLAYER_SCALE_FACTOR)
        # Not seeded, unlike EncounterGenerator's rolls: prop placement has no determinism
        # requirement (ADR 0016).
        self._prop_rng = random.Random()  # noqa: S311 -- game RNG, not cryptographic
        # Rolled once per screen (on first draw() and again at _arrive_at_exit), not every frame --
        # a prop's position stays fixed for as long as the screen does.
        self._cached_props: list[tuple[pygame.Surface, int, int]] = []
        self._props_dirty = True

    @classmethod
    def for_new_generation(
        cls,
        generation: Generation,
        game: Game,
        atlas: SpriteAtlas,
        audio: AudioManager,
        buff_icon_factory: Callable[[EffectName], BuffIcon] | None = None,
        narration: NarrationTriggers | None = None,
    ) -> ExplorationScene:
        """Joins the cycle at `AT_ENTRY` for the first screen beyond spawn. The spawn/home-turf
        position itself is never walked -- it holds no `advance()`-generated encounter, matured
        turf being safe by definition -- so this fires `advance()` once immediately rather than
        waiting for a `WALKING_TO_EXIT` arrival that will never come for this screen (ADR 0012)."""
        audio.play_ambient(SoundKey.EXPLORATION)
        narration = narration if narration is not None else NarrationTriggers()
        narration.fire_sequence(NarrationTrigger.INTRO_LORE, _INTRO_LORE)
        turf_distance_before_advance = generation.distance_to_nearest_matured_turf
        events = generation.advance()
        narration.fire(
            NarrationTrigger.FIRST_EXPLORATION,
            "You venture out of the hive to spread your swarm's turf.",
            "Press Space or Enter to venture further.",
        )
        _fire_narration_for_advance(narration, events)
        return cls(
            generation,
            game,
            atlas,
            buff_icon_factory,
            starting_phase=_Phase.AT_ENTRY,
            pending_events=events,
            narration=narration,
            displayed_turf_distance=turf_distance_before_advance,
        )

    @classmethod
    def resuming_after_combat(
        cls,
        generation: Generation,
        game: Game,
        atlas: SpriteAtlas,
        audio: AudioManager,
        buff_icon_factory: Callable[[EffectName], BuffIcon] | None = None,
        narration: NarrationTriggers | None = None,
    ) -> ExplorationScene:
        """Joins directly at `RESOLVED`, positioned at the marker. The walk there already happened
        in the `ExplorationScene` instance that existed before the `EnterCombat` swap, and that
        screen's `advance()` already fired before combat took over, so this does not call it
        again (ADR 0012)."""
        audio.play_ambient(SoundKey.EXPLORATION)
        return cls(generation, game, atlas, buff_icon_factory, starting_phase=_Phase.RESOLVED, narration=narration)

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type != pygame.KEYDOWN:
            return
        action = KEY_ACTIONS.get(pygame_event.key)
        if self._narration.queue.is_active:
            self._narration.queue.dismiss()
            # Forwarded only on the dismiss that empties the queue, and never under a card --
            # FIRST_SEED_READY can fire on a frame where a pickup card is already up (GOTCHAS.md).
            if (
                not self._narration.queue.is_active
                and self._card is None
                and action is not None
                and action not in _OVERLAY_ACTIONS
            ):
                self._pending_action = action
            return
        if self._legend_open:
            self._legend_open = pygame_event.key not in LEGEND_CLOSE_KEYS
            return
        if self._card is not None:
            # Returning here, before any _pending_action write, is the entire reason no walk or
            # seed can start while a card is up. Do not add an unguarded _pending_action write
            # above it.
            self._dismiss_card = True
            return
        if action is not None:
            self._pending_action = action

    def update(self, dt: float) -> PlaySceneTransition | None:
        if self._player_animator is not None:
            self._player_animator.update(dt)
        if self._encounter_animator is not None:
            self._encounter_animator.update(dt)
        self._check_narration_triggers()
        # Below the animator ticks, not above them: skipping a tick would drop a frame of
        # whichever clip is playing.
        if self._dismiss_card:
            self._dismiss_card = False
            self._card = None
            return None
        if self._phase in (_Phase.WALKING_TO_EXIT, _Phase.WALKING_TO_ENCOUNTER):
            # A key pressed mid-walk is a silent no-op, not a queued one -- discarded here rather
            # than left to fire the instant the walk ends.
            self._pending_action = None
            return self._advance_walk(dt)

        action = self._pending_action
        self._pending_action = None
        if action is None:
            return None
        if action is ExplorationAction.PLANT_SEED:
            # The narration check above can raise FIRST_SEED_READY on this very frame, on the same
            # press that would otherwise plant -- withhold planting until that prompt has actually
            # been read and dismissed, rather than have the "press P" message outlive its own action.
            if self._can_plant_seed() and not self._narration.queue.is_active:
                self._handle_plant_seed()
            return None
        if action in _OVERLAY_ACTIONS:
            # Same same-frame FIRST_SEED_READY race as PLANT_SEED above.
            if self._narration.queue.is_active:
                return None
            if action is ExplorationAction.OPEN_SETTINGS:
                return OpenSettings()
            self._legend_open = True
            return None
        if self._phase is _Phase.RESOLVED:
            self._begin_walk(_Phase.WALKING_TO_EXIT)
        elif self._phase is _Phase.AT_ENTRY:
            self._begin_walk(_Phase.WALKING_TO_ENCOUNTER)
        else:
            return None
        # The frame that starts a walk also spends its own dt on it -- otherwise a walk that
        # begins on frame N doesn't move until frame N+1, silently stretching every walk by one
        # frame's worth of time (imperceptible at 60fps, but wrong on principle and awkward to
        # drive deterministically in tests).
        return self._advance_walk(dt)

    def _check_narration_triggers(self) -> None:
        # Level checks, not edge-triggered: safe to call every frame since NarrationTriggers.fire()
        # is itself a once-per-generation no-op once seen.
        if self._can_plant_seed():
            self._narration.fire(
                NarrationTrigger.FIRST_SEED_READY,
                "A seed is ready to plant.",
                "Press P to plant it - it won't strengthen you, only marks this ground for whoever comes after.",
            )
        distance = self._generation.distance_to_nearest_matured_turf
        # inf (no turf has matured this generation yet) is excluded: "you've ventured too far" is
        # a lie on a fresh save's first screen, where zero matured turf is the expected baseline.
        if math.isfinite(distance) and distance >= PROXIMITY_FALLOFF_RANGE:
            self._narration.fire(
                NarrationTrigger.FIRST_PROXIMITY_FALLOFF,
                "You've ventured too far from home.",
                "Alone here - the swarm's strength doesn't reach this far.",
            )

    def _begin_walk(self, phase: _Phase) -> None:
        # No card can be up here: handle_pygame_event returns before writing _pending_action
        # while one is raised.
        self._set_phase(phase)
        self._walk_elapsed_seconds = 0.0

    def _set_phase(self, phase: _Phase) -> None:
        # Single source of truth for phase transitions (post-__init__) -- keeps the player
        # animator's state from being able to drift out of sync with the phase (ADR 0012).
        self._phase = phase
        if self._player_animator is not None:
            self._player_animator.set_state(_animation_state_for_phase(phase))

    def _can_plant_seed(self) -> bool:
        # Single source of truth for plant legality -- both the actual gate in update() and the
        # GUI's "seed ready" icon/HUD label read this, so they can't drift apart (ADR 0012:
        # RESOLVED is the only phase where planting is legal).
        return self._phase is _Phase.RESOLVED and self._generation.is_seed_ready

    def _handle_plant_seed(self) -> None:
        events = self._generation.plant_seed()
        planted = next((event for event in events if isinstance(event, SeedPlanted)), None)
        if planted is not None:
            self._last_message = f"You plant a seed at screen {planted.position}."

    def _advance_walk(self, dt: float) -> PlaySceneTransition | None:
        self._walk_elapsed_seconds += dt
        duration = (
            WALK_TO_EXIT_DURATION_SECONDS
            if self._phase is _Phase.WALKING_TO_EXIT
            else WALK_TO_ENCOUNTER_DURATION_SECONDS
        )
        if self._walk_elapsed_seconds < duration:
            return None
        if self._phase is _Phase.WALKING_TO_EXIT:
            self._arrive_at_exit()
            return None
        return self._arrive_at_encounter()

    def _arrive_at_exit(self) -> None:
        self._pending_events = self._generation.advance()
        _fire_narration_for_advance(self._narration, self._pending_events)
        self._rebuild_encounter_visuals()
        self._props_dirty = True
        self._set_phase(_Phase.AT_ENTRY)
        self._walk_elapsed_seconds = 0.0

    def _rebuild_encounter_visuals(self) -> None:
        # Called from __init__ and _arrive_at_exit, not every draw() -- built once per encounter
        # (ADR 0011), not once per frame. _arrive_at_encounter clears _pending_events without
        # calling this; draw()'s own phase gate means that staleness is never seen.
        key = _resolve_encounter_sprite_key(self._pending_events)
        if key is None:
            self._encounter_animator = None
            self._encounter_static_sprite = None
            return
        scale_factor = _encounter_scale_factor(key)
        self._encounter_animator = _build_encounter_animator(self._atlas, key, scale_factor)
        self._encounter_static_sprite = scale_sprite(self._atlas.get(key), scale_factor)

    def _arrive_at_encounter(self) -> PlaySceneTransition | None:
        events, self._pending_events = self._pending_events, ()
        self._set_phase(_Phase.RESOLVED)
        self._walk_elapsed_seconds = 0.0
        # The reveal point: advance() applied the pickup back when the screen loaded.
        self._displayed_effects = self._generation.active_lifespan_effects
        self._displayed_spores = self._generation.spores_gained
        self._displayed_turf_distance = self._generation.distance_to_nearest_matured_turf

        encounter = next((event for event in events if isinstance(event, EnemyEncountered)), None)
        if encounter is not None:
            return EnterCombat(encounter=encounter)

        screen_event = next(
            (event for event in events if isinstance(event, EffectGranted | ResourceGranted | NothingHappened)), None
        )
        if screen_event is not None:
            # Twice by design: the card is the moment, the HUD line the record it leaves.
            self._last_message = _describe_screen_event(screen_event)
            self._card = self._card_for_screen_event(screen_event)
        return None

    def _card_for_screen_event(self, event: _ScreenEvent) -> Card | None:
        if isinstance(event, EffectGranted):
            return Card(
                title=effect_label(event.effect),
                icon=self._buff_icon_factory(event.effect),
                description=EFFECT_DESCRIPTIONS[event.effect],
                subtitle=_EFFECT_CARD_SUBTITLE,
            )
        if isinstance(event, ResourceGranted):
            return Card(
                title=_resource_label(event.kind),
                icon=self._resource_icons[event.kind],
                description=RESOURCE_DESCRIPTIONS[event.kind],
                subtitle=f"+{event.amount}",
            )
        return None

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_background(surface)
        self._draw_props(surface)
        self._draw_encounter(surface)
        self._draw_player(surface)
        self._draw_status_icons(surface)
        self._draw_spores_counter(surface)
        self._draw_buff_icons(surface)
        self._draw_hud(surface)
        self._draw_raised_card(surface)
        if self._legend_open:
            draw_effect_legend(surface, self._displayed_effects, self._buff_icon_factory)
        self._draw_narration(surface)

    def _draw_background(self, surface: pygame.Surface) -> None:
        key = resolve_biome(self._generation.distance_from_home)
        background = crop_to_cover(self._atlas.get(key), surface.get_size())
        surface.blit(background, (0, 0))

    def _draw_props(self, surface: pygame.Surface) -> None:
        if self._props_dirty:
            self._rebuild_props(surface.get_size())
            self._props_dirty = False
        for prop, x, y in self._cached_props:
            surface.blit(prop, (x, y))

    def _rebuild_props(self, size: tuple[int, int]) -> None:
        sampling = resolve_prop_sampling(self._generation.distance_from_home)
        width, height = size
        y_min = round(height * PROP_Y_BAND_MIN_FRACTION)
        y_max = round(height * PROP_Y_BAND_MAX_FRACTION)
        props: list[tuple[pygame.Surface, int, int]] = []
        for key, count in sampling:
            pool = list(self._atlas.get_props(key).values())
            if not pool:
                continue
            for _ in range(count):
                prop = self._prop_rng.choice(pool)
                scaled = scale_sprite(prop, PROP_SCALE_FACTOR)
                x = self._prop_rng.randint(0, max(0, width - scaled.get_width()))
                y = self._prop_rng.randint(y_min, max(y_min, y_max - scaled.get_height()))
                props.append((scaled, x, y))
        self._cached_props = props

    def _player_x_fraction(self) -> float:
        match self._phase:
            case _Phase.RESOLVED:
                return ENCOUNTER_X_FRACTION
            case _Phase.AT_ENTRY:
                return ENTRY_X_FRACTION
            case _Phase.WALKING_TO_EXIT:
                duration, start, end = WALK_TO_EXIT_DURATION_SECONDS, ENCOUNTER_X_FRACTION, EXIT_X_FRACTION
            case _Phase.WALKING_TO_ENCOUNTER:
                duration, start, end = WALK_TO_ENCOUNTER_DURATION_SECONDS, ENTRY_X_FRACTION, ENCOUNTER_X_FRACTION
            case _:
                assert_never(self._phase)
        ratio = min(1.0, self._walk_elapsed_seconds / duration)
        return start + (end - start) * ratio

    def _draw_player(self, surface: pygame.Surface) -> None:
        player = (
            self._player_animator.current_frame() if self._player_animator is not None else self._player_static_sprite
        )
        x = round(surface.get_width() * self._player_x_fraction())
        y = round(surface.get_height() * EXPLORATION_GROUND_Y_FRACTION)
        surface.blit(player, player.get_rect(center=(x, y)))

    def _draw_encounter(self, surface: pygame.Surface) -> None:
        # Visible from the moment a screen's encounter is generated (AT_ENTRY) through the walk
        # toward it (WALKING_TO_ENCOUNTER) -- untriggered the whole time, per ADR 0012.
        if self._phase not in (_Phase.AT_ENTRY, _Phase.WALKING_TO_ENCOUNTER):
            return
        sprite = (
            self._encounter_animator.current_frame()
            if self._encounter_animator is not None
            else self._encounter_static_sprite
        )
        if sprite is None:
            return
        x = round(surface.get_width() * ENCOUNTER_X_FRACTION)
        y = round(surface.get_height() * EXPLORATION_GROUND_Y_FRACTION)
        surface.blit(sprite, sprite.get_rect(center=(x, y)))

    def _draw_status_icons(self, surface: pygame.Surface) -> None:
        showing = {
            SpriteKey.SEED: self._can_plant_seed(),
            SpriteKey.TURF: bool(self._game.matured_turf_positions),
        }
        x = _ICON_MARGIN
        for key in _STATUS_ICON_KEYS:
            if not showing[key]:
                continue
            sprite = self._atlas.get(key)
            surface.blit(sprite, (x, _ICON_MARGIN))
            if key is SpriteKey.TURF and math.isfinite(self._displayed_turf_distance):
                self._draw_turf_distance_badge(surface, sprite.get_rect(topleft=(x, _ICON_MARGIN)))
            x += sprite.get_width() + _ICON_MARGIN

    def _draw_turf_distance_badge(self, surface: pygame.Surface, icon_rect: pygame.Rect) -> None:
        # Overlaid on the icon's corner rather than beside it: the top row has no width to spare
        # once every Lifespan effect is showing.
        distance = self._displayed_turf_distance
        font = get_font(GameFont.ITHACA, _TURF_DISTANCE_FONT_SIZE)
        text = _turf_distance_label(distance)
        label = font.render(text, True, _turf_distance_color(distance))
        # A plate, so the tint never has to contrast with whatever art the icon carries.
        plate = label.get_rect().inflate(_TURF_DISTANCE_PLATE_PADDING * 2, 0)
        plate.bottomright = icon_rect.bottomright
        pygame.draw.rect(surface, _TURF_DISTANCE_PLATE_COLOR, plate)
        surface.blit(label, label.get_rect(center=plate.center))

    def _draw_spores_counter(self, surface: pygame.Surface) -> None:
        self._spores_icon.render(surface, pygame.Vector2(self._spores_counter_left, _ICON_MARGIN), _SPORES_ICON_SIZE)
        total = get_font(GameFont.ITHACA, _FONT_SIZE).render(str(self._displayed_spores), True, _TEXT_COLOR)
        # Centred on the icon's box: a number hung from its top reads as a superscript.
        surface.blit(
            total,
            (
                self._spores_counter_left + _SPORES_ICON_SIZE + _SPORES_LABEL_GAP,
                _ICON_MARGIN + (_SPORES_ICON_SIZE - total.get_height()) // 2,
            ),
        )

    def _draw_buff_icons(self, surface: pygame.Surface) -> None:
        # No countdown beside an icon: a Lifespan effect runs until the generation ends, so it has
        # no remaining_turns to show (PROJECT_BRIEF.md §5.6).
        active = self._displayed_effects
        if not active:
            return
        # Top-right, clear of the top-left status icons and the bottom-left HUD text.
        x = surface.get_width() - _ICON_MARGIN - _BUFF_ICON_STEP * (len(active) - 1) - _BUFF_ICON_SIZE
        for effect in active:
            self._buff_icon_factory(effect).render(surface, pygame.Vector2(x, _ICON_MARGIN), _BUFF_ICON_SIZE)
            x += _BUFF_ICON_STEP

    def _draw_raised_card(self, surface: pygame.Surface) -> None:
        # Centred, unlike CombatScene's: out here there is only one character to point at.
        # Held back while narration is up (drawn after this in draw()) so the two never overlap --
        # the card becomes visible the frame narration is dismissed, not before.
        if self._card is None or self._narration.queue.is_active:
            return
        draw_card(
            surface,
            self._card,
            center_x=surface.get_width() // 2,
            column_width=card_column_width(surface),
            footer=_CARD_FOOTER,
        )

    def _draw_narration(self, surface: pygame.Surface) -> None:
        entry = self._narration.queue.current
        if entry is not None:
            draw_narration(surface, entry, center_x=surface.get_width() // 2, column_width=card_column_width(surface))

    def _draw_hud(self, surface: pygame.Surface) -> None:
        font = get_font(GameFont.ITHACA, _FONT_SIZE)
        lines = [
            f"Seed ready to plant: {'yes' if self._can_plant_seed() else 'no'}",
            self._last_message,
            f"Space/Enter: advance   P: plant seed   {LEGEND_HINT}   Esc: settings",
        ]
        top = surface.get_height() - len(lines) * _FONT_SIZE - _HUD_MARGIN
        for index, line in enumerate(lines):
            surface.blit(font.render(line, True, _TEXT_COLOR), (_HUD_MARGIN, top + index * _FONT_SIZE))
