import pygame

from eye.combat.effects import EffectName
from eye.gui.assets import SpriteAtlas, SpriteKey, build_placeholder_atlas
from eye.gui.widgets import (
    EFFECT_DESCRIPTIONS,
    NonEffectIcon,
    SkillNodeState,
    SpriteBuffIcon,
    TextBuffIcon,
    TextSkillTreeLeaf,
)
from eye.skilltree.tree import Branch, SkillNode, SkillNodeId, SubBranch


def _surface() -> pygame.Surface:
    return pygame.Surface((64, 64))


def _node() -> SkillNode:
    return SkillNode(id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0), cost=3, name="Test Node")


def test_text_buff_icon_stores_the_given_effect() -> None:
    icon = TextBuffIcon(EffectName.FIBROUS)

    assert icon.effect is EffectName.FIBROUS


def test_text_buff_icon_render_does_not_raise_for_a_buff() -> None:
    TextBuffIcon(EffectName.FIBROUS).render(_surface(), pygame.Vector2(0, 0), 64)


def test_text_buff_icon_render_does_not_raise_for_a_debuff() -> None:
    TextBuffIcon(EffectName.TOXICITY).render(_surface(), pygame.Vector2(0, 0), 64)


def test_sprite_buff_icon_renders_the_effect_sprite_scaled_to_the_requested_size() -> None:
    sprite = pygame.Surface((4, 4))
    sprite.fill("crimson")
    atlas = SpriteAtlas({SpriteKey.EFFECT_FIBROUS: sprite})
    destination = pygame.Surface((64, 64))
    destination.fill("black")

    SpriteBuffIcon(atlas, EffectName.FIBROUS).render(destination, pygame.Vector2(0, 0), 32)

    assert destination.get_at((16, 16)) == pygame.Color("crimson")
    assert destination.get_at((33, 33)) == pygame.Color("black")  # just outside the 32x32 box, untouched


def test_sprite_buff_icon_render_does_not_raise_for_every_effect_name() -> None:
    # Also exercises RESONANCE, which has no art yet -- SpriteAtlas falls back to the placeholder
    # shape for it transparently (ADR 0011), so no special-casing is needed here.
    for effect in EffectName:
        SpriteBuffIcon(build_placeholder_atlas(), effect).render(_surface(), pygame.Vector2(0, 0), 64)


def test_sprite_buff_icon_render_does_not_raise_for_every_non_effect_source() -> None:
    for source in NonEffectIcon:
        SpriteBuffIcon(build_placeholder_atlas(), source).render(_surface(), pygame.Vector2(0, 0), 64)


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
