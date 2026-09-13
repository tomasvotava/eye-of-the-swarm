import random
from collections.abc import Callable
from pathlib import Path

import pygame
import pytest

from eye.gui.assets import build_art_atlas, build_placeholder_atlas
from eye.gui.play_scene import Continue
from eye.gui.scenes.skilltree import _ROWS, KEY_ACTIONS, SkillTreeAction, SkillTreeScene, _node_state
from eye.gui.widgets import SkillNodeState
from eye.session.game import Game
from eye.skilltree.catalog import CATALOG
from eye.skilltree.state import SkillTree

_SHIPPED_SPRITES_DIR = Path("eye/gui/sprites")


def _noop() -> None:
    pass


def _game() -> Game:
    return Game(random.Random())


def _scene(spores: int = 0, on_purchase: Callable[[], None] = _noop) -> tuple[SkillTreeScene, Game]:
    game = _game()
    game.skill_tree.add_spores(spores)
    return SkillTreeScene(game, build_placeholder_atlas(), on_purchase=on_purchase), game


def _press(scene: SkillTreeScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_key_actions_maps_the_expected_controls() -> None:
    assert KEY_ACTIONS[pygame.K_LEFT] is SkillTreeAction.MOVE_LEFT
    assert KEY_ACTIONS[pygame.K_RIGHT] is SkillTreeAction.MOVE_RIGHT
    assert KEY_ACTIONS[pygame.K_UP] is SkillTreeAction.MOVE_UP
    assert KEY_ACTIONS[pygame.K_DOWN] is SkillTreeAction.MOVE_DOWN
    assert KEY_ACTIONS[pygame.K_RETURN] is SkillTreeAction.PURCHASE
    assert KEY_ACTIONS[pygame.K_SPACE] is SkillTreeAction.PURCHASE
    assert KEY_ACTIONS[pygame.K_c] is SkillTreeAction.CONTINUE


def test_rows_group_the_catalog_by_branch_and_sub_branch_in_tier_order() -> None:
    for row in _ROWS:
        assert [node.id.tier for node in row] == sorted(node.id.tier for node in row)
        assert len({(node.id.branch, node.id.sub_branch) for node in row}) == 1


def test_rows_do_not_fragment_a_branch_sub_branch_group_across_multiple_rows() -> None:
    # _ROWS is built with itertools.groupby, which only merges *contiguous* runs of equal key --
    # it stays correct only as long as _NODES is sorted by (branch, sub_branch) first. If that
    # sort were ever dropped, the same (branch, sub_branch) pair would split across separate rows
    # instead of raising, so assert directly against that failure mode rather than just the
    # current output.
    keys = [(row[0].id.branch, row[0].id.sub_branch) for row in _ROWS]
    assert len(keys) == len(set(keys))
    assert sum(len(row) for row in _ROWS) == len(CATALOG)


def test_node_state_reflects_purchased_available_and_locked() -> None:
    skill_tree = SkillTree()
    tier0, tier1 = _ROWS[0][0], _ROWS[0][1]

    assert _node_state(skill_tree, tier1) is SkillNodeState.LOCKED  # prerequisite missing

    skill_tree.add_spores(tier0.cost)
    assert _node_state(skill_tree, tier0) is SkillNodeState.AVAILABLE

    skill_tree.purchase(tier0)
    assert _node_state(skill_tree, tier0) is SkillNodeState.PURCHASED


def test_update_with_no_pending_action_returns_none() -> None:
    scene, _ = _scene()

    assert scene.update(0.016) is None


def test_unmapped_key_is_ignored() -> None:
    scene, _ = _scene()

    _press(scene, pygame.K_z)

    assert scene.update(0.016) is None


def test_non_keydown_event_is_ignored() -> None:
    scene, _ = _scene()

    scene.handle_pygame_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_DOWN))

    assert scene.update(0.016) is None


def test_purchase_action_buys_the_selected_node_when_affordable() -> None:
    node = _ROWS[0][0]
    scene, game = _scene(spores=node.cost)

    _press(scene, pygame.K_RETURN)
    scene.update(0.016)

    assert game.skill_tree.is_purchased(node.id)
    assert game.skill_tree.spores_available == 0


def test_purchase_action_invokes_the_on_purchase_hook() -> None:
    node = _ROWS[0][0]
    calls = 0

    def on_purchase() -> None:
        nonlocal calls
        calls += 1

    scene, _ = _scene(spores=node.cost, on_purchase=on_purchase)

    _press(scene, pygame.K_RETURN)
    scene.update(0.016)

    assert calls == 1


def test_purchase_action_without_enough_spores_does_not_invoke_the_on_purchase_hook() -> None:
    node = _ROWS[0][0]
    calls = 0

    def on_purchase() -> None:
        nonlocal calls
        calls += 1

    scene, _ = _scene(spores=node.cost - 1, on_purchase=on_purchase)

    _press(scene, pygame.K_SPACE)
    scene.update(0.016)

    assert calls == 0


def test_purchase_action_is_a_no_op_without_enough_spores() -> None:
    node = _ROWS[0][0]
    scene, game = _scene(spores=node.cost - 1)

    _press(scene, pygame.K_SPACE)
    scene.update(0.016)

    assert not game.skill_tree.is_purchased(node.id)
    assert game.skill_tree.spores_available == node.cost - 1


def test_move_right_then_purchase_is_a_no_op_when_the_prerequisite_tier_is_missing() -> None:
    node = _ROWS[0][1]  # tier 1 of the first row -- requires tier 0, purchased separately
    scene, game = _scene(spores=node.cost)

    _press(scene, pygame.K_RIGHT)
    scene.update(0.016)
    _press(scene, pygame.K_RETURN)
    scene.update(0.016)

    assert not game.skill_tree.is_purchased(node.id)


def test_move_left_from_the_first_tier_wraps_to_the_last_and_back() -> None:
    # MOVE_LEFT from column 0 must wrap to the row's last tier rather than go negative; following
    # it with MOVE_RIGHT should land back on tier 0, confirmed by purchasing it.
    node = _ROWS[0][0]
    scene, game = _scene(spores=node.cost)

    _press(scene, pygame.K_LEFT)
    scene.update(0.016)
    _press(scene, pygame.K_RIGHT)
    scene.update(0.016)
    _press(scene, pygame.K_RETURN)
    scene.update(0.016)

    assert game.skill_tree.is_purchased(node.id)


def test_move_up_from_the_first_row_wraps_to_the_last_and_back() -> None:
    # Same wraparound guarantee as tier navigation, but across rows (sub-branches).
    node = _ROWS[0][0]
    scene, game = _scene(spores=node.cost)

    _press(scene, pygame.K_UP)
    scene.update(0.016)
    _press(scene, pygame.K_DOWN)
    scene.update(0.016)
    _press(scene, pygame.K_RETURN)
    scene.update(0.016)

    assert game.skill_tree.is_purchased(node.id)


def test_continue_action_requests_a_continue_transition() -> None:
    scene, _ = _scene()

    _press(scene, pygame.K_c)
    transition = scene.update(0.016)

    assert transition == Continue()


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    scene, _ = _scene()

    scene.draw(pygame.Surface(surface_size))


def test_card_for_selected_node_reflects_the_cursor_position() -> None:
    scene, _ = _scene()

    card = scene._card_for_selected_node()

    expected = _ROWS[0][0]
    assert card.title == expected.name
    assert card.description == expected.description


def test_card_for_selected_node_updates_immediately_when_the_cursor_moves() -> None:
    scene, _ = _scene()
    before = scene._card_for_selected_node()

    _press(scene, pygame.K_RIGHT)
    scene.update(0.016)
    after = scene._card_for_selected_node()

    assert after.title == _ROWS[0][1].name
    assert after.title != before.title


def test_card_for_selected_node_builds_for_every_shipped_node_and_state() -> None:
    game = _game()
    atlas = build_art_atlas(_SHIPPED_SPRITES_DIR)
    scene = SkillTreeScene(game, atlas, on_purchase=lambda: None)
    for row_index, row in enumerate(_ROWS):
        for col_index, _node in enumerate(row):
            scene._row, scene._col = row_index, col_index
            card = scene._card_for_selected_node()
            assert card.title
