"""Compound widget seam for buff/debuff and skill-tree-node display (ADR 0009). Both `BuffIcon`
and `SkillTreeLeaf` are `Protocol`s so an art epic can swap in a richer implementation (icon +
text + state styling) at each scene's factory call site without touching scene code.
`SpriteIcon` (ADR 0011) draws an atlas key's art; `SpriteBuffIcon` is its subject-keyed form and
`CombatScene`'s default, and `borderless_icon` the form a label on bare background takes.
`StaticSpriteIcon` (ADR 0015) wraps one already-resolved `Surface` for a caller that re-selects
its variant on every render, e.g. the skill-tree inspector card. `TextBuffIcon` remains as a
plain-text fallback/test double. `SpriteSkillTreeLeaf` (ADR 0015) renders a node's icon (keyed by
`SkillIconVariant`) plus name and effect summary, and is `SkillTreeScene`'s default;
`TextSkillTreeLeaf` remains as a plain-text fallback/test double.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum, auto
from typing import TYPE_CHECKING, ClassVar, Protocol, assert_never

import pygame

from eye.combat.effects import EFFECT_POLARITY, EffectName, EffectPolarity
from eye.gui.assets import IconVariant, SkillIconVariant, SpriteAtlas, SpriteKey
from eye.gui.fonts.fonts import GameFont, get_font
from eye.skilltree.tree import SkillNode

if TYPE_CHECKING:
    import pygame.typing

_FONT_SIZE = 16
_BUFF_COLOR: pygame.typing.ColorLike = "mediumseagreen"
_DEBUFF_COLOR: pygame.typing.ColorLike = "indianred"
_LOCKED_COLOR: pygame.typing.ColorLike = "dimgray"
_AVAILABLE_COLOR: pygame.typing.ColorLike = "gold"
_PURCHASED_COLOR: pygame.typing.ColorLike = "limegreen"


class BuffIcon(Protocol):
    def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None: ...


class NonEffectIcon(Enum):
    """An icon subject with no `EffectName` behind it to name it by."""

    RECOIL = auto()


# Everything a scene's icon factory can be asked to resolve, effect or not.
type IconSource = EffectName | NonEffectIcon


class SkillNodeState(Enum):
    LOCKED = auto()  # prerequisite tier missing, or too few spores
    AVAILABLE = auto()  # not yet purchased, but purchasable now
    PURCHASED = auto()


class SkillTreeLeaf(Protocol):
    def render(self, surface: pygame.Surface, rect: pygame.Rect, node: SkillNode, state: SkillNodeState) -> None: ...


def effect_label(effect: EffectName) -> str:
    return effect.name.replace("_", " ").title()


# PROJECT_BRIEF.md §9.7: a short, functional description of what each effect does, distinct from
# its flavor name (`effect_label`).
EFFECT_DESCRIPTIONS: Mapping[EffectName, str] = {
    EffectName.TOXICITY: "Lowers HP after every turn",
    EffectName.NOURISHED: "Heals a little each turn",
    EffectName.CLOUDED_JUDGEMENT: "Confuses the next action",
    EffectName.LIGNEOUS_PERIDERM: "Raises defense",
    EffectName.SPLINTERED: "Lowers defense",
    EffectName.SPIKY_SKIN: "Reflects some damage back at the attacker",
    EffectName.ADRENALINE: "Revives once on death with Fibrous effect",
    EffectName.FIBROUS: "Raises attack",
    EffectName.RUNT: "Lowers attack",
    EffectName.UPROOTED: "May grant an extra action",
    EffectName.WILTY: "May cause sudden death",
    EffectName.VEGETATIVE: "May skip the turn",
    EffectName.RESONANCE: "Primes the next battle's meter",
}


class TextBuffIcon:
    """Plain-text `BuffIcon` for an effect, coloured by its polarity. Effect-only on purpose: a
    non-effect subject has no polarity to colour by."""

    def __init__(self, effect: EffectName) -> None:
        self.effect = effect

    def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
        color = _BUFF_COLOR if EFFECT_POLARITY[self.effect] is EffectPolarity.BUFF else _DEBUFF_COLOR
        surface.blit(get_font(GameFont.ITHACA, _FONT_SIZE).render(effect_label(self.effect), True, color), pos)


def _sprite_key_for(source: IconSource) -> SpriteKey:
    match source:
        case EffectName.TOXICITY:
            return SpriteKey.EFFECT_TOXICITY
        case EffectName.NOURISHED:
            return SpriteKey.EFFECT_NOURISHED
        case EffectName.CLOUDED_JUDGEMENT:
            return SpriteKey.EFFECT_CLOUDED_JUDGEMENT
        case EffectName.LIGNEOUS_PERIDERM:
            return SpriteKey.EFFECT_LIGNEOUS_PERIDERM
        case EffectName.SPLINTERED:
            return SpriteKey.EFFECT_SPLINTERED
        case EffectName.SPIKY_SKIN:
            return SpriteKey.EFFECT_SPIKY_SKIN
        case EffectName.ADRENALINE:
            return SpriteKey.EFFECT_ADRENALINE
        case EffectName.FIBROUS:
            return SpriteKey.EFFECT_FIBROUS
        case EffectName.RUNT:
            return SpriteKey.EFFECT_RUNT
        case EffectName.UPROOTED:
            return SpriteKey.EFFECT_UPROOTED
        case EffectName.WILTY:
            return SpriteKey.EFFECT_WILTY
        case EffectName.VEGETATIVE:
            return SpriteKey.EFFECT_VEGETATIVE
        case EffectName.RESONANCE:
            return SpriteKey.EFFECT_RESONANCE
        case NonEffectIcon.RECOIL:
            return SpriteKey.ICON_RECOIL
        case _:
            assert_never(source)


class SpriteIcon:
    """`BuffIcon` backed by real art (ADR 0011), named by the atlas key it draws. `variant` picks
    one of the key's named static variants; `None` takes the reserved `sprite.png`."""

    def __init__(self, atlas: SpriteAtlas, sprite_key: SpriteKey, variant: IconVariant | None = None) -> None:
        self.sprite_key = sprite_key
        self._surface = (
            atlas.get(sprite_key) if variant is None else atlas.get_variant_set(sprite_key, IconVariant)[variant]
        )
        # The shipped art is 210x210 while callers render into boxes a few tens of pixels across,
        # so an unscaled blit would cover a large part of the screen.
        self._scaled: dict[int, pygame.Surface] = {}

    def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
        scaled = self._scaled.get(size)
        if scaled is None:
            scaled = pygame.transform.smoothscale(self._surface, (size, size))
            self._scaled[size] = scaled
        surface.blit(scaled, pos)


class StaticSpriteIcon:
    """A `BuffIcon` wrapping one already-resolved `Surface` -- for a caller (like the skill-tree
    inspector) that re-selects its variant every render rather than fixing it at construction, the
    way `SpriteIcon` does."""

    def __init__(self, surface: pygame.Surface) -> None:
        self._surface = surface

    def render(self, surface: pygame.Surface, pos: pygame.Vector2, size: int) -> None:
        scaled = pygame.transform.smoothscale(self._surface, (size, size))
        surface.blit(scaled, pos)


def borderless_icon(atlas: SpriteAtlas, sprite_key: SpriteKey) -> SpriteIcon:
    """`sprite_key`'s icon as a label on bare background: the borderless variant where the atlas
    carries one, the bordered `sprite.png` where it carries none (ADR 0011's per-key contract)."""
    return SpriteIcon(atlas, sprite_key, IconVariant.BORDERLESS if atlas.has_variant_set(sprite_key) else None)


class SpriteBuffIcon(SpriteIcon):
    """A `SpriteIcon` named by its subject -- `CombatScene`'s default `buff_icon_factory`."""

    def __init__(self, atlas: SpriteAtlas, source: IconSource) -> None:
        super().__init__(atlas, _sprite_key_for(source))


_STATE_COLORS: dict[SkillNodeState, pygame.typing.ColorLike] = {
    SkillNodeState.LOCKED: _LOCKED_COLOR,
    SkillNodeState.AVAILABLE: _AVAILABLE_COLOR,
    SkillNodeState.PURCHASED: _PURCHASED_COLOR,
}


class TextSkillTreeLeaf:
    def __init__(self, atlas: SpriteAtlas | None = None) -> None:
        pass  # no art dependency -- accepts an atlas only to match SkillTreeLeaf-factory's signature

    def render(self, surface: pygame.Surface, rect: pygame.Rect, node: SkillNode, state: SkillNodeState) -> None:
        surface.blit(
            get_font(GameFont.ITHACA, _FONT_SIZE).render(f"{node.name} ({node.cost})", True, _STATE_COLORS[state]),
            rect.topleft,
        )


def _skill_effect_summary(node: SkillNode) -> str:
    """A short, single-line description of what `node` grants -- the grid leaf's caption line."""
    parts: list[str] = []
    delta = node.stats_delta
    if delta.max_hp:
        parts.append(f"Max HP {delta.max_hp:+d}")
    if delta.attack:
        parts.append(f"Attack {delta.attack:+d}")
    if delta.defense:
        parts.append(f"Defense {delta.defense:+d}")
    if delta.recoil:
        parts.append(f"Recoil {delta.recoil:+.1f}")
    if delta.meter_fill_rate:
        parts.append(f"Meter fill {delta.meter_fill_rate:+d}")
    for effect in node.lifespan_effects:
        parts.append(effect_label(effect))
    for action in node.unlocked_actions:
        parts.append(f"Unlocks {action.name}")
    modifier = node.exploration_modifier
    if modifier.seed_growth_rate_multiplier != 1.0:
        parts.append(f"Seed growth x{modifier.seed_growth_rate_multiplier:.2f}")
    if modifier.proximity_discount_bonus:
        parts.append(f"Proximity discount +{modifier.proximity_discount_bonus:.1f}")
    return ", ".join(parts)


def _skill_sprite_key(node: SkillNode) -> SpriteKey:
    return SpriteKey(f"skill_{node.id.branch.name.lower()}_{node.id.sub_branch.name.lower()}_{node.id.tier}")


def _truncate_to_width(text: str, font: pygame.font.Font, max_width: int) -> str:
    """`text`, shortened with a trailing ellipsis if needed so it renders no wider than
    `max_width` in `font` -- a grid leaf's cell is a quick-glance summary, not the full detail
    the inspector Card (ADR 0015) shows on selection, so losing a long line's tail is acceptable."""
    if font.size(text)[0] <= max_width:
        return text
    ellipsis = "..."
    while text and font.size(text + ellipsis)[0] > max_width:
        text = text[:-1]
    return text + ellipsis if text else ellipsis


class SpriteSkillTreeLeaf:
    """`SkillTreeLeaf` backed by real art (ADR 0015): a node's icon (keyed by `SkillIconVariant`
    off `state`), its name, and a short effect-summary line -- `SkillTreeScene`'s default in place
    of `TextSkillTreeLeaf`."""

    _STATE_VARIANTS: ClassVar[dict[SkillNodeState, SkillIconVariant]] = {
        SkillNodeState.LOCKED: SkillIconVariant.LOCKED,
        SkillNodeState.AVAILABLE: SkillIconVariant.NORMAL,
        SkillNodeState.PURCHASED: SkillIconVariant.ACQUIRED,
    }

    def __init__(self, atlas: SpriteAtlas) -> None:
        self._atlas = atlas
        self._variants: dict[SpriteKey, Mapping[SkillIconVariant, pygame.Surface]] = {}

    def _icon_surface(self, sprite_key: SpriteKey, state: SkillNodeState) -> pygame.Surface:
        if not self._atlas.has_variant_set(sprite_key):
            return self._atlas.get(sprite_key)  # placeholder atlas: no acquired/locked/normal split
        variants = self._variants.setdefault(sprite_key, self._atlas.get_variant_set(sprite_key, SkillIconVariant))
        return variants[self._STATE_VARIANTS[state]]

    def render(self, surface: pygame.Surface, rect: pygame.Rect, node: SkillNode, state: SkillNodeState) -> None:
        icon_size = rect.height
        icon = pygame.transform.smoothscale(
            self._icon_surface(_skill_sprite_key(node), state),
            (icon_size, icon_size),
        )
        surface.blit(icon, rect.topleft)
        font = get_font(GameFont.ITHACA, _FONT_SIZE)
        text_x = rect.left + icon_size + 4
        available_width = rect.width - icon_size - 4
        name = _truncate_to_width(node.name, font, available_width)
        surface.blit(font.render(name, True, _STATE_COLORS[state]), (text_x, rect.top))
        summary = _skill_effect_summary(node)
        if summary:
            summary = _truncate_to_width(summary, font, available_width)
            surface.blit(font.render(summary, True, _STATE_COLORS[state]), (text_x, rect.top + _FONT_SIZE))
