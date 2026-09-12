# 0016 — Biome-aware background rendering and prop placement

**Status:** Accepted
**Date:** 2026-09-12

## Context

ADR 0014 keyed and stored three Biomes' worth of background and foreground "prop" art
(`SpriteKey.BIOME_TURF` / `_DEAD_FOREST` / `_FOREST`) but explicitly deferred both consumers: the
random prop-placement renderer PROJECT_BRIEF.md §9.3 describes, and `SpriteAtlas.get_props()`,
the reading contract reserved to serve it. Neither exists yet. `ExplorationScene._draw_background`
(`eye/gui/scenes/exploration.py`) still draws the old placeholder `SpriteKey.BACKGROUND` key,
scaled with a non-uniform `pygame.transform.scale(..., surface.get_size())`. `CombatScene.draw()`
(`eye/gui/scenes/combat.py`) has no background at all — it fills black.

Three things the delivered art didn't match what ADR 0014 assumed:

- **Biome backgrounds don't share an aspect ratio.** `biome_turf/sprite.png` is 1024×768 (4:3,
  matching the 640×480 window per `eye/gui/app.py`'s `_WINDOW_SIZE`); `biome_dead_forest` and
  `biome_forest` are both 1456×816 (16:9). Today's non-uniform stretch is fine for the 4:3 one and
  visibly distorts the 16:9 ones, including the "walkable path across the lower section"
  PROJECT_BRIEF.md §9.3 describes.
- **Delivered prop art is sized like a background, not like foreground dressing** — every
  `prop_*.png` under a Biome directory is 1024×768 up to 1456×816, the same order of magnitude
  as the background itself. This is resized down at asset-landing time as part of implementing
  the renderer (see Decision), the same asset-landing-time-conversion move ADR 0014 already used
  converting the turf Biome's `.jpg` delivery to `.png`.
- **Neither `ExplorationRun` nor `Generation` exposes a screen-count-style accessor.** Both only
  expose turf-relative distances (`distance_to_nearest_seed`, `distance_to_nearest_matured_turf`).
  PROJECT_BRIEF.md §9.3 already treats Biome selection as "purely a GUI-side function of screen
  count... no new domain state is needed," and §9.4 wants a "distance from home" display value
  that is exactly this same count — it just isn't a public property today.

The domain's own `Biome` enum (`eye/exploration/encounters.py`) remains a single `BRAMBEROSITY`
placeholder, with selection "not wired in yet" per its own comment in `eye/exploration/run.py`.
`EnemyEncountered.biome` has exactly one other reader in the repo — `eye/tui/render.py`, the TUI
adapter's own label — which this work leaves untouched.

## Decision

- **A `distance_from_home` property** is added to `ExplorationRun` (backed by retaining
  `starting_screen` alongside the existing `_current_screen` in `__init__`, computed as their
  difference) and threaded through `Generation`. This is no new domain state — just exposing an
  existing private value — and doubles as the backing value for the not-yet-built §9.4 "distance
  from home" HUD display, though building that display is out of scope here.
- **Biome resolution is a pure GUI-side function of `distance_from_home`**, mapping it to
  `SpriteKey.BIOME_TURF` / `_DEAD_FOREST` / `_FOREST` via two boundary thresholds kept as named
  constants in `eye/gui/tuning.py` (playtesting-driven placeholders, per this project's existing
  convention) — never touching the domain's `Biome` enum or `EnemyEncountered.biome`, both of
  which stay exactly as they are.
- **Background rendering uses crop-to-cover**: scale uniformly to fill the window, cropping
  overflow, rather than today's non-uniform stretch or a letterboxed contain-fit. Chosen because a
  stretch distorts the 16:9 Biomes and a letterbox wastes screen space while complicating keeping
  the lower-section walkable path in a consistent on-screen position. This is a standing
  constraint on future biome art: author assuming the frame may be cropped at the edges, not that
  the full image is always visible.
- **`CombatScene` gains a background for the first time**, driven by the same resolver,
  `distance_from_home`, and crop-to-cover helper — not by `EnemyEncountered.biome`, which stays
  exactly as unreliable as before. Swapping in a dedicated combat background later is a
  `SpriteKey`-level change only, per ADR 0011's existing swappable-art precedent.
- **`SpriteAtlas.get_props()`** is implemented as ADR 0014 originally specified: it returns a
  key's full raw prop-file mapping directly, with no enum resolution and no all-or-nothing
  requirement, since a prop pool has no fixed membership to be missing from. The delivered
  `prop_*.png` files are resized down to a usable scattered-dressing scale as part of this same
  PR, at asset-landing time — not something `build_art_atlas` special-cases at load time.
- **A prop-placement renderer** samples `get_props()` at random positions per screen, weighted by
  distance within the current Biome (thinning as screen count rises within it) and blended with
  the next Biome's pool near a boundary, per PROJECT_BRIEF.md §9.3's overlap description.

## Consequences

- The turf Biome's already-known no-alpha/opaque prop art (flagged by ADR 0014) will render as
  flat rectangles once placed as foreground dressing — a carried-forward content gap, not a
  regression this work introduces.
- Two independent "Biome" concepts now deliberately coexist: the domain's placeholder enum
  (unchanged, still `BRAMBEROSITY`-only) and the GUI's real screen-count-driven resolution. A
  future domain-side Biome epic, if one is ever scoped, can replace the former without touching
  this work's resolver contract.
- Combatant/encounter/player sprite scale factors (`_COMBATANT_SCALE_FACTOR`,
  `ENCOUNTER_ENEMY_SCALE_FACTOR`, `ENCOUNTER_PICKUP_SCALE_FACTOR`, `_PLAYER_SCALE_FACTOR`) are very
  likely wrong once real backgrounds replace the placeholder — retuning them is tracked as its own
  sub-issue, verified visually per `GOTCHAS.md`'s placeholder-atlas-hides-geometry-bugs entry, not
  specified by this ADR.
- This ADR does not implement §9.4's actual distance-from-home/distance-from-turf display —
  only the accessor a future display reads from.
