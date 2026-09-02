"""SkillTreeScene: the between-generations spend screen (ADR 0009, PROJECT_BRIEF.md §5.3). Lists
every catalog node via `SkillTreeLeaf`, lets the player purchase along a cursor, and hands off to a
fresh `ExplorationScene` once they continue -- `game.start_generation()` is what actually begins
the next life; this scene only decides when that happens.
"""

from collections.abc import Callable
from enum import Enum, auto

import pygame
import pygame.typing

from eye.gui.assets import SpriteAtlas
from eye.gui.scene import Scene
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.widgets import SkillTreeLeaf, TextSkillTreeLeaf
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from eye.skilltree.tree import SkillNode

_FONT_SIZE = 20
_ROW_HEIGHT = 24
_MARGIN = 8
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_CURSOR_COLOR: pygame.typing.ColorLike = "slategray"

_NODES: tuple[SkillNode, ...] = tuple(
    sorted(CATALOG.values(), key=lambda node: (node.id.branch.name, node.id.sub_branch.name, node.id.tier))
)


class SkillTreeAction(Enum):
    MOVE_UP = auto()
    MOVE_DOWN = auto()
    PURCHASE = auto()
    CONTINUE = auto()


# pygame key -> SkillTreeAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, SkillTreeAction] = {
    pygame.K_UP: SkillTreeAction.MOVE_UP,
    pygame.K_DOWN: SkillTreeAction.MOVE_DOWN,
    pygame.K_RETURN: SkillTreeAction.PURCHASE,
    pygame.K_SPACE: SkillTreeAction.PURCHASE,
    pygame.K_c: SkillTreeAction.CONTINUE,
}

_font: pygame.font.Font | None = None


def _get_font() -> pygame.font.Font:
    # Constructed lazily rather than at import time: pygame.font must already be initialized,
    # which module import order doesn't guarantee (mirrors eye.gui.widgets._get_font()).
    global _font
    if _font is None:
        _font = pygame.font.Font(None, _FONT_SIZE)
    return _font


class SkillTreeScene:
    def __init__(
        self,
        game: Game,
        atlas: SpriteAtlas,
        leaf_factory: Callable[[], SkillTreeLeaf] = TextSkillTreeLeaf,
    ) -> None:
        self._game = game
        self._atlas = atlas
        self._leaf = leaf_factory()
        self._cursor = 0
        self._pending_action: SkillTreeAction | None = None
        self._last_message = "Spend spores before the next generation begins."

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

        if action is SkillTreeAction.MOVE_UP:
            self._cursor = (self._cursor - 1) % len(_NODES)
        elif action is SkillTreeAction.MOVE_DOWN:
            self._cursor = (self._cursor + 1) % len(_NODES)
        elif action is SkillTreeAction.PURCHASE:
            self._handle_purchase()
        elif action is SkillTreeAction.CONTINUE:
            return self._handle_continue()
        return None

    def _handle_purchase(self) -> None:
        node = _NODES[self._cursor]
        try:
            self._game.skill_tree.purchase(node)
        except RuntimeError as exc:
            self._last_message = str(exc)
            return
        self._last_message = f"Purchased {node.name or node.id}."

    def _handle_continue(self) -> Scene:
        generation = self._game.start_generation()
        return ExplorationScene(generation, self._game, self._atlas)

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        self._draw_nodes(surface)
        self._draw_hud(surface)

    def _draw_nodes(self, surface: pygame.Surface) -> None:
        skill_tree = self._game.skill_tree
        row_width = surface.get_width() - 2 * _MARGIN
        for index, node in enumerate(_NODES):
            rect = pygame.Rect(_MARGIN, _MARGIN + index * _ROW_HEIGHT, row_width, _ROW_HEIGHT)
            if index == self._cursor:
                pygame.draw.rect(surface, _CURSOR_COLOR, rect)
            locked = not (skill_tree.is_purchased(node.id) or skill_tree.can_purchase(node))
            self._leaf.render(surface, rect, node, locked)

    def _draw_hud(self, surface: pygame.Surface) -> None:
        font = _get_font()
        lines = [
            f"Spores available: {self._game.skill_tree.spores_available}",
            self._last_message,
            "Up/Down: select   Enter/Space: purchase   C: continue",
        ]
        top = surface.get_height() - len(lines) * _FONT_SIZE - _MARGIN
        for index, line in enumerate(lines):
            surface.blit(font.render(line, True, _TEXT_COLOR), (_MARGIN, top + index * _FONT_SIZE))
