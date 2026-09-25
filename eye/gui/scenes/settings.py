"""SettingsScene: exposes the combat-speed multiplier and, where the platform allows, the window
scale (ADR 0017) as rows picked with Up/Down, each stepped through a small fixed set of values
with Left/Right. Every change is persisted via `save.settings_store()` immediately rather than
only on exit, and a window-scale change is applied to the window at once. Takes `back_scene`
rather than resolving one itself, mirroring `CreditsScene`'s constructor pattern -- whatever
constructs it decides how it is reached and dismissed. An optional `on_change` receives each newly
persisted snapshot, for a caller that holds a setting live (e.g. `GameDriver` when Settings is
opened in-game).
"""

import dataclasses
from collections.abc import Callable, Sequence
from enum import Enum, auto

import pygame
import pygame.typing

from eye.gui import window
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.scene import Scene
from eye.persistence import save
from eye.persistence.settings import SettingsSnapshot, WindowScale, encode_settings

_TITLE_FONT_SIZE = 28
_LABEL_FONT_SIZE = 20
_FOOTER_FONT_SIZE = 14
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_CURSOR_COLOR: pygame.typing.ColorLike = "slategray"
_TITLE_TOP_MARGIN = 24
_FOOTER_BOTTOM_MARGIN = 24
_ROWS_TOP_FRACTION = 0.4
_ROW_HEIGHT = 32
_ROW_WIDTH_FRACTION = 0.6

_TITLE = "Settings"
_FOOTER = "Up/Down: select   Left/Right: change   Escape: back"

# Fixed preset steps rather than a free scalar -- keeps the control to a single left/right cycle.
_COMBAT_SPEED_PRESETS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)

_WINDOW_SCALE_LABELS: dict[WindowScale, str] = {
    WindowScale.AUTO: "Auto",
    WindowScale.X1: "1x",
    WindowScale.X2: "2x",
    WindowScale.X3: "3x",
    WindowScale.X4: "4x",
    WindowScale.FULLSCREEN: "Fullscreen",
}


class SettingsRow(Enum):
    COMBAT_SPEED = auto()
    WINDOW_SCALE = auto()


class SettingsAction(Enum):
    PREVIOUS_ROW = auto()
    NEXT_ROW = auto()
    DECREASE = auto()
    INCREASE = auto()
    BACK = auto()


# pygame key -> SettingsAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, SettingsAction] = {
    pygame.K_UP: SettingsAction.PREVIOUS_ROW,
    pygame.K_DOWN: SettingsAction.NEXT_ROW,
    pygame.K_LEFT: SettingsAction.DECREASE,
    pygame.K_RIGHT: SettingsAction.INCREASE,
    pygame.K_ESCAPE: SettingsAction.BACK,
}


def _closest_preset_index(multiplier: float) -> int:
    return min(range(len(_COMBAT_SPEED_PRESETS)), key=lambda index: abs(_COMBAT_SPEED_PRESETS[index] - multiplier))


class SettingsScene:
    """`window_scales` are the scales to offer, defaulting to what this desktop supports; an empty
    sequence hides the window row, and a non-empty one must include `AUTO`, the fallback for a
    saved scale it lacks. `apply_window_scale` resizes the real window on a change."""

    def __init__(
        self,
        back_scene: Scene,
        on_change: Callable[[SettingsSnapshot], None] | None = None,
        window_scales: Sequence[WindowScale] | None = None,
        apply_window_scale: Callable[[WindowScale], None] = window.apply_window_scale,
    ) -> None:
        self._back_scene = back_scene
        self._on_change = on_change
        self._window_scales = tuple(window_scales) if window_scales is not None else window.desktop_window_scales()
        self._apply_window_scale = apply_window_scale
        self._rows = (SettingsRow.COMBAT_SPEED, *((SettingsRow.WINDOW_SCALE,) if self._window_scales else ()))
        self._row_index = 0
        self._settings = save.load_settings()
        self._preset_index = _closest_preset_index(self._settings.combat_speed_multiplier)
        self._window_scale = window.effective_window_scale(self._settings.window_scale, self._window_scales)
        self._pending_action: SettingsAction | None = None

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
        if action is SettingsAction.BACK:
            return self._back_scene
        if action is SettingsAction.PREVIOUS_ROW:
            self._row_index = (self._row_index - 1) % len(self._rows)
        elif action is SettingsAction.NEXT_ROW:
            self._row_index = (self._row_index + 1) % len(self._rows)
        else:
            self._step(-1 if action is SettingsAction.DECREASE else 1)
        return None

    def _step(self, delta: int) -> None:
        if self._rows[self._row_index] is SettingsRow.COMBAT_SPEED:
            self._apply_preset(self._preset_index + delta)
        else:
            self._step_window_scale(delta)

    def _apply_preset(self, index: int) -> None:
        clamped = max(0, min(len(_COMBAT_SPEED_PRESETS) - 1, index))
        if clamped == self._preset_index:
            return
        self._preset_index = clamped
        self._commit(dataclasses.replace(self._settings, combat_speed_multiplier=_COMBAT_SPEED_PRESETS[clamped]))

    def _step_window_scale(self, delta: int) -> None:
        current = self._window_scales.index(self._window_scale)
        clamped = max(0, min(len(self._window_scales) - 1, current + delta))
        if clamped == current:
            return
        self._window_scale = self._window_scales[clamped]
        self._commit(dataclasses.replace(self._settings, window_scale=self._window_scale))
        self._apply_window_scale(self._window_scale)

    def _commit(self, settings: SettingsSnapshot) -> None:
        self._settings = settings
        save.settings_store().save(encode_settings(settings))
        if self._on_change is not None:
            self._on_change(settings)

    def _row_label(self, row: SettingsRow) -> str:
        if row is SettingsRow.COMBAT_SPEED:
            return f"Combat speed: {self._settings.combat_speed_multiplier:.2f}x"
        return f"Window size: {_WINDOW_SCALE_LABELS[self._window_scale]}"

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        title_font = get_font(GameFont.ITHACA, _TITLE_FONT_SIZE)
        title = title_font.render(_TITLE, True, _TEXT_COLOR)
        surface.blit(title, (surface.get_width() // 2 - title.get_width() // 2, _TITLE_TOP_MARGIN))

        label_font = get_font(GameFont.ITHACA, _LABEL_FONT_SIZE)
        row_width = round(surface.get_width() * _ROW_WIDTH_FRACTION)
        top = round(surface.get_height() * _ROWS_TOP_FRACTION)
        for index, row in enumerate(self._rows):
            rect = pygame.Rect(0, 0, row_width, _ROW_HEIGHT)
            rect.midtop = (surface.get_width() // 2, top + index * _ROW_HEIGHT)
            if index == self._row_index:
                pygame.draw.rect(surface, _CURSOR_COLOR, rect)
            label = label_font.render(self._row_label(row), True, _TEXT_COLOR)
            surface.blit(label, label.get_rect(center=rect.center))

        footer_font = get_font(GameFont.ITHACA, _FOOTER_FONT_SIZE)
        footer = footer_font.render(_FOOTER, True, _TEXT_COLOR)
        surface.blit(
            footer,
            (surface.get_width() // 2 - footer.get_width() // 2, surface.get_height() - _FOOTER_BOTTOM_MARGIN),
        )
