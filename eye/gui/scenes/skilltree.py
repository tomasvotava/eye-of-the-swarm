"""SkillTreeScene: the between-generations spend screen (ADR 0009, PROJECT_BRIEF.md §5.3). Lays
out the catalog as a grid -- one row per (branch, sub_branch), tiers left to right within a row --
and lets the player purchase along a 2D cursor before continuing. Requests a `Continue` transition
when the player is done spending; `GameDriver` (ADR 0010) is the one that calls
`game.start_generation()` and constructs the next `ExplorationScene`. `on_purchase` is invoked
after every successful purchase so `GameDriver` can persist -- mirroring
`eye/tui/skilltree_menu.py::run()`'s own `on_purchase` hook -- without this scene needing to know
`eye.persistence` exists.
"""

from collections.abc import Callable
from enum import Enum, auto
from itertools import groupby

import pygame
import pygame.typing

from eye.gui.assets import SpriteAtlas
from eye.gui.fonts.fonts import GameFont, get_font
from eye.gui.play_scene import Continue, PlaySceneTransition
from eye.gui.widgets import SkillNodeState, SkillTreeLeaf, SpriteSkillTreeLeaf
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from eye.skilltree.state import SkillTree
from eye.skilltree.tree import SkillNode

_FONT_SIZE = 16
_ROW_LABEL_WIDTH = 80  # was 100 -- freed width the taller icon-bearing cells now need
_CELL_WIDTH = 150  # was 190 -- a ~36px icon plus a two-line name/effects caption, kept small
# enough to fit all three tier columns inside the 640px window
_ROW_HEIGHT = 40  # was 28 -- fits the icon height plus the two text lines SpriteSkillTreeLeaf draws
_ROW_GAP = 6
_BRANCH_GAP = 16  # extra vertical gap where a row's branch differs from the previous row's
_MARGIN = 8
_TEXT_COLOR: pygame.typing.ColorLike = "white"
_CURSOR_COLOR: pygame.typing.ColorLike = "slategray"

# Rows in catalog order, each row already tier-ordered: one row per (branch, sub_branch), grouped
# rather than assumed-fixed-width, since a row's tier count is a catalog fact, not a layout one.
_NODES: tuple[SkillNode, ...] = tuple(
    sorted(CATALOG.values(), key=lambda node: (node.id.branch.name, node.id.sub_branch.name, node.id.tier))
)
_ROWS: tuple[tuple[SkillNode, ...], ...] = tuple(
    tuple(group) for _, group in groupby(_NODES, key=lambda node: (node.id.branch, node.id.sub_branch))
)


class SkillTreeAction(Enum):
    MOVE_LEFT = auto()
    MOVE_RIGHT = auto()
    MOVE_UP = auto()
    MOVE_DOWN = auto()
    PURCHASE = auto()
    CONTINUE = auto()


# pygame key -> SkillTreeAction. Edit this mapping to reassign controls.
KEY_ACTIONS: dict[int, SkillTreeAction] = {
    pygame.K_LEFT: SkillTreeAction.MOVE_LEFT,
    pygame.K_RIGHT: SkillTreeAction.MOVE_RIGHT,
    pygame.K_UP: SkillTreeAction.MOVE_UP,
    pygame.K_DOWN: SkillTreeAction.MOVE_DOWN,
    pygame.K_RETURN: SkillTreeAction.PURCHASE,
    pygame.K_SPACE: SkillTreeAction.PURCHASE,
    pygame.K_c: SkillTreeAction.CONTINUE,
}


def _node_state(skill_tree: SkillTree, node: SkillNode) -> SkillNodeState:
    if skill_tree.is_purchased(node.id):
        return SkillNodeState.PURCHASED
    if skill_tree.can_purchase(node):
        return SkillNodeState.AVAILABLE
    return SkillNodeState.LOCKED


def _row_label(node: SkillNode) -> str:
    return f"{node.id.branch.name.title()} / {node.id.sub_branch.name.title()}"


class SkillTreeScene:
    def __init__(
        self,
        game: Game,
        atlas: SpriteAtlas,
        on_purchase: Callable[[], None],
        leaf_factory: Callable[[SpriteAtlas], SkillTreeLeaf] = SpriteSkillTreeLeaf,
    ) -> None:
        self._game = game
        self._atlas = atlas
        self._leaf = leaf_factory(atlas)
        self._on_purchase = on_purchase
        self._row = 0
        self._col = 0
        self._pending_action: SkillTreeAction | None = None
        self._last_message = "Spend spores before the next generation begins."

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        if pygame_event.type != pygame.KEYDOWN:
            return
        action = KEY_ACTIONS.get(pygame_event.key)
        if action is not None:
            self._pending_action = action

    def update(self, dt: float) -> PlaySceneTransition | None:
        if self._pending_action is None:
            return None
        action = self._pending_action
        self._pending_action = None

        if action is SkillTreeAction.MOVE_LEFT:
            self._col = (self._col - 1) % len(_ROWS[self._row])
        elif action is SkillTreeAction.MOVE_RIGHT:
            self._col = (self._col + 1) % len(_ROWS[self._row])
        elif action is SkillTreeAction.MOVE_UP:
            self._move_row(-1)
        elif action is SkillTreeAction.MOVE_DOWN:
            self._move_row(1)
        elif action is SkillTreeAction.PURCHASE:
            self._handle_purchase()
        elif action is SkillTreeAction.CONTINUE:
            return self._handle_continue()
        return None

    def _move_row(self, delta: int) -> None:
        self._row = (self._row + delta) % len(_ROWS)
        self._col = min(self._col, len(_ROWS[self._row]) - 1)

    def _handle_purchase(self) -> None:
        node = _ROWS[self._row][self._col]
        try:
            self._game.skill_tree.purchase(node)
        except RuntimeError as exc:
            self._last_message = str(exc)
            return
        self._on_purchase()
        self._last_message = f"Purchased {node.name or node.id}."

    def _handle_continue(self) -> PlaySceneTransition:
        return Continue()

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")
        self._draw_grid(surface)
        self._draw_hud(surface)

    def _draw_grid(self, surface: pygame.Surface) -> None:
        skill_tree = self._game.skill_tree
        font = get_font(GameFont.ITHACA, _FONT_SIZE)
        top = _MARGIN
        previous_branch = None
        for row_index, row in enumerate(_ROWS):
            branch = row[0].id.branch
            if previous_branch is not None and branch is not previous_branch:
                top += _BRANCH_GAP
            surface.blit(font.render(_row_label(row[0]), True, _TEXT_COLOR), (_MARGIN, top))
            for col_index, node in enumerate(row):
                rect = pygame.Rect(_MARGIN + _ROW_LABEL_WIDTH + col_index * _CELL_WIDTH, top, _CELL_WIDTH, _ROW_HEIGHT)
                if row_index == self._row and col_index == self._col:
                    pygame.draw.rect(surface, _CURSOR_COLOR, rect)
                self._leaf.render(surface, rect, node, _node_state(skill_tree, node))
            top += _ROW_HEIGHT + _ROW_GAP
            previous_branch = branch

    def _draw_hud(self, surface: pygame.Surface) -> None:
        font = get_font(GameFont.ITHACA, _FONT_SIZE)
        lines = [
            f"Spores available: {self._game.skill_tree.spores_available}",
            self._last_message,
            "Left/Right: tier   Up/Down: sub-branch   Enter/Space: purchase   C: continue",
        ]
        top = surface.get_height() - len(lines) * _FONT_SIZE - _MARGIN
        for index, line in enumerate(lines):
            surface.blit(font.render(line, True, _TEXT_COLOR), (_MARGIN, top + index * _FONT_SIZE))
