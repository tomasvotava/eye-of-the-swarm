import pygame

from eye.combat.effects import EffectName
from eye.gui.widgets import EFFECT_DESCRIPTIONS, SkillNodeState, TextBuffIcon, TextSkillTreeLeaf
from eye.skilltree.tree import Branch, SkillNode, SkillNodeId, SubBranch


def _surface() -> pygame.Surface:
    return pygame.Surface((64, 64))


def _node() -> SkillNode:
    return SkillNode(id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0), cost=3, name="Test Node")


def test_text_buff_icon_stores_the_given_effect() -> None:
    icon = TextBuffIcon(EffectName.FIBROUS)

    assert icon.effect is EffectName.FIBROUS


def test_text_buff_icon_render_does_not_raise_for_a_buff() -> None:
    TextBuffIcon(EffectName.FIBROUS).render(_surface(), pygame.Vector2(0, 0))


def test_text_buff_icon_render_does_not_raise_for_a_debuff() -> None:
    TextBuffIcon(EffectName.TOXICITY).render(_surface(), pygame.Vector2(0, 0))


def test_text_skill_tree_leaf_render_does_not_raise_when_locked() -> None:
    TextSkillTreeLeaf().render(_surface(), pygame.Rect(0, 0, 64, 16), _node(), SkillNodeState.LOCKED)


def test_text_skill_tree_leaf_render_does_not_raise_when_available() -> None:
    TextSkillTreeLeaf().render(_surface(), pygame.Rect(0, 0, 64, 16), _node(), SkillNodeState.AVAILABLE)


def test_text_skill_tree_leaf_render_does_not_raise_when_purchased() -> None:
    TextSkillTreeLeaf().render(_surface(), pygame.Rect(0, 0, 64, 16), _node(), SkillNodeState.PURCHASED)


def test_effect_descriptions_covers_every_effect_name() -> None:
    for effect in EffectName:
        assert effect in EFFECT_DESCRIPTIONS
        assert EFFECT_DESCRIPTIONS[effect]  # non-empty
