# 0002 — Exploration domain architecture

**Status:** Accepted
**Date:** 2026-08-30

## Context

Combat (`eye/combat/`, ADR 0001) is complete and pygame-free. Its ADR named three not-yet-built
systems that would eventually feed values into it: exploration, Seed/Turf, and skill tree.
Exploration goes first: PROJECT_BRIEF.md §6 defines "distance from nearest Seed" as a screen
count, so Seed/Turf's growth math (§5.2) and combat's proximity scaling (§5.1) both depend on the
screen-walking skeleton existing first. `eye/main.py` is currently just a stub pygame loop with
no screens and no game state. This ADR also covers a small combat-side addition — a Swarm
Resonance pre-fill effect — needed to make the "start next combat with the meter already filling"
pickup mechanically real, not just narrative flavor.

## Decision

- **`Character` (new, `eye/character.py`) is the per-generation persistent state, owned by
  neither `eye.combat` nor `eye.exploration`.** It holds `current_hp`, `max_hp`, and
  `effects: EffectRegistry` — state that outlives any single `Battle` or exploration screen but
  resets on death. Both domains read/write it; it lives at the top level so neither has to import
  the other's aggregate root to reach shared state.
- **`ExplorationRun` (new, `eye/exploration/`) mutates the `Character` reference it's given
  directly and returns `list[ExplorationEvent]` per call** — the same mutate-and-log style
  `Battle.take_round()` already uses on its `Combatant`s (ADR 0001), applied at the correct
  altitude. It never constructs a `Combatant` and never imports `Stats`/`ActionDefinition` — an
  `ENEMY` encounter surfaces only a `Strain` identifier; resolving `Strain → Stats/actions` and
  building `Combatant`s is a composition-root concern, out of scope here.
- **`ExplorationRun` does not take a mutable reference for matured turf or spores.** Those cross
  generation boundaries in ways `Character` deliberately does not (turf survives death by design;
  spores persist indefinitely for skill-tree spend). `ExplorationRun` tracks its own
  `pending_seeds` and `spores_gained` internally and exposes them as read-only queries; a future
  composition root reads them once, at death, and folds them into whatever persists across
  generations. `ExplorationRun` itself never needs to know death happened — death handling,
  maturation, rebirth, and spore spending are a separate, later epic.
- **Two independent distance metrics, not one.** `distance_to_nearest_matured_turf` (combat
  proximity, §5.1) is a **raw** screen count — `current_screen - max(matured_turf_positions)`,
  minus an accumulated discount from "fellow carcass" resource pickups, floored at 0. No falloff
  shaping happens on the exploration side; `eye.combat.tuning.distance_falloff_scale` already
  owns that on the consuming side, so the two domains share a number, not a formula.
  `distance_to_nearest_seed` (growth rate, §5.2) needs its own formula — growth is slow near a
  seed and speeds up with distance, the opposite shape from proximity falloff — so it's a small
  exploration-local function, not shared with combat.
  Both use `math.inf` as the "nothing exists yet" sentinel (e.g. the very first generation, before
  anything is planted or matured): correct at both ends for free, because the two formulas have
  opposite monotonicity (one floors at zero as distance grows, the other caps at a maximum).
- **`matured_turf_positions` and `pending_seeds` store screen positions, not counts.** Distance is
  always "how many screens since this was planted," never "how many seeds exist." Since movement
  is strictly forward, the furthest-along (`max`) matured position is always the nearest one.
- **New terminology, locked for the rest of the project:** **Biome** (a path zone/segment, §8's
  open "zones" question) and **Strain** (an enemy archetype/kind, replacing the generic
  "race"/"enemy kind" language) — both modeled as single-member enums in this slice, the same
  "shape now, values later" pattern as `ActionKind` or the AI difficulty tiers in
  `eye/combat/tuning.py`.
- **Swarm Resonance is a new `EffectName.RESONANCE` in `eye/combat/effects.py`** — a trigger-type
  effect (not a stat modifier, checked via `.has()`, same family as `ADRENALINE`/`TOXICITY`) — plus
  a new `Battle.start() -> list[BattleEvent]`, called once by the composition root right after
  constructing `Battle` and before the first `take_round()`. It prefills `current_meter` for any
  combatant holding a Lifespan-category `RESONANCE` instance, consumes it, and emits the
  *existing* `MeterFilled`/`EffectExpired` events — no new `BattleEvent` variant needed. It checks
  the Lifespan category only, not Adrenaline's Battle-preferred-over-Lifespan precedence: a
  Battle-category effect cannot survive to the *next* battle's `Battle.start()` call, since
  `clear_battle_effects()` already wipes Battle-category effects when the prior battle ends —
  mirroring Adrenaline's precedence here would be dead code.

## Consequences

- A future composition root owns: constructing `Character` at generation start (HP from
  skill-tree-resolved `Stats`, once skill tree exists), resolving `Strain → Combatant` for
  encounters, driving `Battle`, writing post-battle HP back onto `Character`, and — on death —
  folding `ExplorationRun.pending_seeds` into the next generation's matured-turf baseline and
  `ExplorationRun.spores_gained` into a persistent spore ledger. None of that exists yet.
- Skill tree remains fully unbuilt; `Character.max_hp` and combat `Stats` are constructed with
  placeholder/default values until it lands.
- Multi-Biome path segmentation (how many zones, how they affect Strain selection or difficulty)
  is deferred — v1 ships one fixed `Biome`, mirroring combat's single-`Strain` v1 guardrail.
- Full design rationale (module-by-module API surface, tuning-constant names, testing strategy)
  lived in a working spec during design that is not committed to this repository (working
  specs/plans stay local per this project's docs conventions). This ADR is the durable record;
  per-component GitHub issues carry the implementation-level detail forward.
