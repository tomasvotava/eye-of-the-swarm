"""ExplorationScene: the screen-by-screen driver for the Seed/Turf loop (ADR 0009,
PROJECT_BRIEF.md §6). Advances `Generation.advance()` on keypress, offers `plant_seed()` once the
current Seed is ready, and requests an `EnterCombat` transition the moment an `EnemyEncountered`
event surfaces -- the only trigger among those in `eye.exploration.encounters` that needs its own
screen.
"""

from enum import Enum, auto

import pygame
import pygame.typing

from eye.exploration.events import EffectGranted, EnemyEncountered, NothingHappened, ResourceGranted, SeedPlanted
from eye.gui.assets import SpriteAtlas, SpriteKey
from eye.gui.scene import EnterCombat, SceneTransition
from eye.session.game import Game
from eye.session.generation import Generation

_FONT_SIZE = 20
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_HUD_MARGIN = 8
_ICON_MARGIN = 8

type _ScreenEvent = EffectGranted | ResourceGranted | NothingHappened


class ExplorationAction(Enum):
    ADVANCE = auto()
    PLANT_SEED = auto()


# pygame key -> ExplorationAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, ExplorationAction] = {
    pygame.K_SPACE: ExplorationAction.ADVANCE,
    pygame.K_RETURN: ExplorationAction.ADVANCE,
    pygame.K_p: ExplorationAction.PLANT_SEED,
}

_font: pygame.font.Font | None = None


def _get_font() -> pygame.font.Font:
    # Constructed lazily rather than at import time: pygame.font must already be initialized,
    # which module import order doesn't guarantee (mirrors eye.gui.widgets._get_font()).
    global _font
    if _font is None:
        _font = pygame.font.Font(None, _FONT_SIZE)
    return _font


def _describe_screen_event(event: _ScreenEvent) -> str:
    if isinstance(event, EffectGranted):
        return f"You feel {event.effect.name.replace('_', ' ').title()} take hold."
    if isinstance(event, ResourceGranted):
        return f"You gain {event.amount} ({event.kind.name.replace('_', ' ').title()})."
    return "Nothing happens here."


class ExplorationScene:
    def __init__(self, generation: Generation, game: Game, atlas: SpriteAtlas) -> None:
        self._generation = generation
        self._game = game
        self._atlas = atlas
        self._pending_action: ExplorationAction | None = None
        self._last_message = "You explore outward from the hive."

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type != pygame.KEYDOWN:
            return
        action = KEY_ACTIONS.get(pygame_event.key)
        if action is not None:
            self._pending_action = action

    def update(self, dt: float) -> SceneTransition | None:
        if self._pending_action is None:
            return None
        action = self._pending_action
        self._pending_action = None

        if action is ExplorationAction.PLANT_SEED:
            self._handle_plant_seed()
            return None
        return self._handle_advance()

    def _handle_plant_seed(self) -> None:
        if not self._generation.is_seed_ready:
            return
        events = self._generation.plant_seed()
        planted = next((event for event in events if isinstance(event, SeedPlanted)), None)
        if planted is not None:
            self._last_message = f"You plant a seed at screen {planted.position}."

    def _handle_advance(self) -> SceneTransition | None:
        events = self._generation.advance()

        encounter = next((event for event in events if isinstance(event, EnemyEncountered)), None)
        if encounter is not None:
            return EnterCombat(generation=self._generation, game=self._game, encounter=encounter)

        screen_event = next(
            (event for event in events if isinstance(event, EffectGranted | ResourceGranted | NothingHappened)), None
        )
        if screen_event is not None:
            self._last_message = _describe_screen_event(screen_event)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        self._draw_background(surface)
        self._draw_player(surface)
        self._draw_status_icons(surface)
        self._draw_hud(surface)

    def _draw_background(self, surface: pygame.Surface) -> None:
        background = pygame.transform.scale(self._atlas.get(SpriteKey.BACKGROUND), surface.get_size())
        surface.blit(background, (0, 0))

    def _draw_player(self, surface: pygame.Surface) -> None:
        player = self._atlas.get(SpriteKey.PLAYER)
        surface.blit(player, player.get_rect(center=surface.get_rect().center))

    def _draw_status_icons(self, surface: pygame.Surface) -> None:
        x = _ICON_MARGIN
        if self._generation.is_seed_ready:
            seed = self._atlas.get(SpriteKey.SEED)
            surface.blit(seed, (x, _ICON_MARGIN))
            x += seed.get_width() + _ICON_MARGIN
        if self._game.matured_turf_positions:
            turf = self._atlas.get(SpriteKey.TURF)
            surface.blit(turf, (x, _ICON_MARGIN))

    def _draw_hud(self, surface: pygame.Surface) -> None:
        font = _get_font()
        lines = [
            f"Seed ready to plant: {'yes' if self._generation.is_seed_ready else 'no'}",
            f"Spores this life: {self._generation.spores_gained}",
            self._last_message,
            "Space/Enter: advance   P: plant seed",
        ]
        top = surface.get_height() - len(lines) * _FONT_SIZE - _HUD_MARGIN
        for index, line in enumerate(lines):
            surface.blit(font.render(line, True, _TEXT_COLOR), (_HUD_MARGIN, top + index * _FONT_SIZE))
