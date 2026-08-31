# 0004 — Composition root architecture

**Status:** Accepted
**Date:** 2026-08-31

## Context

Combat (`eye/combat/`, ADR 0001), exploration (`eye/exploration/`, ADR 0002), and skill tree
(`eye/skilltree/`, ADR 0003) are all complete and pygame-free. Each ADR named the same gap in its
own "Consequences" section: resolving a `Strain` into a `Combatant`, constructing `Character` from
skill-tree-resolved `Stats`, driving `Battle`/`ExplorationRun` together, handling death, folding a
generation's `pending_seeds`/`spores_gained` forward, and awarding Spores after every battle
(PROJECT_BRIEF.md §4) are all explicitly deferred as "a future composition root's job" — and that
composition root doesn't exist yet. Two content catalogs it depends on don't exist either: nothing
maps `Strain → Stats/actions` for enemies, and nothing defines the player's own base `Stats`/
actions (e.g. the base Struggle action). This ADR fixes the module boundaries and open questions
for that composition root before implementation, following the same "decide first, then file
per-component issues" pattern the three prior ADRs used.

## Decision

- **Composition root scope for this epic is a headless, pygame-free orchestrator only.**
  Persistence (save/load of `SkillTree` state and `matured_turf_positions`) and any UI/rendering
  adapter are explicitly out of scope and deferred to their own future epics — the same
  "domain/orchestration first, adapters later" sequencing already used for combat, exploration,
  and skill tree individually. `Game`/`Generation` (below) hold their state in memory only and are
  exercised by tests the same way the three domains already are.
- **Two new top-level content-catalog modules, owned by neither domain** — `eye/player.py`
  (`BASE_PLAYER_STATS: Stats`, `BASE_PLAYER_ACTIONS: tuple[ActionDefinition, ...]`, including the
  base Struggle action) and `eye/bestiary.py` (`Strain → StrainProfile`, where `StrainProfile`
  bundles `Stats`, actions, and a per-Strain Spore award). Same placement rationale ADR 0002 used
  for `Character`: reusable content data that both the composition root and (later) a UI need to
  reach, so it lives at the top level rather than inside any one domain package. `StrainProfile` is
  keyed by `Strain` in a plain `dict`, mirroring how `Strain`/`Biome` were already built as
  "single-member enum now, more later" (ADR 0002) — v1 ships one entry, for `Strain.BRAMBLE`.
- **Magic numbers in these two catalogs are inline, playtesting-driven placeholders**, marked as
  such the same way every domain's `tuning.py` already is — a deliberate, small exception to "every
  magic number lives in a domain's `tuning.py`" (CLAUDE.md), since `eye/player.py`/`eye/bestiary.py`
  aren't domains and two files' worth of constants don't warrant a dedicated top-level tuning
  module.
- **Spores are awarded per Strain, not a single flat constant** — `StrainProfile` carries its own
  award amount. V1 has only one `Strain` to scale against, so this has no visible effect yet, but it
  avoids a rework the first time a second Strain ships.
- **New package `eye/session/`, the one package allowed to import from all three domains at
  once** (`generation.py`, `game.py`, `events.py`, `tuning.py`). This is the composition root
  CLAUDE.md already names as the place domain wiring belongs — not a fourth domain, and not
  pygame-free by accident but by the same "no rendering, no adapters yet" discipline the domains
  themselves followed during their own build-out.
- **Two aggregates, split by lifetime, matching the brief's own vocabulary (§4, §5.5):**
  - **`Generation`** owns one life: a `Character`, an `ExplorationRun`, and the screen-by-screen
    loop. Advancing it calls `ExplorationRun.advance()`; an `EnemyEncountered` result resolves the
    enemy `Combatant` via `eye.bestiary` and the player `Combatant` via `Character` plus
    skill-tree-resolved stats/actions, then drives `Battle` to completion, writes the winning
    side's HP back onto `Character`, and accumulates the Strain's Spore award. It stops advancing
    once `Character.current_hp <= 0` — the only path to 0 HP, since nothing on the exploration side
    deals damage (only heals). Exposes `pending_seeds`, `spores_gained`, and `died: bool` read-only,
    the same shape `ExplorationRun` already exposes its own accumulators.
  - **`Game`** owns everything that crosses generation boundaries: the `SkillTree` and
    `matured_turf_positions`. `Game.play_generation(...)` constructs a `Generation` — `Stats` via
    `resolved_stats`, actions via `resolved_actions`, Lifespan effects via
    `resolved_lifespan_effects` applied at birth, exploration modifiers via
    `resolved_exploration_modifiers`, spawn screen = `max(matured_turf_positions, default=0)` —
    runs it to death, then folds `pending_seeds` into `matured_turf_positions` and calls
    `SkillTree.add_spores(spores_gained)`. `Game` does not loop generations automatically; the
    caller invokes `play_generation()` again to continue, the same explicit-pacing pattern a future
    UI/test harness needs to drive anyway.
  - Both mutate their owned state directly and return `list[SessionEvent]` per call — the same
    convention `Battle`/`ExplorationRun`/`SkillTree` already established (CLAUDE.md) — wrapping the
    underlying domain events plus new session-level ones (e.g. `GenerationEnded`, `SeedsMatured`).
- **Choosers and `random.Random` are constructor parameters on `Game`/`Generation`**, the same
  dependency-injection pattern `Battle` already uses for `ActionChooser`. No pygame dependency
  anywhere in this package; a future interactive chooser is a separate adapter.
- **Enemy AI difficulty is a single fixed `T` tuning placeholder for v1** — one Strain, one Biome,
  no basis yet for per-Strain or per-Biome differentiation.
- **Explicitly not enforced here: skill-tree purchase timing.** PROJECT_BRIEF.md §4 frames spending
  Spores as happening "between runs," but `SkillTree.purchase()` stays callable at any time — that's
  a UI-policy concern, not something this composition root encodes, matching house-rules'
  don't-over-engineer guidance.

## Consequences

- A future persistence epic owns: serializing/deserializing `SkillTree`'s purchased-node set and
  spore balance, and `Game`'s `matured_turf_positions`, across process restarts. `Game` stays an
  in-memory state machine until then, matching `Battle`/`ExplorationRun`/`SkillTree`.
- A future UI/rendering epic owns: a real interactive `ActionChooser` adapter, presenting
  `Generation`/`Game` state, and enforcing any "purchase between runs only" policy at the interface
  level rather than in the domain/orchestration layer.
- Adding a second `Strain` or `Biome` later is a `eye/bestiary.py` dict entry plus (for `Biome`)
  wiring into `EncounterGenerator`, not a restructure — the per-Strain Spore award and the
  single-member-enum shape were chosen with this in mind.
- Full design rationale (scope, module layout, the `Game`/`Generation` split) lived in a working
  spec during design that was not committed to this repository. This ADR is the durable record;
  per-component GitHub issues carry the implementation-level detail forward.
