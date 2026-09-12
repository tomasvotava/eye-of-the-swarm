# 0014 — Skill icon keying and biome prop-pool assets

**Status:** Accepted
**Date:** 2026-09-12

## Context

Two art deliveries landed in the same batch: 18 skill-tree icons (§9.6) — each with `acquired`,
`locked`, and `normal` states — and three Biomes' worth of backgrounds and foreground dressing
(§9.3). Both need a home under `eye/gui/sprites/` per ADR 0011's rule, but neither fits an
existing case cleanly.

**Skill icons.** ADR 0011 already built the machinery a per-skill icon needs — `get_variant_set`
resolves a caller's `StrEnum` against a key's static named-variant files — but never named a key
per skill or picked what identifies one. `SkillNode.name` (`eye/skilltree/catalog.py`) is exactly
the kind of narratively-flexible placeholder PROJECT_BRIEF.md §0 warns about ("Nasty Tendrils"
could be renamed without changing the mechanic); a directory named after it would need renaming
alongside every narrative pass. `SkillNodeId`'s `(branch, sub_branch, tier)` is the actual
mechanical identity and never changes for that reason.

**Biome dressing.** §9.3 wants a background that stays fixed per Biome plus foreground "props"
rendered at random, with the mix of prop pools shifting near a Biome boundary. A background is a
plain no-variant case (`sprite.png`). Props are not: there's no fixed enum of "the states a prop
key can be in" the way `locked`/`acquired`/`normal` or `idle`/`walk` are — it's an open, growing
bag of interchangeable dressing pieces (`bare_dead_tree_1.png` through `_4`, four `mossy_log_*`
variations, and so on) that a renderer samples from, not resolves a specific named member of.
Forcing that into `get_variant_set`'s all-or-nothing enum-resolution contract would require a
`StrEnum` member per prop file, listing every prop art delivery ever makes as a name a caller must
carry and keep in sync — exactly the churn `get_variant_set` exists to avoid for skill icons, just
inverted.

The delivered turf art also arrived as `.jpg`, while the dead_forest/forest batches are `.png`.
`build_art_atlas` only globs `*.png` (ADR 0011) — an authoring-side detail, not something the
pipeline should special-case for one Biome.

## Decision

- **Skill icon keys are `SpriteKey.SKILL_{BRANCH}_{SUB_BRANCH}_{TIER}`** (e.g.
  `skill_self_attack_0`, `skill_swarm_utility_2`) — one directory per `SkillNodeId`, never per
  skill name. Each carries `acquired.png` / `locked.png` / `normal.png` and no `sprite.png`: a
  skill icon has no unvaried default, so `SpriteAtlas.get(key)` correctly falls back to the
  placeholder for these keys, and a future consumer resolves the three states through a new
  `SkillIconVariant(StrEnum)` (`ACQUIRED`, `LOCKED`, `NORMAL`) passed to `get_variant_set` — that
  enum isn't defined yet; nothing consumes it until §9.6's presentation work picks this up.
- **Biome keys are `SpriteKey.BIOME_{NAME}`** (`biome_turf`, `biome_dead_forest`, `biome_forest`).
  `sprite.png` is the background (with its lower-section path/road, per this Epic's brainstorm) —
  the ordinary no-variant case, unchanged from ADR 0011. Every other `<name>.png` in the directory
  (`prop_bare_dead_tree_1.png`, `prop_mossy_log_3.png`, …) already lands in `build_art_atlas`'s
  existing per-key raw dict — the same "no `.json` sibling → static named entry" branch that feeds
  `_variants` today — with **no pipeline code change required**. What's new is only the *reading*
  contract this ADR reserves: a future `SpriteAtlas.get_props(key) -> Mapping[str, Surface]`
  returns that raw dict directly, with no enum resolution and no all-or-nothing requirement,
  because a prop pool has no fixed membership to be missing from. `get_props` is not implemented by
  this ADR — nothing consumes it yet (§9.3's random-placement renderer is a future epic) — the same
  deliberate non-build ADR 0011 used for `get_variant_set` in its own Epic.
- **Source art that isn't already `.png` is converted at asset-landing time, not load time.** The
  turf Biome's `.jpg` delivery was converted to `.png` before being placed under
  `eye/gui/sprites/`; the pipeline's `*.png`-only glob (ADR 0011) is unchanged. The turf source had
  no alpha channel, so its converted `.png` files are fully opaque rectangles — a content gap to
  close in a future art pass, not something this ADR's conversion step fabricates a fix for.

```
eye/gui/sprites/
  skill_self_attack_0/
    acquired.png   locked.png   normal.png
  skill_swarm_utility_2/
    acquired.png   locked.png   normal.png
  biome_turf/
    sprite.png                      # background + path
    prop_bone.png  prop_carcass.png  prop_dead_tree.png  prop_eggs.png
    prop_heart.png  prop_knot.png  prop_moss_heap.png  prop_vines.png
  biome_dead_forest/
    sprite.png
    prop_bare_dead_tree_1.png ... _4.png
    prop_cluster_of_alien_pod_eggs_1.png ... _4.png
    prop_dead_husk_1.png ... _3.png
    prop_gnarly_vine_knot_1.png ... _3.png
  biome_forest/
    sprite.png
    prop_cluster_of_lily_pads_1.png ... _4.png
    prop_mossy_log_1.png ... _4.png
    prop_sunbaked_rock_1.png ... _4.png
    prop_swamp_reeds_1.png ... _4.png
```

- **Three Biomes are named and ordered** (settles PROJECT_BRIEF.md §8's open "how many Biomes"
  question): `turf` (home, nearest the hive) → `dead_forest` → `forest` (furthest out) — see
  PROJECT_BRIEF.md §9.3 for the narrative framing this ordering carries.

## Consequences

- Landing this Epic's actual presentation work — a skill-tree icon widget that resolves
  `SkillIconVariant` via `get_variant_set`, and an exploration/combat-background renderer that
  samples `get_props` with a distance-weighted mix across a Biome boundary — is unstarted; both
  need their own tracked issues when that work is scoped, per this project's Epic/sub-issue
  process. This ADR only settles where the art lives and how it's keyed.
- `get_props`'s "no fixed membership" shape means a future art delivery can add or remove prop
  files for a Biome without touching any enum or raising `ValueError` anywhere — unlike
  `get_variant_set`, which is deliberately strict for exactly the state-icon case this isn't.
- A `SkillIconVariant` enum, once added, is a second real consumer of `get_variant_set` alongside
  `IconVariant` — confirms ADR 0011's generic-over-`TVariant` design rather than motivating a new
  mechanism.
- The turf Biome's opaque (no-alpha) prop art will read as flat rectangles once anything renders
  it over a background — a known content gap, not a code defect, until touched up or replaced.
