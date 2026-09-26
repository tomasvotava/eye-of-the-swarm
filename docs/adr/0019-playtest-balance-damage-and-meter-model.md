# 0019 — Playtest balance: damage model, hit variance, and meter fill shape

**Status:** Accepted
**Date:** 2026-09-25

## Context

Playtesting after Epic #253 surfaced three problems that are properties of the combat model's
*shape*, not of its tuning constants:

- **Defense zeroes out hits.** Damage is `max(0, base_power + ATK − DEF)`. A player who invests
  in the Defense line reaches DEF 18 (22 with Ligneous Periderm): Tumbleweed, Beatle and Flea
  then deal 0, Golem deals 1, and Sap-Fed's Nourished (+3/turn) out-heals every strain. Some
  fights heal the player every turn; death becomes impossible.
- **Fights are fully calculable.** Every hit deals a fixed amount, so the turn count to win or
  lose is known before the first swing — against PROJECT_BRIEF.md §5.6's stated intent that
  "fights can't be fully calculated in advance from stats alone".
- **The Swarm Resonance meter almost never fills** (#292, and #93 before it). Fill is
  `meter_fill_rate × distance_falloff_scale(distance)`, the same linear ramp to zero that scales
  Swarm Attack damage. At rate 20 a full meter costs 5 turns next to turf and 10 at distance 5;
  most fights end first.

## Decision

### Damage

- **Ratio formula.** With `P = base_power + effective ATK`:
  `raw = P² / (P + effective DEF)`. It never reaches zero, defense has diminishing returns, and
  the attacker's own power still matters against a heavy defender. P and effective DEF are each
  clamped at 0 before the division (`raw` is 0 when P is 0), a defensive guard no shipped
  combatant reaches.
- **Per-hit order of operations:** `raw` → × distance scale (Swarm Attack only, unchanged) →
  × spread multiplier → × critical multiplier → round → `max(1, …)`. The floor of 1 covers the
  corner a Runt-reduced attacker can reach (`P = 3` against DEF 22 is 0.36 before rounding).
- **Spread:** `DAMAGE_SPREAD = 0.2` in `eye/combat/tuning.py`; each landed hit draws a
  multiplier from `rng.uniform(1 − s, 1 + s)` using `Battle`'s injected RNG. `Battle` takes
  `damage_spread` as a constructor parameter defaulting to that constant, and makes **no draw**
  when it is 0 — so tests switch variance off by construction, and existing seeded tests keep
  their RNG stream.
- **Critical hits:** `Stats` gains `crit_chance: float = 0.0` and `crit_multiplier: float = 1.0`.
  The defaults mean "cannot crit", mirroring `recoil`'s immune-by-default precedent (ADR 0001).
  `BASE_PLAYER_STATS` and every bestiary strain set them explicitly from `CRIT_CHANCE = 0.1` and
  `CRIT_MULTIPLIER = 1.5` in tuning — one shared value today, per-combatant data so a skill node
  or strain can differ later without a model change. The crit roll is made only when
  `crit_chance > 0`. `HitLanded` gains `is_critical: bool` so the GUI can call it out.
- **`resolve_hit` stays deterministic.** It takes `damage_multiplier: float = 1.0` (spread × crit
  combined) instead of drawing anything itself; `Battle` does the drawing. `GreedyAI` scores
  with the default 1.0, so the enemy ranks actions on unvaried, non-critical damage and never
  consumes the battle's RNG. Its "wins the fight" bonus (§5.7) is therefore judged on the
  average hit — a slightly conservative AI, accepted.
- **What varies and what doesn't.** Recoil and Spiky Skin reflection derive from the final
  hit damage, so they vary with it (a player crit also costs more recoil). Toxicity and
  Nourished ticks stay fixed — §5.6 wants volatility "in bounded and named ways", and those are
  named effects. Reflection rounds with `ceil`, so any reflected hit deals at least 1.

### Meter fill

- **Own falloff, separate from damage scaling.** New `meter_fill_scale(distance)` in
  `eye/combat/tuning.py`: 1.0 at distance 0, linear down to `METER_FILL_EDGE_SCALE ≈ 0.37` just
  inside `PROXIMITY_FALLOFF_RANGE`, then **0** at or beyond it (including `math.inf`, i.e. a
  generation with no matured turf). `distance_falloff_scale` is unchanged and keeps scaling Swarm
  Attack damage.
- **Rate:** the player's base `meter_fill_rate` rises 20 → 34, so a full meter takes ~3 turns next
  to turf and ~8 at the edge of the influence radius. Skill-tree `meter_fill_rate` deltas stay
  additive on top.
- The first generation (no matured turf) keeps zero fill — it is "too far out" by definition.

### Wilty

- **New `Wilted(combatant)` event**, emitted immediately before the `Death` a Wilty roll causes.
  Death is otherwise causeless in the event stream, which is why a Wilty kill reads as the
  combatant simply dropping; the event lets the GUI say why.

### Brief

PROJECT_BRIEF.md is amended alongside this ADR: §5.1 (the meter uses its own floored falloff,
damage keeps the linear one), §5.4 (fill frequency), §5.6 (per-hit spread and critical hits as
bounded volatility).

## Consequences

- Every matchup shifts. Unarmored numbers stay close (Tumbleweed 6 → 7.6 against DEF 5), but the
  player's damage against high-DEF strains rises sharply (Golem 5 → 9). Bestiary retuning is left
  to the next playtest rather than guessed here; all values remain §8 placeholders.
- `Stats` grows two fields, and `HitLanded` one; construction sites that need crits opt in
  explicitly, everything else is unaffected.
- The AI and the combat engine now see different numbers for the same hit (expected vs. drawn).
  Anything that needs to predict a hit's outcome — the AI today, any future preview UI — goes
  through `resolve_hit` with multiplier 1.0 and must treat it as an average.
- Meter fill and Swarm Attack damage no longer share a falloff; retuning one does not move the
  other.
