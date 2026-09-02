import random

import pygame
import pytest

from eye.gui.assets import build_placeholder_atlas
from eye.gui.scenes.exploration import ExplorationScene
from eye.gui.scenes.skilltree import _NODES, KEY_ACTIONS, SkillTreeAction, SkillTreeScene
from eye.session.game import Game


def _scene(spores: int = 0) -> tuple[SkillTreeScene, Game]:
    game = Game(random.Random())
    game.skill_tree.add_spores(spores)
    return SkillTreeScene(game, build_placeholder_atlas()), game


def _press(scene: SkillTreeScene, key: int) -> None:
    scene.handle_pygame_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def test_key_actions_maps_the_expected_controls() -> None:
    assert KEY_ACTIONS[pygame.K_UP] is SkillTreeAction.MOVE_UP
    assert KEY_ACTIONS[pygame.K_DOWN] is SkillTreeAction.MOVE_DOWN
    assert KEY_ACTIONS[pygame.K_RETURN] is SkillTreeAction.PURCHASE
    assert KEY_ACTIONS[pygame.K_SPACE] is SkillTreeAction.PURCHASE
    assert KEY_ACTIONS[pygame.K_c] is SkillTreeAction.CONTINUE


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
    node = _NODES[0]
    scene, game = _scene(spores=node.cost)

    _press(scene, pygame.K_RETURN)
    scene.update(0.016)

    assert game.skill_tree.is_purchased(node.id)
    assert game.skill_tree.spores_available == 0


def test_purchase_action_is_a_no_op_without_enough_spores() -> None:
    node = _NODES[0]
    scene, game = _scene(spores=node.cost - 1)

    _press(scene, pygame.K_SPACE)
    scene.update(0.016)

    assert not game.skill_tree.is_purchased(node.id)
    assert game.skill_tree.spores_available == node.cost - 1


def test_purchase_action_is_a_no_op_when_the_prerequisite_tier_is_missing() -> None:
    # _NODES[1] is the second node in its (branch, sub_branch) group, i.e. tier 1 -- purchasing it
    # before its tier-0 prerequisite must fail even with enough spores banked.
    node = _NODES[1]
    scene, game = _scene(spores=node.cost)

    _press(scene, pygame.K_DOWN)
    scene.update(0.016)
    _press(scene, pygame.K_RETURN)
    scene.update(0.016)

    assert not game.skill_tree.is_purchased(node.id)


def test_move_up_from_the_first_node_wraps_to_the_last_and_back() -> None:
    # MOVE_UP from index 0 must wrap to len(_NODES) - 1 rather than go negative; following it with
    # MOVE_DOWN should land back on the first node, confirmed by purchasing it.
    node = _NODES[0]
    scene, game = _scene(spores=node.cost)

    _press(scene, pygame.K_UP)
    scene.update(0.016)
    _press(scene, pygame.K_DOWN)
    scene.update(0.016)
    _press(scene, pygame.K_RETURN)
    scene.update(0.016)

    assert game.skill_tree.is_purchased(node.id)


def test_continue_action_starts_a_new_generation_and_returns_an_exploration_scene() -> None:
    scene, game = _scene()

    _press(scene, pygame.K_c)
    next_scene = scene.update(0.016)

    assert isinstance(next_scene, ExplorationScene)
    assert game.matured_turf_positions == ()


@pytest.mark.parametrize("surface_size", [(64, 64), (800, 600)])
def test_draw_does_not_raise(surface_size: tuple[int, int]) -> None:
    scene, _ = _scene()

    scene.draw(pygame.Surface(surface_size))
