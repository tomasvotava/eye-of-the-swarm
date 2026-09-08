"""ExplorationScene: the screen-by-screen driver for the Seed/Turf loop (ADR 0009,
PROJECT_BRIEF.md §6), walked visibly across three fixed x-positions per screen -- entry, encounter
marker, exit -- per ADR 0012. `generation.advance()` still fires exactly once per screen, as early
as when the screen loads (once at construction for the first screen via `for_new_generation()`, at
every `WALKING_TO_EXIT` arrival after that); only the GUI's reveal of that call's outcome is
deferred until the player's sprite reaches the marker. Owned and routed by `GameDriver` (ADR 0010),
never constructs a sibling scene itself.
"""

from collections.abc import Sequence
from enum import Enum, StrEnum, auto
from typing import assert_never

import pygame
import pygame.typing

from eye.exploration.events import EffectGranted, EnemyEncountered, NothingHappened, ResourceGranted, SeedPlanted
from eye.gui.animation import Animator, scale_clip, scale_sprite
from eye.gui.assets import SpriteAtlas, SpriteKey
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.play_scene import EnterCombat, PlaySceneTransition
from eye.gui.tuning import (
    ENCOUNTER_X_FRACTION,
    ENTRY_X_FRACTION,
    EXIT_X_FRACTION,
    WALK_TO_ENCOUNTER_DURATION_SECONDS,
    WALK_TO_EXIT_DURATION_SECONDS,
)
from eye.session.events import SessionEvent
from eye.session.game import Game
from eye.session.generation import Generation

_FONT_SIZE = 20
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_HUD_MARGIN = 8
_ICON_MARGIN = 8
_PLAYER_SCALE_FACTOR = 3.0

type _ScreenEvent = EffectGranted | ResourceGranted | NothingHappened


class PlayerAnimationState(StrEnum):
    """The player's animation states (ADR 0011)."""

    IDLE = "idle"
    WALK = "walk"


class ExplorationAction(Enum):
    ADVANCE = auto()
    PLANT_SEED = auto()


# pygame key -> ExplorationAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, ExplorationAction] = {
    pygame.K_SPACE: ExplorationAction.ADVANCE,
    pygame.K_RETURN: ExplorationAction.ADVANCE,
    pygame.K_p: ExplorationAction.PLANT_SEED,
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


def _describe_screen_event(event: _ScreenEvent) -> str:
    if isinstance(event, EffectGranted):
        return f"You feel {event.effect.name.replace('_', ' ').title()} take hold."
    if isinstance(event, ResourceGranted):
        return f"You gain {event.amount} ({event.kind.name.replace('_', ' ').title()})."
    return "Nothing happens here."


def _resolve_enemy_sprite_key(strain_name: str) -> SpriteKey:
    # Mirrors CombatScene's own helper (eye/gui/scenes/combat.py) rather than importing it --
    # exploration.py and combat.py deliberately never reference each other (see play_scene.py's
    # docstring), and this is too small a duplicate to justify breaking that seam for.
    try:
        return SpriteKey[strain_name]
    except KeyError:
        return SpriteKey.UNKNOWN


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


class ExplorationScene:
    def __init__(
        self,
        generation: Generation,
        game: Game,
        atlas: SpriteAtlas,
        *,
        starting_phase: _Phase,
        pending_events: Sequence[SessionEvent] = (),
    ) -> None:
        self._generation = generation
        self._game = game
        self._atlas = atlas
        self._phase = starting_phase
        self._pending_events = pending_events
        self._walk_elapsed_seconds = 0.0
        self._pending_action: ExplorationAction | None = None
        self._last_message = "You explore outward from the hive."

        # None when the atlas has no player animation data (e.g. build_placeholder_atlas()) --
        # mirrors DevAssetViewerScene's identical guard for this identical key/enum (ADR 0011).
        self._player_animator: Animator[PlayerAnimationState] | None = None
        if atlas.has_animation_set(SpriteKey.PLAYER):
            clips = {
                state: scale_clip(clip, _PLAYER_SCALE_FACTOR)
                for state, clip in atlas.get_animation_set(SpriteKey.PLAYER, PlayerAnimationState).items()
            }
            self._player_animator = Animator(clips, initial_state=_animation_state_for_phase(starting_phase))
        # Fallback for a placeholder atlas with no player animation data -- scaled once here
        # rather than on every draw().
        self._player_static_sprite = scale_sprite(atlas.get(SpriteKey.PLAYER), _PLAYER_SCALE_FACTOR)

    @classmethod
    def for_new_generation(cls, generation: Generation, game: Game, atlas: SpriteAtlas) -> ExplorationScene:
        """Joins the cycle at `AT_ENTRY` for the first screen beyond spawn. The spawn/home-turf
        position itself is never walked -- it holds no `advance()`-generated encounter, matured
        turf being safe by definition -- so this fires `advance()` once immediately rather than
        waiting for a `WALKING_TO_EXIT` arrival that will never come for this screen (ADR 0012)."""
        events = generation.advance()
        return cls(generation, game, atlas, starting_phase=_Phase.AT_ENTRY, pending_events=events)

    @classmethod
    def resuming_after_combat(cls, generation: Generation, game: Game, atlas: SpriteAtlas) -> ExplorationScene:
        """Joins directly at `RESOLVED`, positioned at the marker. The walk there already happened
        in the `ExplorationScene` instance that existed before the `EnterCombat` swap, and that
        screen's `advance()` already fired before combat took over, so this does not call it
        again (ADR 0012)."""
        return cls(generation, game, atlas, starting_phase=_Phase.RESOLVED)

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type != pygame.KEYDOWN:
            return
        action = KEY_ACTIONS.get(pygame_event.key)
        if action is not None:
            self._pending_action = action

    def update(self, dt: float) -> PlaySceneTransition | None:
        if self._player_animator is not None:
            self._player_animator.update(dt)
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
            if self._can_plant_seed():
                self._handle_plant_seed()
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

    def _begin_walk(self, phase: _Phase) -> None:
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
        self._set_phase(_Phase.AT_ENTRY)
        self._walk_elapsed_seconds = 0.0

    def _arrive_at_encounter(self) -> PlaySceneTransition | None:
        events, self._pending_events = self._pending_events, ()
        self._set_phase(_Phase.RESOLVED)
        self._walk_elapsed_seconds = 0.0

        encounter = next((event for event in events if isinstance(event, EnemyEncountered)), None)
        if encounter is not None:
            return EnterCombat(encounter=encounter)

        screen_event = next(
            (event for event in events if isinstance(event, EffectGranted | ResourceGranted | NothingHappened)), None
        )
        if screen_event is not None:
            self._last_message = _describe_screen_event(screen_event)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_background(surface)
        self._draw_encounter(surface)
        self._draw_player(surface)
        self._draw_status_icons(surface)
        self._draw_hud(surface)

    def _draw_background(self, surface: pygame.Surface) -> None:
        background = pygame.transform.scale(self._atlas.get(SpriteKey.BACKGROUND), surface.get_size())
        surface.blit(background, (0, 0))

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
        surface.blit(player, player.get_rect(center=(x, surface.get_rect().centery)))

    def _draw_encounter(self, surface: pygame.Surface) -> None:
        # Visible from the moment a screen's encounter is generated (AT_ENTRY) through the walk
        # toward it (WALKING_TO_ENCOUNTER) -- untriggered the whole time, per ADR 0012.
        if self._phase not in (_Phase.AT_ENTRY, _Phase.WALKING_TO_ENCOUNTER):
            return
        sprite_key = _resolve_encounter_sprite_key(self._pending_events)
        if sprite_key is None:
            return
        sprite = self._atlas.get(sprite_key)
        x = round(surface.get_width() * ENCOUNTER_X_FRACTION)
        surface.blit(sprite, sprite.get_rect(center=(x, surface.get_rect().centery)))

    def _draw_status_icons(self, surface: pygame.Surface) -> None:
        x = _ICON_MARGIN
        if self._can_plant_seed():
            seed = self._atlas.get(SpriteKey.SEED)
            surface.blit(seed, (x, _ICON_MARGIN))
            x += seed.get_width() + _ICON_MARGIN
        if self._game.matured_turf_positions:
            turf = self._atlas.get(SpriteKey.TURF)
            surface.blit(turf, (x, _ICON_MARGIN))

    def _draw_hud(self, surface: pygame.Surface) -> None:
        font = get_font(GameFont.ITHACA, _FONT_SIZE)
        lines = [
            f"Seed ready to plant: {'yes' if self._can_plant_seed() else 'no'}",
            f"Spores this life: {self._generation.spores_gained}",
            self._last_message,
            "Space/Enter: advance   P: plant seed",
        ]
        top = surface.get_height() - len(lines) * _FONT_SIZE - _HUD_MARGIN
        for index, line in enumerate(lines):
            surface.blit(font.render(line, True, _TEXT_COLOR), (_HUD_MARGIN, top + index * _FONT_SIZE))
