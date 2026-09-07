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
from dataclasses import dataclass
from enum import Enum
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
from eye.gui.assets import SpriteAtlas, SpriteKey
from eye.gui.play_scene import BattleConcluded, PlaySceneTransition
from eye.gui.widgets import BuffIcon, TextBuffIcon
from eye.session.generation import Generation

_FONT_SIZE = 20
_MARGIN = 8
_GAP = 4
_BAR_WIDTH = 200
_BAR_HEIGHT = 16
_METER_HEIGHT = 8
_BUFF_ICON_STEP = 90
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

_font: pygame.font.Font | None = None


def _get_font() -> pygame.font.Font:
    # Constructed lazily rather than at import time: pygame.font must already be initialized,
    # which module import order doesn't guarantee (mirrors eye.gui.widgets._get_font()).
    global _font
    if _font is None:
        _font = pygame.font.Font(None, _FONT_SIZE)
    return _font


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
        self._queue_events(self._battle.start())

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

    def _phases_for(self, event: BattleEvent) -> list[Phase]:
        # Stubbed to [] for every variant -- the Phase primitive and driver land here; per-event
        # visual content is added per-variant in #172 (animation-driven swings), #173
        # (Announcement/Tween), and #174 (Overlay), per ADR 0013.
        match event:
            case ActionChosen():
                return []
            case Death():
                return []
            case Revive():
                return []
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
            case MeterFilled():
                return []
            case MeterConsumed():
                return []
            case HitLanded():
                return []
            case HitReflected():
                return []
            case SelfDamageTaken():
                return []
            case DotTicked():
                return []
            case HealApplied():
                return []
            case _:
                assert_never(event)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        self._draw_combatant(surface, self._battle.player, SpriteKey.PLAYER, mirrored=False)
        self._draw_combatant(surface, self._battle.enemy, self._enemy_sprite_key, mirrored=True)
        self._draw_menu(surface)

    def _draw_combatant(
        self, surface: pygame.Surface, combatant: Combatant, sprite_key: SpriteKey, *, mirrored: bool
    ) -> None:
        # mirrored=True anchors the whole panel to the surface's right edge instead of the left,
        # so the player and enemy sit on opposite sides of the screen facing each other.
        font = _get_font()
        sprite = self._atlas.get(sprite_key)
        top = _MARGIN
        if mirrored:
            sprite_x = surface.get_width() - _MARGIN - sprite.get_width()
            bar_right = sprite_x - _GAP
            bar_left = bar_right - _BAR_WIDTH
        else:
            sprite_x = _MARGIN
            bar_left = sprite_x + sprite.get_width() + _GAP
            bar_right = bar_left + _BAR_WIDTH
        surface.blit(sprite, (sprite_x, top))

        name = font.render(combatant.name, True, _TEXT_COLOR)
        name_x = bar_right - name.get_width() if mirrored else bar_left
        surface.blit(name, (name_x, top))

        current_hp = max(0, combatant.current_hp)
        hp_rect = pygame.Rect(bar_left, top + _FONT_SIZE, _BAR_WIDTH, _BAR_HEIGHT)
        self._draw_bar(surface, hp_rect, current_hp / combatant.base_stats.max_hp, _HP_COLOR)
        hp_label = font.render(f"{current_hp}/{combatant.base_stats.max_hp}", True, _TEXT_COLOR)
        hp_label_x = hp_rect.left - _GAP - hp_label.get_width() if mirrored else hp_rect.right + _GAP
        surface.blit(hp_label, (hp_label_x, hp_rect.top))

        meter_rect = pygame.Rect(bar_left, hp_rect.bottom + _GAP, _BAR_WIDTH, _METER_HEIGHT)
        self._draw_bar(surface, meter_rect, combatant.current_meter / combatant.base_stats.meter_capacity, _METER_COLOR)
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
        font = _get_font()
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
