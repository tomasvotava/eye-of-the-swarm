"""SettingsScene: exposes the combat-speed multiplier (ADR 0017) as a small fixed set of preset
values stepped with Left/Right, persisted via `save.settings_store()` immediately on every change
rather than only on exit. Takes `back_scene` rather than resolving one itself, mirroring
`CreditsScene`'s constructor pattern -- whatever constructs it decides how it is reached and
dismissed.
"""

from enum import Enum, auto

import pygame
import pygame.typing

from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.scene import Scene
from eye.persistence import save
from eye.persistence.settings import SETTINGS_SCHEMA_VERSION, SettingsSnapshot, encode_settings

_TITLE_FONT_SIZE = 28
_LABEL_FONT_SIZE = 20
_FOOTER_FONT_SIZE = 14
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_TITLE_TOP_MARGIN = 24
_FOOTER_BOTTOM_MARGIN = 24
_LABEL_TOP_FRACTION = 0.45

_TITLE = "Settings"
_FOOTER = "Left/Right: change speed   Escape: back"

# Fixed preset steps rather than a free scalar -- keeps the control to a single left/right cycle.
_COMBAT_SPEED_PRESETS: tuple[float, ...] = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0)


class SettingsAction(Enum):
    DECREASE_SPEED = auto()
    INCREASE_SPEED = auto()
    BACK = auto()


# pygame key -> SettingsAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, SettingsAction] = {
    pygame.K_LEFT: SettingsAction.DECREASE_SPEED,
    pygame.K_RIGHT: SettingsAction.INCREASE_SPEED,
    pygame.K_ESCAPE: SettingsAction.BACK,
}


def _closest_preset_index(multiplier: float) -> int:
    return min(range(len(_COMBAT_SPEED_PRESETS)), key=lambda index: abs(_COMBAT_SPEED_PRESETS[index] - multiplier))


class SettingsScene:
    def __init__(self, back_scene: Scene) -> None:
        self._back_scene = back_scene
        self._settings = save.load_settings()
        self._preset_index = _closest_preset_index(self._settings.combat_speed_multiplier)
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
        if action is SettingsAction.DECREASE_SPEED:
            self._apply_preset(self._preset_index - 1)
        elif action is SettingsAction.INCREASE_SPEED:
            self._apply_preset(self._preset_index + 1)
        return None

    def _apply_preset(self, index: int) -> None:
        clamped = max(0, min(len(_COMBAT_SPEED_PRESETS) - 1, index))
        if clamped == self._preset_index:
            return
        self._preset_index = clamped
        self._settings = SettingsSnapshot(
            schema_version=SETTINGS_SCHEMA_VERSION,
            combat_speed_multiplier=_COMBAT_SPEED_PRESETS[clamped],
        )
        save.settings_store().save(encode_settings(self._settings))

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        title_font = get_font(GameFont.ITHACA, _TITLE_FONT_SIZE)
        title = title_font.render(_TITLE, True, _TEXT_COLOR)
        surface.blit(title, (surface.get_width() // 2 - title.get_width() // 2, _TITLE_TOP_MARGIN))

        label_font = get_font(GameFont.ITHACA, _LABEL_FONT_SIZE)
        label_text = f"Combat speed: {self._settings.combat_speed_multiplier:.2f}x"
        label = label_font.render(label_text, True, _TEXT_COLOR)
        surface.blit(
            label,
            (surface.get_width() // 2 - label.get_width() // 2, round(surface.get_height() * _LABEL_TOP_FRACTION)),
        )

        footer_font = get_font(GameFont.ITHACA, _FOOTER_FONT_SIZE)
        footer = footer_font.render(_FOOTER, True, _TEXT_COLOR)
        surface.blit(
            footer,
            (surface.get_width() // 2 - footer.get_width() // 2, surface.get_height() - _FOOTER_BOTTOM_MARGIN),
        )
