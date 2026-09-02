"""CombatScene: the first real consumer of `Battle.turn_phase` (ADR 0008/0009). A frame-based main
loop can't block on player input the way the TUI's `play_battle` does, so `update()` drives
whatever step `battle.turn_phase` is ready for on each call -- resolving automatic steps on its
own and surfacing an action menu only once the player actually needs to choose. On
`battle.is_over`, hands off to a fresh `ExplorationScene` on a win or a `SkillTreeScene` on death,
per PROJECT_BRIEF.md's generational-handoff framing (§4).
"""

from collections import deque
from collections.abc import Callable, Sequence
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
from eye.gui import save
from eye.gui.assets import SpriteAtlas, SpriteKey
from eye.gui.scene import Scene
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.scenes.skilltree import SkillTreeScene
from eye.gui.widgets import BuffIcon, TextBuffIcon
from eye.persistence.port import SaveStore
from eye.session.game import Game
from eye.session.generation import Generation

_FONT_SIZE = 20
_MARGIN = 8
_GAP = 4
_BAR_WIDTH = 200
_BAR_HEIGHT = 16
_METER_HEIGHT = 8
_PANEL_GAP = 16
_BUFF_ICON_STEP = 90
_LOG_LINES = 4
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
    # Assumes a same-named SpriteKey per Strain (true for v1's only member, BRAMBLE) -- a future
    # multi-Strain epic (PROJECT_BRIEF.md §8) must keep the two enums' names in sync or give this
    # a real Strain -> SpriteKey mapping instead. Falls back to the "missing texture" placeholder
    # rather than crashing the scene if the two ever drift apart.
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


class CombatScene:
    def __init__(
        self,
        generation: Generation,
        game: Game,
        encounter: EnemyEncountered,
        atlas: SpriteAtlas,
        save_store: SaveStore,
        buff_icon_factory: Callable[[EffectName], BuffIcon] = TextBuffIcon,
    ) -> None:
        self._generation = generation
        self._game = game
        self._atlas = atlas
        self._buff_icon_factory = buff_icon_factory
        self._save_store = save_store
        self._enemy_sprite_key = _resolve_enemy_sprite_key(encounter.strain.name)
        self._battle: Battle = generation.start_battle(encounter)
        self._pending_query: PlayerTurnNeedsAction | None = None
        self._pending_action_index: int | None = None
        self._cursor_index = 0
        self._log: deque[str] = deque(maxlen=_LOG_LINES)
        self._record(self._battle.start())

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type != pygame.KEYDOWN or self._pending_query is None:
            return
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

    def update(self, dt: float) -> Scene | None:
        if self._battle.is_over:
            return self._conclude()
        phase = self._battle.turn_phase
        if phase is TurnPhase.AWAITING_QUERY:
            self._advance_query()
        elif phase is TurnPhase.AWAITING_PLAYER_ACTION:
            self._resolve_pending_action()
        elif phase is TurnPhase.AWAITING_ENEMY_TURN:
            self._record(self._battle.resolve_enemy_turn())
        return None

    def _advance_query(self) -> None:
        query = self._battle.query_player_turn()
        if isinstance(query, PlayerTurnNeedsAction):
            self._record(query.pre_turn_events)
            self._pending_query = query
            self._cursor_index = 0
        else:
            self._record(query.events)

    def _resolve_pending_action(self) -> None:
        if self._pending_query is None or self._pending_action_index is None:
            return
        action = self._pending_query.available[self._pending_action_index]
        self._pending_query = None
        self._pending_action_index = None
        self._record(self._battle.resolve_player_turn(action))

    def _conclude(self) -> Scene:
        self._generation.finish_battle(self._battle)
        if not self._generation.died:
            return ExplorationScene(self._generation, self._game, self._atlas, save_store=self._save_store)
        self._game.end_generation(self._generation)
        save.persist(self._game, self._save_store)
        return SkillTreeScene(self._game, self._atlas, save_store=self._save_store)

    def _record(self, events: Sequence[BattleEvent]) -> None:
        for event in events:
            self._log.append(_describe_event(event))

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        panel_height = _FONT_SIZE + _BAR_HEIGHT + _METER_HEIGHT + _GAP * 2
        self._draw_combatant(surface, self._battle.player, SpriteKey.PLAYER, _MARGIN)
        self._draw_combatant(surface, self._battle.enemy, self._enemy_sprite_key, _MARGIN + panel_height + _PANEL_GAP)
        self._draw_menu(surface)
        self._draw_log(surface)

    def _draw_combatant(self, surface: pygame.Surface, combatant: Combatant, sprite_key: SpriteKey, top: int) -> None:
        font = _get_font()
        sprite = self._atlas.get(sprite_key)
        surface.blit(sprite, (_MARGIN, top))
        label_x = _MARGIN + sprite.get_width() + _GAP
        surface.blit(font.render(combatant.name, True, _TEXT_COLOR), (label_x, top))

        current_hp = max(0, combatant.current_hp)
        hp_rect = pygame.Rect(label_x, top + _FONT_SIZE, _BAR_WIDTH, _BAR_HEIGHT)
        self._draw_bar(surface, hp_rect, current_hp / combatant.base_stats.max_hp, _HP_COLOR)
        hp_label = font.render(f"{current_hp}/{combatant.base_stats.max_hp}", True, _TEXT_COLOR)
        surface.blit(hp_label, (hp_rect.right + _GAP, hp_rect.top))

        meter_rect = pygame.Rect(label_x, hp_rect.bottom + _GAP, _BAR_WIDTH, _METER_HEIGHT)
        self._draw_bar(surface, meter_rect, combatant.current_meter / combatant.base_stats.meter_capacity, _METER_COLOR)
        self._draw_buff_icons(surface, combatant, (label_x, meter_rect.bottom + _GAP))

    def _draw_bar(
        self, surface: pygame.Surface, rect: pygame.Rect, ratio: float, color: pygame.typing.ColorLike
    ) -> None:
        pygame.draw.rect(surface, _BAR_BG_COLOR, rect)
        filled = rect.copy()
        filled.width = round(rect.width * min(1.0, max(0.0, ratio)))
        pygame.draw.rect(surface, color, filled)

    def _draw_buff_icons(self, surface: pygame.Surface, combatant: Combatant, pos: tuple[int, int]) -> None:
        x, y = pos
        for name in EffectName:
            if not combatant.effects.has(name):
                continue
            self._buff_icon_factory(name).render(surface, pygame.Vector2(x, y))
            x += _BUFF_ICON_STEP

    def _draw_menu(self, surface: pygame.Surface) -> None:
        if self._pending_query is None:
            return
        font = _get_font()
        available = self._pending_query.available
        menu_height = (len(available) + 1) * _FONT_SIZE  # +1 for the control hint below the rows
        top = surface.get_height() - _LOG_LINES * _FONT_SIZE - menu_height - _MARGIN
        for index, action in enumerate(available):
            row = pygame.Rect(_MARGIN, top + index * _FONT_SIZE, _BAR_WIDTH, _FONT_SIZE)
            if index == self._cursor_index:
                pygame.draw.rect(surface, _CURSOR_COLOR, row)
            label = f"{index + 1}) {action.name or action.kind.name.replace('_', ' ').title()}"
            surface.blit(font.render(label, True, _TEXT_COLOR), row.topleft)
        hint = font.render("1-9: choose   Up/Down + Enter: choose", True, _TEXT_COLOR)
        surface.blit(hint, (_MARGIN, top + len(available) * _FONT_SIZE))

    def _draw_log(self, surface: pygame.Surface) -> None:
        font = _get_font()
        top = surface.get_height() - len(self._log) * _FONT_SIZE - _MARGIN
        for index, line in enumerate(self._log):
            surface.blit(font.render(line, True, _TEXT_COLOR), (_MARGIN, top + index * _FONT_SIZE))
