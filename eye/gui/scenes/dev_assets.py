"""DevAssetViewerScene: a developer-only Scene that pages through every SpriteKey in a SpriteAtlas
with its name, so placeholder (and later, real) art can be inspected without stepping through the
generational loop (ADR 0009). Wired in behind a dev-only entry point in app.py -- it never appears
in the normal exploration -> combat -> skill-tree -> rebirth loop.
"""

from __future__ import annotations

from enum import Enum, StrEnum, auto
from typing import TYPE_CHECKING

import pygame

from eye.gui.animation import Animator
from eye.gui.assets import SpriteAtlas, SpriteKey
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.scene import Scene
from eye.gui.scenes.exploration import PlayerAnimationState

if TYPE_CHECKING:
    import pygame.typing

_FONT_SIZE = 14
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_MARGIN = 8
_SPRITE_SCALE = 8  # placeholder sprites are tiny; enlarge them for visibility while browsing

_KEYS: tuple[SpriteKey, ...] = tuple(SpriteKey)
_ENEMY_KEYS: tuple[SpriteKey, ...] = (
    SpriteKey.BEATLE,
    SpriteKey.FLEA,
    SpriteKey.GOLEM,
    SpriteKey.PHIDIZVIK,
    SpriteKey.TUMBLEWEED,
)


class EnemyAnimationState(StrEnum):
    """Dev-viewer-only preview states, matching the idle/attack/hit clips shipped per enemy
    directory -- not the combat domain's eventual state type, which combat wiring defines
    separately when it lands.
    """

    IDLE = "idle"
    ATTACK = "attack"
    HIT = "hit"


class DevAssetViewerAction(Enum):
    NEXT = auto()
    PREVIOUS = auto()
    NEXT_STATE = auto()
    PREVIOUS_STATE = auto()


# pygame key -> DevAssetViewerAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, DevAssetViewerAction] = {
    pygame.K_RIGHT: DevAssetViewerAction.NEXT,
    pygame.K_LEFT: DevAssetViewerAction.PREVIOUS,
    pygame.K_UP: DevAssetViewerAction.NEXT_STATE,
    pygame.K_DOWN: DevAssetViewerAction.PREVIOUS_STATE,
}


class DevAssetViewerScene:
    def __init__(self, atlas: SpriteAtlas) -> None:
        self._atlas = atlas
        self._index = 0
        self._pending_action: DevAssetViewerAction | None = None
        self._player_animator: Animator[PlayerAnimationState] | None = None
        if atlas.has_animation_set(SpriteKey.PLAYER):
            self._player_animator = Animator(
                atlas.get_animation_set(SpriteKey.PLAYER, PlayerAnimationState),
                initial_state=PlayerAnimationState.IDLE,
            )
        self._enemy_state = EnemyAnimationState.IDLE
        self._enemy_animators: dict[SpriteKey, Animator[EnemyAnimationState]] = {
            key: Animator(atlas.get_animation_set(key, EnemyAnimationState), initial_state=EnemyAnimationState.IDLE)
            for key in _ENEMY_KEYS
            if atlas.has_animation_set(key)
        }

    @property
    def current_key(self) -> SpriteKey:
        return _KEYS[self._index]

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type != pygame.KEYDOWN:
            return
        action = KEY_ACTIONS.get(pygame_event.key)
        if action is not None:
            self._pending_action = action

    def update(self, dt: float) -> Scene | None:
        if self._pending_action is not None:
            action = self._pending_action
            self._pending_action = None
            match action:
                case DevAssetViewerAction.NEXT:
                    self._index = (self._index + 1) % len(_KEYS)
                case DevAssetViewerAction.PREVIOUS:
                    self._index = (self._index - 1) % len(_KEYS)
                case DevAssetViewerAction.NEXT_STATE:
                    self._cycle_enemy_state(1)
                case DevAssetViewerAction.PREVIOUS_STATE:
                    self._cycle_enemy_state(-1)
        if self._player_animator is not None:
            self._player_animator.update(dt)
        current_enemy_animator = self._enemy_animators.get(self.current_key)
        if current_enemy_animator is not None:
            current_enemy_animator.set_state(self._enemy_state)
            current_enemy_animator.update(dt)
        return None

    def _cycle_enemy_state(self, delta: int) -> None:
        states = tuple(EnemyAnimationState)
        self._enemy_state = states[(states.index(self._enemy_state) + delta) % len(states)]

    def _current_sprite(self, key: SpriteKey) -> pygame.Surface:
        if key is SpriteKey.PLAYER and self._player_animator is not None:
            return self._player_animator.current_frame()
        enemy_animator = self._enemy_animators.get(key)
        if enemy_animator is not None:
            return enemy_animator.current_frame()
        return self._atlas.get(key)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        key = self.current_key
        sprite = pygame.transform.scale_by(self._current_sprite(key), _SPRITE_SCALE)
        surface.blit(sprite, sprite.get_rect(center=surface.get_rect().center))
        self._draw_hud(surface, key)

    def _draw_hud(self, surface: pygame.Surface, key: SpriteKey) -> None:
        font = get_font(GameFont.ITHACA, _FONT_SIZE)
        lines = [
            f"{key.value}  ({self._index + 1}/{len(_KEYS)})",
            "Left/Right: previous/next sprite",
        ]
        if key in self._enemy_animators:
            lines.append(f"state: {self._enemy_state.value}  (Up/Down: previous/next state)")
        for index, line in enumerate(lines):
            surface.blit(font.render(line, True, _TEXT_COLOR), (_MARGIN, _MARGIN + index * _FONT_SIZE))
