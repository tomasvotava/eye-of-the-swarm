# 0003 — Skill tree domain architecture

**Status:** Accepted
**Date:** 2026-08-30

## Context

PROJECT_BRIEF.md §5.3 defines the skill tree as the game's central self-vs-hive tension: two
branches ("I" and "Swarm"), each with Attack/Defense/Utility sub-branches, spent from Spores
earned during exploration. Both prior ADRs named skill tree as one of the not-yet-built systems
that feeds values into combat — `Character.max_hp` and combat `Stats` are explicitly placeholder
until it lands (ADR 0002). A design was needed before implementation because node representation
touches four existing surfaces at once — `Stats`, `EffectRegistry`, `ActionDefinition`, and
`ExplorationRun`'s constructor — and getting the touch points wrong would mean reworking Accepted,
tested combat/exploration code rather than composing with it.

## Decision

- **New package `eye/skilltree/`, pygame-free**, following the same "domain owns pure
  computation, composition root wires timing" split as `eye.combat`/`eye.exploration`. It reads
  types from `eye.combat.stats`/`actions`/`effects` (the same way `eye.exploration` already reads
  `EffectName`/`ActiveEffect`), but neither combat nor exploration imports anything from
  `eye.skilltree`.
- **`Branch {SELF, SWARM}` × `SubBranch {ATTACK, DEFENSE, UTILITY}`; a node's id is
  `(branch, sub_branch, tier: int)`.** Progression is a strict per-sub-branch chain — tier *N*
  requires tier *N-1* purchased in the same `(branch, sub_branch)`; no cross-branch or
  intra-branch forks. No respec: purchases are permanent, matching the generational-memory framing
  in §5.5 (the hive doesn't un-learn).
- **Stat growth is a permanent, additive `StatsDelta`, not an `EffectRegistry` grant.**
  `StatsDelta` mirrors `Stats`' full field set (`max_hp`, `attack`, `defense`, `recoil`,
  `meter_capacity`, `meter_fill_rate`) and is folded directly into `Stats` at Character-
  construction time. This is required, not stylistic: `EffectRegistry` allows at most one active
  instance per `(category, name)` — reusing a named effect like `LIGNEOUS_PERIDERM` across
  multiple tiers would refresh, not stack, which can't express a compounding tree. Bypassing
  `EffectRegistry` for stat growth needs no change to the Accepted combat domain.
- **`EffectRegistry` `LIFESPAN` grants are reserved for nodes that hand out an actual named buff
  mechanic** (e.g. `FIBROUS`, `LIGNEOUS_PERIDERM`, `SPIKY_SKIN`, `NOURISHED`) — reapplied at the
  start of *every* `ExplorationRun`, not baked once at Character construction, so the hook point
  stays correct even if a future design ever splits a generation into more than one excursion. A
  `SkillNode` carries a `tuple[EffectName, ...]`, not a single optional value — multiple named
  grants from one node are allowed, the same multi-valued shape `ActionDefinition.inflicts`
  already uses.
- **Unlocked attacks accumulate, they don't replace.** Multiple `ActionDefinition`s of the same
  `ActionKind` can coexist in `available_actions` once unlocked — `Battle`'s chooser/AI already
  loops over `available_actions` with no kind-uniqueness assumption, so no engine change is needed
  beyond adding a `name: str = ""` field to `ActionDefinition` so same-kind variants are
  distinguishable. A `SkillNode` carries `tuple[ActionDefinition, ...]` for the same
  multi-grant reason as effects.
- **Utility nodes are scoped to knobs the exploration engine already implements**: a
  `seed_growth_rate` multiplier (nodes combine multiplicatively, neutral element 1.0) and a
  permanent proximity-discount baseline (nodes combine additively, neutral element 0.0) — both
  plumbed into `ExplorationRun` as two new optional constructor parameters
  (`seed_growth_multiplier`, `base_proximity_discount`), the same "accept external context as
  plain params" pattern ADR 0001 established for `distance_from_turf`. Speculative brief knobs
  with no existing implementation (max planting distance, turf decay/expansion, §5.3) are
  explicitly out of scope for this epic.
- **`SkillTree` is a mutable, event-sourced aggregate**, matching `Battle.take_round()`/
  `ExplorationRun.advance()`: it holds the purchased-node set and a persistent spore balance.
  `purchase(id)` raises if the node's prerequisite isn't met, it's already owned, or spores are
  insufficient (the same "raise for invalid calls" convention as
  `ExplorationRun.plant_seed()`), otherwise deducts cost and returns `[NodePurchased(id)]`.
  `add_spores(amount)` lets a future composition root fold a generation's death payout in.
- **Four pure resolver functions bridge `SkillTree` state to the rest of the engine** —
  `resolved_stats(base, tree)`, `resolved_lifespan_effects(tree)`, `resolved_actions(tree, base)`,
  `resolved_exploration_modifiers(tree)` — called by a future composition root. `SkillTree` itself
  has no awareness of `Character`, `Combatant`, or `ExplorationRun`.
- **v1 node catalog is 3 tiers × 6 sub-branches (18 nodes)** — the brief's own stated minimum
  viable scope (§7). "I" nodes lean on direct `StatsDelta` grants, including compromised
  (trade-off) capstones; "Swarm" nodes lean on `EffectRegistry` grants early and uncompromised
  `StatsDelta` capstones. The mechanism itself — raw compounding numbers vs. situational named
  buffs — carries the brief's "cheap, obviously good" vs. "flat, high-ceiling" distinction, not a
  divergent cost curve; costs are uniform per tier across both branches. Exact costs and
  magnitudes are `skilltree/tuning.py` placeholders, not fixed by this ADR.

## Consequences

- A future composition root owns: constructing `Stats` via `resolved_stats()` at generation
  birth, building `Combatant.available_actions` via `resolved_actions()`, applying
  `resolved_lifespan_effects()` into `Character.effects` at the start of each `ExplorationRun`,
  passing `resolved_exploration_modifiers()` into `ExplorationRun`'s constructor, and calling
  `SkillTree.add_spores()` when a generation's death folds `ExplorationRun.spores_gained`
  forward. None of that composition root exists yet.
- Persistence/save-format for `SkillTree`'s purchased-node set and spore balance is explicitly a
  composition-root concern, not this domain's — `SkillTree` stays an in-memory mutable state
  machine, matching `Battle` and `ExplorationRun`.
- Awarding Spores "after every battle" (PROJECT_BRIEF.md §4) also stays a composition-root
  concern — nothing in this epic touches `Battle` or wires spore payout to combat outcomes.
- Full design rationale lived in a working spec during design that is not committed to this
  repository (per this project's docs conventions). This ADR is the durable record; per-component
  GitHub issues carry the implementation-level detail forward.
