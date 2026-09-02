# 0012 — Screen-walking movement

**Status:** Accepted
**Date:** 2026-09-02

## Context

PROJECT_BRIEF.md §9.1 asks for the "walk right until you touch the thing" (§6) traversal to become
visible: the player enters a screen from its left edge, its encounter is visible ahead at a fixed
position, and the player chooses when to walk toward it, rather than one keypress both moving to
the next screen and revealing its result in the same instant as today. `advance()` must still fire
exactly once per screen, "as early as it does today, when the screen loads" — the walk is a
presentational delay between a decision already made and its reveal, not a trigger for it.

ADR 0009's Consequences section flagged, in advance, exactly the problem this ADR has to solve:
PROJECT_BRIEF.md §5.2's plant-decision-timing invariant (you cannot preview a screen and
retroactively plant for the one before it) holds in v1 only as a side effect of
`ExplorationRun.advance()` and its reveal being one atomic call. Splitting "arrived at the next
screen" from "touched its trigger" into separate steps — which is exactly what this ADR does —
removes that atomicity, so this ADR must re-derive where the plant-decision window closes rather
than assume ADR 0009's enforcement mechanism still holds.

A further constraint, surfaced during design: the player must not be able to plant a seed at a
screen whose encounter they haven't yet resolved — planting is only legal once they've dealt with
whatever is on the current screen (collected the pickup, defeated the enemy) and before they've
moved on to the next one. This is a stricter, more precisely located requirement than "sometime
after arriving," and shapes the phase design below.

This ADR is blocked on ADR 0011 (sprite asset pipeline & animation framework): the player must
stay visibly animated (looping its idle clip) while walking, since no walk-cycle art exists yet
and the idle clip is reused as a placeholder for the `WALK` state — `ExplorationScene` is the
first real consumer of `Animator`/`get_animation_set`.

Nothing in `eye/exploration/`, `eye/session/`, or any other domain module changes.
`ExplorationRun.advance()`'s signature, return type, and side-effecting behavior are untouched;
only when the GUI calls it changes.

## Decision

- **A screen has three x-positions**: entry (left edge), an encounter marker (fixed, roughly
  mid-screen), and an exit (right edge). `ExplorationScene` becomes a 4-phase state machine over
  them:
  ```
  RESOLVED --[ADVANCE]--> WALKING_TO_EXIT --[arrival]--> AT_ENTRY --[ADVANCE]--> WALKING_TO_ENCOUNTER --[arrival]--> RESOLVED (next screen)
     ^ plant legal only here                  |
     |                                         v
     +---------- generation.advance() fires here, for the NEW screen
  ```
  - **`RESOLVED`** — player sits at the encounter marker; this screen's outcome is already known
    and applied (or it's the spawn screen, with nothing to resolve). **Plant is legal only in this
    phase** — pressing the plant key elsewhere is a silent no-op, mirroring the existing
    `is_seed_ready` guard style. ADVANCE starts the walk to the exit.
  - **`WALKING_TO_EXIT`** — arrival at the exit immediately calls `generation.advance()` for the
    next screen (this is the "as early as when the screen loads" call — it applies that screen's
    resource/effect side-effects domain-side right away, exactly as `advance()` already does
    today; only the GUI's *reveal* of the outcome is deferred) and resets the player to the new
    screen's entry position.
  - **`AT_ENTRY`** — idle at the new screen's left edge. The just-generated encounter is already
    visible at the marker position (an enemy sprite standing there, etc. — nothing about *what* it
    is stays secret) but untriggered. ADVANCE starts the walk to it.
  - **`WALKING_TO_ENCOUNTER`** — arrival triggers the reveal: `EnemyEncountered` returns an
    `EnterCombat` transition; otherwise the HUD message is shown and the phase drops to
    `RESOLVED`.
- **Every fresh `ExplorationScene` construction starts in `RESOLVED`, uniformly — no
  combat-vs-fresh-generation branch in `GameDriver`.** A new generation's spawn screen has nothing
  to resolve (fine — `RESOLVED` with nothing pending). Returning from a won battle also lands in
  `RESOLVED`, positioned at the encounter marker: the fight itself *was* resolving the encounter,
  so there's nothing left to walk to. This is the re-derived plant-decision window required by ADR
  0009's flagged consequence: it is exactly the `RESOLVED` phase, and it survives the exploration
  ⟷ combat scene swap without `GameDriver` needing any awareness of walk phases.
- **`plant_seed()` itself is unchanged** — still plants at `_current_screen`, still synchronous on
  keypress. Only the GUI's gating of *when* it forwards the plant key changes.
- **The core invariant still holds structurally, unaffected by the walk animation**:
  `_current_screen` only ever advances via `generation.advance()`, which happens exactly once per
  screen at the `WALKING_TO_EXIT` arrival boundary, and there is no mechanic to move backward.
  Once it advances, the previous screen is permanently behind — planting always targets wherever
  `_current_screen` currently points, which the GUI never lets outrun what's been resolved.
- **New `eye/gui/tuning.py`** holds GUI-side pacing constants (walk duration/speed for both
  `WALKING_TO_EXIT` and `WALKING_TO_ENCOUNTER`) — mirrors PROJECT_BRIEF.md §9.5's own note that
  even presentation pacing belongs in a `tuning.py`, not a magic number in scene code.
- **Animation wiring**: the player's `Animator[PlayerAnimationState]` (ADR 0011,
  `required_states=frozenset({IDLE, WALK})`) is set to `WALK` on entering either walking phase and
  back to `IDLE` on entering either idle phase (`RESOLVED`, `AT_ENTRY`). `walk.png`/`walk.json`
  ship as byte-for-byte duplicates of `idle.png`/`idle.json` (no walk-cycle art exists yet) —
  proves the state machine drives a visible state change end-to-end; a future art delivery swaps
  just the asset files, no code change.

## Consequences

- `GameDriver`'s routing policy (ADR 0010) is untouched: it still only distinguishes
  `EnterCombat`/`BattleConcluded`/`Continue` and constructs `ExplorationScene` the same way from
  every path — it has no awareness that `ExplorationScene` now has internal phases.
  `BattleConcluded`'s non-died branch already just returns a fresh `ExplorationScene`, which now
  happens to start in `RESOLVED` as a consequence of this ADR, not a new parameter `GameDriver`
  has to pass.
  `EnterCombat`'s payload (the `EnemyEncounter`) is unchanged — only when it's returned from
  `ExplorationScene.update()` moves, from immediately on `advance()` to `WALKING_TO_ENCOUNTER`
  arrival.
- Any future implementation of PROJECT_BRIEF.md §9.2 (cosmetic door choice) builds on top of the
  `AT_ENTRY`/`WALKING_TO_ENCOUNTER` phases established here, rather than needing its own
  traversal model.
- Structural tests (phase transitions, `advance()` call count/timing, `EnterCombat` withheld until
  `WALKING_TO_ENCOUNTER` arrival, plant accepted only in `RESOLVED`, fresh-construction-always-
  starts-`RESOLVED` for both the new-generation and post-combat-win paths) replace/extend
  `test_exploration.py`'s current single-call-does-everything assertions.
