from pathlib import Path

import pygame

from eye.combat.effects import EffectName
from eye.gui.assets import IconVariant, SpriteAtlas, SpriteKey, build_art_atlas, build_placeholder_atlas
from eye.gui.widgets import (
    EFFECT_DESCRIPTIONS,
    NonEffectIcon,
    SkillNodeState,
    SpriteBuffIcon,
    SpriteIcon,
    SpriteSkillTreeLeaf,
    TextBuffIcon,
    TextSkillTreeLeaf,
    _skill_effect_summary,
    _skill_sprite_key,
    effect_label,
)
from eye.skilltree.catalog import CATALOG
from eye.skilltree.tree import Branch, SkillNode, SkillNodeId, StatsDelta, SubBranch

_SHIPPED_SPRITES_DIR = Path("eye/gui/sprites")


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


def test_sprite_icon_draws_the_shipped_art_scaled_down_to_the_requested_box() -> None:
    # The real art, not a fixture: build_placeholder_atlas() is 32x32 for every key and the
    # tmp_path helpers write 4x4, so only a 210x210 source can catch an unscaled blit.
    atlas = build_art_atlas(_SHIPPED_SPRITES_DIR)
    box = 32
    destination = pygame.Surface((box * 2, box * 2))
    destination.fill("black")

    SpriteIcon(atlas, SpriteKey.ICON_HEALTH).render(destination, pygame.Vector2(0, 0), box)

    outside = [
        (x, y) for x in range(destination.get_width()) for y in range(destination.get_height()) if x >= box or y >= box
    ]
    assert all(destination.get_at(pixel) == pygame.Color("black") for pixel in outside)
    assert any(destination.get_at((x, y)) != pygame.Color("black") for x in range(box) for y in range(box))


def test_sprite_icon_takes_the_named_variant_over_the_default_sprite() -> None:
    atlas = build_art_atlas(_SHIPPED_SPRITES_DIR)
    default = _surface()
    borderless = _surface()

    SpriteIcon(atlas, SpriteKey.ICON_HEALTH).render(default, pygame.Vector2(0, 0), 32)
    SpriteIcon(atlas, SpriteKey.ICON_HEALTH, IconVariant.BORDERLESS).render(borderless, pygame.Vector2(0, 0), 32)

    assert pygame.image.tobytes(default, "RGBA") != pygame.image.tobytes(borderless, "RGBA")


def test_sprite_buff_icon_is_a_sprite_icon_named_by_its_subject() -> None:
    icon = SpriteBuffIcon(build_placeholder_atlas(), EffectName.FIBROUS)

    assert isinstance(icon, SpriteIcon)
    assert icon.sprite_key is SpriteKey.EFFECT_FIBROUS


def test_sprite_skill_tree_leaf_effect_summary_describes_a_stats_delta() -> None:
    node = SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0),
        cost=1,
        stats_delta=StatsDelta(attack=2),
    )

    assert "Attack +2" in _skill_effect_summary(node)


def test_sprite_skill_tree_leaf_effect_summary_describes_a_lifespan_effect() -> None:
    node = SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.ATTACK, tier=1),
        cost=1,
        lifespan_effects=(EffectName.FIBROUS,),
    )

    assert effect_label(EffectName.FIBROUS) in _skill_effect_summary(node)


def test_skill_sprite_key_matches_the_shipped_sprite_key_naming() -> None:
    node = SkillNode(id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0), cost=1)

    assert _skill_sprite_key(node) is SpriteKey.SKILL_SELF_ATTACK_0


def test_sprite_skill_tree_leaf_render_does_not_raise_for_every_shipped_skill_key() -> None:
    atlas = build_art_atlas(_SHIPPED_SPRITES_DIR)
    leaf = SpriteSkillTreeLeaf(atlas)
    for node in CATALOG.values():
        for state in SkillNodeState:
            leaf.render(_surface(), pygame.Rect(0, 0, 190, 40), node, state)


def test_sprite_skill_tree_leaf_falls_back_to_plain_get_for_a_placeholder_atlas() -> None:
    atlas = build_placeholder_atlas()
    leaf = SpriteSkillTreeLeaf(atlas)
    node = next(iter(CATALOG.values()))

    leaf.render(_surface(), pygame.Rect(0, 0, 190, 40), node, SkillNodeState.AVAILABLE)  # must not raise
