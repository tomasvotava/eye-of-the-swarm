# 0001 — Combat domain architecture

**Status:** Accepted
**Date:** 2026-08-30

## Context

The combat system (PROJECT_BRIEF.md §5.4, §5.6, §5.7) needs turn resolution, an ATB-style
meter, twelve buff/debuff types with cross-cutting interactions (Adrenaline reviving through
Wilty, Clouded Judgement altering action selection, multi-hit "cluster" enemy attacks), and
a scoring-based enemy AI. None of it exists yet, and several not-yet-built systems
(exploration, Seed/Turf, skill tree) will eventually feed values into it. The design needed
to fix module boundaries and a handful of representation choices before implementation,
since getting them wrong would ripple through every buff/action/AI interaction.

## Decision

- **Combat lives in `eye/combat/` as pygame-free domain logic.** No rendering, no
  exploration/Seed-Turf/skill-tree wiring in this slice. External context (skill-tree-
  resolved stats, `distance_from_turf`) is accepted as plain constructor parameters —
  combat has no awareness of where they come from.
- **The `Battle` aggregate is event-sourced.** `Battle.take_round()` returns an ordered
  `list[BattleEvent]` (frozen dataclasses — `HitLanded`, `Death`, `EffectApplied`, etc.)
  rather than a single summarized result. This is required, not optional: multi-hit
  "cluster" enemy attacks and chained effects (Wilty → Adrenaline → extra turn) must be
  playable back one discrete event at a time by a future UI, not collapsed into one outcome.
- **Player and enemy action selection share one `ActionChooser` protocol.** The player side
  is a `ScriptedChooser` in this slice (a future pygame adapter implements the same protocol
  by blocking on input); the enemy side is `GreedyAI` (§5.7 scoring + geometric rank
  sampling). This is what lets Uprooted's "second action same turn" and Clouded Judgement's
  player-swap fall out of `Battle`'s round loop without side-specific branches.
- **`Stat` and `EffectName` are enums, never bare strings**, anywhere in the engine's public
  surface (effect registry keys, modifier lookups, event fields) — statically checkable.
- **Recoil (self-damage from moves like Struggle) is a per-combatant `Stat`, not a global
  constant** — enemies default to 0 (immune), the player has a nonzero base value that a
  future skill-tree upgrade would reduce by adjusting the base stat, same as any other stat.
- **An action's inflicted effects are targeted and multi-valued**
  (`InflictedEffect(effect, target=SELF|OPPONENT)`, `tuple[InflictedEffect, ...]`) — needed
  for moves that debuff/buff their own caster (e.g. Wilty+Adrenaline on the caster) rather
  than only ever hitting the opponent.
- **Multi-hit is a property of the action definition (`hit_count`), not the combatant.** A
  "cluster" enemy is simply given an action with `hit_count > 1`; nothing about `Combatant`
  encodes clustering. Death is checked after every individual hit — a lethal hit mid-sequence
  skips the remaining hits.
- **Toxicity/Nourished tick unconditionally per turn** (duration-gated only), not contingent
  on the holder having attacked that turn.
- **Uprooted's extra-action chance is parameterized by a per-turn counter**
  (`extra_action_index`) so a future decay curve is a single constant change, not a
  restructure. A separate hard `MAX_EXTRA_ACTIONS_PER_TURN` ceiling guards against runaway
  chaining from a misconfigured chance — defensive only, not intended to bind in practice.

## Consequences

- A future pygame combat-screen adapter consumes `list[BattleEvent]` and owns all
  pacing/animation; `Battle` itself has no notion of time passing between events.
- Skill tree and exploration integration are additive later: skill tree resolves final
  `Stats` before a `Combatant` is constructed; exploration supplies `distance_from_turf` and
  grants Lifespan-category effects into the same `EffectRegistry` combat already reads.
- The full design rationale (module map, exact round-resolution ordering, testing strategy)
  lived in a working spec during design that was not committed to this repository. This ADR
  is the durable record; per-component GitHub issues carry the implementation-level detail
  forward.
