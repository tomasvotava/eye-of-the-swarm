"""MenuScene: the slot picker players see before a `GameDriver` exists (ADR 0017). Classifies
each of the 3 save slots as Empty/Corrupt/Valid via `save.store_for_slot()`/`save.peek()` without
constructing a `Game`, then confirms into a `GameDriver` bound to whichever slot's store the
player picked. New Game vs. Continue is decided inside `GameDriver` itself (`load_or_new()`'s
existing empty/corrupt-both-start-fresh behavior), not duplicated here -- Empty and Corrupt both
resolve to the same confirm action, just displayed differently so a corrupt slot doesn't read as
merely unused.
"""

import random
from dataclasses import dataclass
from enum import Enum, auto

import pygame
import pygame.typing

from eye.gui.assets import SpriteAtlas
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.game_driver import GameDriver
from eye.gui.scene import Scene
from eye.persistence import save
from eye.persistence.codec import GameSnapshot, SaveDataError
from eye.persistence.port import SaveStore

_SLOT_COUNT = 3

_TITLE_FONT_SIZE = 28
_SLOT_LABEL_FONT_SIZE = 18
_SLOT_DETAIL_FONT_SIZE = 14
_FOOTER_FONT_SIZE = 14
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_EMPTY_COLOR: pygame.typing.ColorLike = "gray"
_CORRUPT_COLOR: pygame.typing.ColorLike = "orangered"
_CURSOR_COLOR: pygame.typing.ColorLike = "slategray"
_MARGIN = 8
_TITLE_TOP_MARGIN = 24
_SLOT_HEIGHT = 56
_SLOT_GAP = 10
_FOOTER_BOTTOM_MARGIN = 24

_TITLE = "The Eye of the Swarm"
_FOOTER = "Up/Down: select slot   Enter/Space: confirm"


class SlotStatus(Enum):
    EMPTY = auto()
    CORRUPT = auto()
    VALID = auto()


class MenuAction(Enum):
    MOVE_UP = auto()
    MOVE_DOWN = auto()
    CONFIRM = auto()


# pygame key -> MenuAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, MenuAction] = {
    pygame.K_UP: MenuAction.MOVE_UP,
    pygame.K_DOWN: MenuAction.MOVE_DOWN,
    pygame.K_RETURN: MenuAction.CONFIRM,
    pygame.K_SPACE: MenuAction.CONFIRM,
}


@dataclass(frozen=True, slots=True)
class _SlotView:
    number: int
    store: SaveStore
    status: SlotStatus
    snapshot: GameSnapshot | None


def _build_slot_view(number: int) -> _SlotView:
    store = save.store_for_slot(number)
    try:
        snapshot = save.peek(store)
    except SaveDataError:
        return _SlotView(number, store, SlotStatus.CORRUPT, None)
    status = SlotStatus.EMPTY if snapshot is None else SlotStatus.VALID
    return _SlotView(number, store, status, snapshot)


def _status_color(status: SlotStatus) -> pygame.typing.ColorLike:
    if status is SlotStatus.CORRUPT:
        return _CORRUPT_COLOR
    if status is SlotStatus.EMPTY:
        return _EMPTY_COLOR
    return _TEXT_COLOR


def _status_label(view: _SlotView) -> str:
    if view.status is SlotStatus.EMPTY:
        return "Empty (New Game)"
    if view.status is SlotStatus.CORRUPT:
        return "Corrupt save (New Game)"
    if view.snapshot is None:
        raise RuntimeError("a VALID slot view always carries a decoded snapshot")
    progress = max(view.snapshot.matured_turf_positions, default=0)
    return f"Spores: {view.snapshot.spores_available}   Progress: {progress} (Continue)"


class MenuScene:
    def __init__(self, atlas: SpriteAtlas, rng: random.Random) -> None:
        self._atlas = atlas
        self._rng = rng
        self._slots = tuple(_build_slot_view(number) for number in range(1, _SLOT_COUNT + 1))
        self._cursor = 0
        self._pending_action: MenuAction | None = None

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type != pygame.KEYDOWN:
            return
        action = KEY_ACTIONS.get(pygame_event.key)
        if action is not None:
            self._pending_action = action

    def update(self, dt: float) -> Scene | None:
        if self._pending_action is None:
            return None
        action = self._pending_action
        self._pending_action = None
        if action is MenuAction.MOVE_UP:
            self._cursor = (self._cursor - 1) % len(self._slots)
        elif action is MenuAction.MOVE_DOWN:
            self._cursor = (self._cursor + 1) % len(self._slots)
        elif action is MenuAction.CONFIRM:
            return self._confirm()
        return None

    def _confirm(self) -> Scene:
        view = self._slots[self._cursor]
        return GameDriver(
            self._atlas,
            self._rng,
            save_store=view.store,
            narration_store=save.narration_store_for_slot(view.number),
            combat_speed_multiplier=save.load_settings().combat_speed_multiplier,
        )

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        title_font = get_font(GameFont.ITHACA, _TITLE_FONT_SIZE)
        title = title_font.render(_TITLE, True, _TEXT_COLOR)
        surface.blit(title, (surface.get_width() // 2 - title.get_width() // 2, _TITLE_TOP_MARGIN))

        top = _TITLE_TOP_MARGIN + title.get_height() + _SLOT_GAP * 2
        for index, view in enumerate(self._slots):
            rect = pygame.Rect(_MARGIN, top, surface.get_width() - _MARGIN * 2, _SLOT_HEIGHT)
            if index == self._cursor:
                pygame.draw.rect(surface, _CURSOR_COLOR, rect)
            self._draw_slot(surface, rect, view)
            top += _SLOT_HEIGHT + _SLOT_GAP

        footer_font = get_font(GameFont.ITHACA, _FOOTER_FONT_SIZE)
        footer = footer_font.render(_FOOTER, True, _TEXT_COLOR)
        surface.blit(
            footer,
            (surface.get_width() // 2 - footer.get_width() // 2, surface.get_height() - _FOOTER_BOTTOM_MARGIN),
        )

    def _draw_slot(self, surface: pygame.Surface, rect: pygame.Rect, view: _SlotView) -> None:
        label_font = get_font(GameFont.ITHACA, _SLOT_LABEL_FONT_SIZE)
        label = label_font.render(f"Slot {view.number}", True, _TEXT_COLOR)
        surface.blit(label, (rect.x + _MARGIN, rect.y + _MARGIN // 2))

        detail_font = get_font(GameFont.ITHACA, _SLOT_DETAIL_FONT_SIZE)
        detail = detail_font.render(_status_label(view), True, _status_color(view.status))
        surface.blit(detail, (rect.x + _MARGIN, rect.y + _MARGIN // 2 + label.get_height()))
