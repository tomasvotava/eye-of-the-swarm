"""Entity/background sprites for the GUI driver. `build_placeholder_atlas()` draws a solid-color
primitive per key — a placeholder per ADR 0009, grep-discoverable as exactly what a future art
epic replaces with `build_art_atlas(assets_dir)`, swapped in at its one call site without touching
scene code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import pygame

from eye.gui.animation import AnimationClip
from eye.gui.spritesheet import load_spritesheet_clip
from eye.gui.tuning import PROP_BACKGROUND_KEY_DISTANCE

if TYPE_CHECKING:
    import pygame.typing

PLACEHOLDER_SPRITE_SIZE = 32
_STATIC_SPRITE_FILENAME = "sprite.png"


class SpriteKey(StrEnum):
    PLAYER = "player"
    BRAMBLE = "bramble"
    SEED = "seed"
    TURF = "turf"
    BACKGROUND = "background"
    # A screen's not-yet-triggered EffectGranted/ResourceGranted encounter, visible at the
    # marker while walking toward it (ADR 0012) -- distinct from SEED, which is the HUD's
    # "seed ready to plant" status icon, not a screen encounter.
    EFFECT_PICKUP = "effect_pickup"
    RESOURCE_PICKUP = "resource_pickup"
    # Fallback for a lookup that couldn't resolve a more specific key (e.g. a Strain with no
    # same-named sprite) -- the conventional "missing texture" placeholder, not tied to any one
    # entity, so callers have somewhere to fall back to instead of crashing.
    UNKNOWN = "unknown"
    BEATLE = "beatle"
    FLEA = "flea"
    GOLEM = "golem"
    PHIDIZVIK = "phidizvik"
    TUMBLEWEED = "tumbleweed"
    # One member per EffectName (widgets.py's SpriteBuffIcon maps between them)
    EFFECT_TOXICITY = "effect_toxicity"
    EFFECT_NOURISHED = "effect_nourished"
    EFFECT_CLOUDED_JUDGEMENT = "effect_clouded_judgement"
    EFFECT_LIGNEOUS_PERIDERM = "effect_ligneous_periderm"
    EFFECT_SPLINTERED = "effect_splintered"
    EFFECT_SPIKY_SKIN = "effect_spiky_skin"
    EFFECT_ADRENALINE = "effect_adrenaline"
    EFFECT_FIBROUS = "effect_fibrous"
    EFFECT_RUNT = "effect_runt"
    EFFECT_UPROOTED = "effect_uprooted"
    EFFECT_WILTY = "effect_wilty"
    EFFECT_VEGETATIVE = "effect_vegetative"
    EFFECT_RESONANCE = "effect_resonance"
    # Icons with no entity or EffectName behind them: resource pickup grants, and recoil
    ICON_HEALTH = "icon_health"
    ICON_SPORES = "icon_spores"
    ICON_SEED_GROWTH = "icon_seed_growth"
    ICON_DISTANCE_DISCOUNT = "icon_distance_discount"
    ICON_RECOIL = "icon_recoil"
    # One member per SkillNodeId (eye/skilltree/catalog.py) -- keyed by (branch, sub_branch, tier),
    # not by skill name, so a narrative rename of a skill (PROJECT_BRIEF.md §0) never touches this
    # key. Each carries acquired/locked/normal named variants, not sprite.png (ADR 0014).
    SKILL_SELF_ATTACK_0 = "skill_self_attack_0"
    SKILL_SELF_ATTACK_1 = "skill_self_attack_1"
    SKILL_SELF_ATTACK_2 = "skill_self_attack_2"
    SKILL_SELF_DEFENSE_0 = "skill_self_defense_0"
    SKILL_SELF_DEFENSE_1 = "skill_self_defense_1"
    SKILL_SELF_DEFENSE_2 = "skill_self_defense_2"
    SKILL_SELF_UTILITY_0 = "skill_self_utility_0"
    SKILL_SELF_UTILITY_1 = "skill_self_utility_1"
    SKILL_SELF_UTILITY_2 = "skill_self_utility_2"
    SKILL_SWARM_ATTACK_0 = "skill_swarm_attack_0"
    SKILL_SWARM_ATTACK_1 = "skill_swarm_attack_1"
    SKILL_SWARM_ATTACK_2 = "skill_swarm_attack_2"
    SKILL_SWARM_DEFENSE_0 = "skill_swarm_defense_0"
    SKILL_SWARM_DEFENSE_1 = "skill_swarm_defense_1"
    SKILL_SWARM_DEFENSE_2 = "skill_swarm_defense_2"
    SKILL_SWARM_UTILITY_0 = "skill_swarm_utility_0"
    SKILL_SWARM_UTILITY_1 = "skill_swarm_utility_1"
    SKILL_SWARM_UTILITY_2 = "skill_swarm_utility_2"
    # One member per Biome (PROJECT_BRIEF.md §9.3): sprite.png is the background+path, and a pool
    # of unenumerated prop_*.png files sampled randomly for foreground dressing (ADR 0014) -- not
    # a fixed named variant set, so no consumer enum resolves these today.
    BIOME_TURF = "biome_turf"
    BIOME_DEAD_FOREST = "biome_dead_forest"
    BIOME_FOREST = "biome_forest"


class IconVariant(StrEnum):
    """Named static variants of an icon, for `get_variant_set`. Borderless only: `sprite.png` is
    itself the bordered form, so a `BORDERED` member would make `get_variant_set` raise."""

    BORDERLESS = "borderless"


class SkillIconVariant(StrEnum):
    """Named static variants of a skill-tree node's icon (ADR 0015), resolved the same way
    `IconVariant` is: via `get_variant_set`. All three exist as their own files for every
    `SKILL_*` key today, so the all-or-nothing contract is satisfiable as delivered."""

    ACQUIRED = "acquired"
    LOCKED = "locked"
    NORMAL = "normal"


class SpriteAtlas:
    def __init__(
        self,
        surfaces: Mapping[SpriteKey, pygame.Surface],
        clips: Mapping[SpriteKey, Mapping[str, AnimationClip]] | None = None,
        variants: Mapping[SpriteKey, Mapping[str, pygame.Surface]] | None = None,
    ) -> None:
        self._surfaces = surfaces
        self._clips = clips or {}
        self._variants = variants or {}

    def get(self, key: SpriteKey) -> pygame.Surface:
        return self._surfaces[key]

    def has_animation_set(self, key: SpriteKey) -> bool:
        """Whether `key` has any loaded animation clips at all.

        Distinguishes "no animation data for this key" (fine — a caller falls back to `get`)
        from "some clips exist but a required state is missing", which `get_animation_set`
        still raises on rather than this method silently absorbing.
        """
        return key in self._clips

    def get_animation_set[TState: StrEnum](
        self, key: SpriteKey, state_type: type[TState]
    ) -> Mapping[TState, AnimationClip]:
        """Resolve `state_type`'s members against `key`'s loaded animation clips.

        Raises `ValueError` if any member has no matching clip on disk.
        """
        raw = self._clips.get(key, {})
        return _resolve_named_set(key, raw, state_type, label="states")

    def has_variant_set(self, key: SpriteKey) -> bool:
        """Whether `key` has any loaded static named variants. `get_variant_set` is all-or-nothing
        and raises for a variant-less key, so a caller with a fallback asks here first."""
        return key in self._variants

    def get_variant_set[TVariant: StrEnum](
        self, key: SpriteKey, variant_type: type[TVariant]
    ) -> Mapping[TVariant, pygame.Surface]:
        """Resolve `variant_type`'s members against `key`'s loaded static named variants.

        Raises `ValueError` if any member has no matching file on disk.
        """
        raw = self._variants.get(key, {})
        return _resolve_named_set(key, raw, variant_type, label="variants")

    def get_props(self, key: SpriteKey) -> Mapping[str, pygame.Surface]:
        """Every non-`sprite.png` file loaded for `key` (ADR 0014/0016) -- raw filename stem ->
        `Surface`, with no enum resolution and no all-or-nothing requirement, since a prop pool
        has no fixed membership to be missing from."""
        return self._variants.get(key, {})


def _resolve_named_set[T, TEnum: StrEnum](
    key: SpriteKey, raw: Mapping[str, T], enum_type: type[TEnum], *, label: str
) -> Mapping[TEnum, T]:
    resolved: dict[TEnum, T] = {}
    missing: list[TEnum] = []
    for member in enum_type:
        if member.value in raw:
            resolved[member] = raw[member.value]
        else:
            missing.append(member)
    if missing:
        raise ValueError(f"{key!r}: missing sprite files for {label}: {missing}")
    return resolved


@dataclass(frozen=True, slots=True)
class _PlaceholderShape:
    color: pygame.typing.ColorLike
    is_circle: bool


_PLACEHOLDER_SHAPES: Mapping[SpriteKey, _PlaceholderShape] = {
    SpriteKey.PLAYER: _PlaceholderShape(color="dodgerblue", is_circle=True),
    SpriteKey.BRAMBLE: _PlaceholderShape(color="firebrick", is_circle=True),
    SpriteKey.SEED: _PlaceholderShape(color="gold", is_circle=True),
    SpriteKey.TURF: _PlaceholderShape(color="forestgreen", is_circle=False),
    SpriteKey.BACKGROUND: _PlaceholderShape(color="saddlebrown", is_circle=False),
    SpriteKey.EFFECT_PICKUP: _PlaceholderShape(color="mediumorchid", is_circle=True),
    SpriteKey.RESOURCE_PICKUP: _PlaceholderShape(color="goldenrod", is_circle=True),
    SpriteKey.UNKNOWN: _PlaceholderShape(color="magenta", is_circle=False),
    SpriteKey.BEATLE: _PlaceholderShape(color="darkolivegreen", is_circle=True),
    SpriteKey.FLEA: _PlaceholderShape(color="sienna", is_circle=True),
    SpriteKey.GOLEM: _PlaceholderShape(color="slategray", is_circle=True),
    SpriteKey.PHIDIZVIK: _PlaceholderShape(color="teal", is_circle=True),
    SpriteKey.TUMBLEWEED: _PlaceholderShape(color="peru", is_circle=True),
    SpriteKey.EFFECT_TOXICITY: _PlaceholderShape(color="darkorchid", is_circle=False),
    SpriteKey.EFFECT_NOURISHED: _PlaceholderShape(color="mediumseagreen", is_circle=False),
    SpriteKey.EFFECT_CLOUDED_JUDGEMENT: _PlaceholderShape(color="slateblue", is_circle=False),
    SpriteKey.EFFECT_LIGNEOUS_PERIDERM: _PlaceholderShape(color="darkgoldenrod", is_circle=False),
    SpriteKey.EFFECT_SPLINTERED: _PlaceholderShape(color="indianred", is_circle=False),
    SpriteKey.EFFECT_SPIKY_SKIN: _PlaceholderShape(color="crimson", is_circle=False),
    SpriteKey.EFFECT_ADRENALINE: _PlaceholderShape(color="orangered", is_circle=False),
    SpriteKey.EFFECT_FIBROUS: _PlaceholderShape(color="chartreuse", is_circle=False),
    SpriteKey.EFFECT_RUNT: _PlaceholderShape(color="rosybrown", is_circle=False),
    SpriteKey.EFFECT_UPROOTED: _PlaceholderShape(color="deepskyblue", is_circle=False),
    SpriteKey.EFFECT_WILTY: _PlaceholderShape(color="dimgray", is_circle=False),
    SpriteKey.EFFECT_VEGETATIVE: _PlaceholderShape(color="olivedrab", is_circle=False),
    SpriteKey.EFFECT_RESONANCE: _PlaceholderShape(color="gold", is_circle=False),
    SpriteKey.ICON_HEALTH: _PlaceholderShape(color="salmon", is_circle=False),
    SpriteKey.ICON_SPORES: _PlaceholderShape(color="plum", is_circle=False),
    SpriteKey.ICON_SEED_GROWTH: _PlaceholderShape(color="yellowgreen", is_circle=False),
    SpriteKey.ICON_DISTANCE_DISCOUNT: _PlaceholderShape(color="steelblue", is_circle=False),
    SpriteKey.ICON_RECOIL: _PlaceholderShape(color="tomato", is_circle=False),
    SpriteKey.SKILL_SELF_ATTACK_0: _PlaceholderShape(color="salmon", is_circle=False),
    SpriteKey.SKILL_SELF_ATTACK_1: _PlaceholderShape(color="coral", is_circle=False),
    SpriteKey.SKILL_SELF_ATTACK_2: _PlaceholderShape(color="chocolate", is_circle=False),
    SpriteKey.SKILL_SELF_DEFENSE_0: _PlaceholderShape(color="tan", is_circle=False),
    SpriteKey.SKILL_SELF_DEFENSE_1: _PlaceholderShape(color="wheat", is_circle=False),
    SpriteKey.SKILL_SELF_DEFENSE_2: _PlaceholderShape(color="khaki", is_circle=False),
    SpriteKey.SKILL_SELF_UTILITY_0: _PlaceholderShape(color="yellowgreen", is_circle=False),
    SpriteKey.SKILL_SELF_UTILITY_1: _PlaceholderShape(color="limegreen", is_circle=False),
    SpriteKey.SKILL_SELF_UTILITY_2: _PlaceholderShape(color="mediumspringgreen", is_circle=False),
    SpriteKey.SKILL_SWARM_ATTACK_0: _PlaceholderShape(color="cadetblue", is_circle=False),
    SpriteKey.SKILL_SWARM_ATTACK_1: _PlaceholderShape(color="steelblue", is_circle=False),
    SpriteKey.SKILL_SWARM_ATTACK_2: _PlaceholderShape(color="royalblue", is_circle=False),
    SpriteKey.SKILL_SWARM_DEFENSE_0: _PlaceholderShape(color="cornflowerblue", is_circle=False),
    SpriteKey.SKILL_SWARM_DEFENSE_1: _PlaceholderShape(color="mediumpurple", is_circle=False),
    SpriteKey.SKILL_SWARM_DEFENSE_2: _PlaceholderShape(color="darkslateblue", is_circle=False),
    SpriteKey.SKILL_SWARM_UTILITY_0: _PlaceholderShape(color="orchid", is_circle=False),
    SpriteKey.SKILL_SWARM_UTILITY_1: _PlaceholderShape(color="plum", is_circle=False),
    SpriteKey.SKILL_SWARM_UTILITY_2: _PlaceholderShape(color="violet", is_circle=False),
    SpriteKey.BIOME_TURF: _PlaceholderShape(color="darkslategray", is_circle=False),
    SpriteKey.BIOME_DEAD_FOREST: _PlaceholderShape(color="dimgray", is_circle=False),
    SpriteKey.BIOME_FOREST: _PlaceholderShape(color="seagreen", is_circle=False),
}


def _load_variant_surface(path: Path) -> pygame.Surface:
    """Loads a named static variant (prop art, skill/effect icon variants), keying out a flat
    background color for art with no real alpha channel of its own. Real per-pixel alpha art
    (bitsize 32) is returned untouched -- distance 0 would key nothing anyway, but skipping the
    `PixelArray` pass avoids the cost on every already-correct icon variant."""
    surface = pygame.image.load(path)
    if surface.get_bitsize() == 32:
        return surface.convert_alpha()
    keyed = surface.convert_alpha()
    corner = surface.get_at((0, 0))
    pixels = pygame.PixelArray(keyed)
    pixels.replace(corner, (0, 0, 0, 0), distance=PROP_BACKGROUND_KEY_DISTANCE)
    pixels.close()
    return keyed


def _build_placeholder_surface(key: SpriteKey) -> pygame.Surface:
    shape = _PLACEHOLDER_SHAPES[key]
    surface = pygame.Surface((PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE), pygame.SRCALPHA)
    if shape.is_circle:
        radius = PLACEHOLDER_SPRITE_SIZE // 2
        pygame.draw.circle(surface, shape.color, (radius, radius), radius)
    else:
        surface.fill(shape.color)
    return surface


def build_placeholder_atlas() -> SpriteAtlas:
    surfaces = {key: _build_placeholder_surface(key) for key in _PLACEHOLDER_SHAPES}
    return SpriteAtlas(surfaces)


def build_art_atlas(assets_dir: Path) -> SpriteAtlas:
    """Build a `SpriteAtlas` from `eye/gui/sprites`-shaped directories under `assets_dir`.

    Resolved per `SpriteKey`, not all-or-nothing (ADR 0011): a missing `assets_dir / key.value`
    directory, or one with no `sprite.png`, falls back to today's placeholder shape; a
    `sprite.png` inside it loads as the key's static surface; every other `<name>.png` with a
    `<name>.json` sibling loads as an animation clip, and every other `<name>.png` without one
    loads as a static named variant.
    """
    surfaces: dict[SpriteKey, pygame.Surface] = {}
    clips: dict[SpriteKey, dict[str, AnimationClip]] = {}
    variants: dict[SpriteKey, dict[str, pygame.Surface]] = {}

    for key in SpriteKey:
        key_dir = assets_dir / key.value
        surfaces[key] = _build_placeholder_surface(key)
        if not key_dir.is_dir():
            continue

        static_sprite_path = key_dir / _STATIC_SPRITE_FILENAME
        if static_sprite_path.is_file():
            if static_sprite_path.with_suffix(".json").is_file():
                raise ValueError(
                    f"{key!r}: {_STATIC_SPRITE_FILENAME} must not have a .json manifest sibling — "
                    "an animated clip needs a non-'sprite' filename"
                )
            surfaces[key] = pygame.image.load(static_sprite_path).convert_alpha()

        key_clips: dict[str, AnimationClip] = {}
        key_variants: dict[str, pygame.Surface] = {}
        for png_path in sorted(key_dir.glob("*.png")):
            if png_path.name == _STATIC_SPRITE_FILENAME:
                continue
            manifest_path = png_path.with_suffix(".json")
            if manifest_path.is_file():
                sheet_clip = load_spritesheet_clip(png_path, manifest_path)
                key_clips[png_path.stem] = AnimationClip(
                    frames=sheet_clip.frames, frame_duration_seconds=sheet_clip.frame_duration_seconds
                )
            else:
                key_variants[png_path.stem] = _load_variant_surface(png_path)
        if key_clips:
            clips[key] = key_clips
        if key_variants:
            variants[key] = key_variants

    return SpriteAtlas(surfaces, clips, variants)
