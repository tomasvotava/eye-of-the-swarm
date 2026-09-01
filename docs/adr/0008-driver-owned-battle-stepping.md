# 0008 — Driver-owned battle stepping

**Status:** Accepted
**Date:** 2026-09-01

## Context

Issue #99 flagged that `Generation._resolve_battle()`'s `Character` HP write-back and spore-award
bookkeeping run *after* its internal `while not battle.is_over: yield battle.take_round()` loop —
so a driver that stops draining `Generation.advance()` early (a `break`/`return`, or an exception
propagating out of the consuming loop) leaves `Character` state stale, silently.

Investigating that bug surfaced it as a symptom rather than the root problem. `Battle.take_round()`
has had correct per-round granularity since ADR 0001 — that was never the gap. The actual gap is
that `Generation._resolve_battle()` owns a private loop that drives an entire battle to completion
internally, resolving decisions by calling into a `player_chooser: ActionChooser` injected at
construction time. Because that loop is internal, the only way anything outside `Generation` can
affect a decision inside it is via that injected callback — and a blocking callback deep inside a
domain call is exactly the shape three ADRs in a row have independently flagged as unsolved:

- ADR 0001's Consequences named a future pygame adapter's blocking `choose()` call as an open
  problem for that epic to solve.
- ADR 0004's Consequences left "reconcile blocking-call `choose()` semantics with pygbag's
  cooperative-yield requirement (an `async def` main loop that periodically `await`s to hand
  control back to the browser)" as an explicit open item for a future UI epic.
- ADR 0007 made `Generation.advance()` a round-stepping generator specifically so a driver could
  get control back between rounds — but this only changed how *output* events are delivered. The
  *input* side (the injected chooser, called synchronously from deep inside `Battle._act()`,
  invisible to anything outside `Battle`) was untouched, and its Consequences section deferred the
  same blocking-call problem a third time, verbatim.

`Generation.plant_seed()` already solves the equivalent problem for planting, differently: ADR 0004
deliberately gave planting no callback/pull point in the domain — "it's just a method the driver
calls at its own discretion, in its own loop," because `Game` doesn't own a generation's
screen-by-screen loop; the driver does. Combat never got the same treatment, because
`_resolve_battle()` kept driving an entire battle to completion internally rather than handing the
`Battle` instance to the driver the way `Game.start_generation()` hands the driver a `Generation`.

## Decision

- **The driver takes direct ownership of stepping `Battle`, the same way it already steps
  `Generation` and already calls `plant_seed()`.** `Generation.advance()` no longer constructs and
  drains a `Battle` internally. When a screen's event is `EnemyEncountered`, the driver calls a new
  `Generation.start_battle(encounter) -> Battle`, which resolves the player and enemy `Combatant`s
  (unchanged from today's `_resolve_battle()`) and constructs the `Battle` — with only the enemy's
  `ActionChooser` (`GreedyAI`) injected — and returns it undriven. The driver drives it directly in
  its own sub-loop, exactly as `Battle.take_round()` was always designed to be driven (ADR 0001).
  Once `battle.is_over`, the driver calls a new `Generation.finish_battle(battle) -> list[SessionEvent]`,
  which writes `Character.current_hp` from the player `Combatant` and awards the Strain's spores on
  a win — raising if called before `battle.is_over`, mirroring `Game.end_generation()`'s existing
  "raise if not finished" guard. This runs as an ordinary synchronous call the driver makes next,
  not as trailing code inside a suspended generator frame — resolving #99's failure mode entirely,
  rather than patching this one instance of it: there is no longer an internally-owned drain loop
  for a driver to abandon partway through.
- **`Generation.advance()` reverts to `list[SessionEvent]`, a plain method call again.** Nothing
  about screen advancement itself ever needed interruption — `ExplorationRun.advance()` was always
  a single atomic call (walk into one screen, one trigger fires). ADR 0007's round-stepping
  generator existed only to get battle-round events flowing incrementally; once the driver drives
  `Battle` directly, that need is gone. The scoped amendment ADR 0007 made to CLAUDE.md's
  one-call-one-list convention (for `Generation.advance()` specifically) is removed — the aggregate
  rejoins the ordinary convention with no exception. **This supersedes ADR 0007 in full** — unlike
  ADR 0007's own treatment of ADR 0006 (a single-bullet amendment, by reference, with 0006's
  Accepted record left otherwise as originally written, since 0006's epic was already merged), 0007's
  central decision is what's being reversed here, so 0007's Status line is updated to point to this
  ADR rather than left silently stale; its body is otherwise untouched, per house-rules' "supersede,
  don't rewrite history."
- **`Battle` drops the player-side `ActionChooser` and gains an explicit query/resolve pair for the
  player's turn.** Wilty (spontaneous death) and Vegetative (skipped turn) are pre-turn checks that
  can pre-empt the need for a decision entirely, so the driver needs to know *before* it prompts its
  own UI whether this round even needs an action. The shape (naming is implementation latitude, not
  binding here):
  - A query resolving this round's pre-turn checks for the player exactly once, caching the outcome
    so a later resolve call doesn't re-roll it, and returning either "the player needs to choose,
    here's what's available" or "the turn already concluded without one, here are the events"
    (covering Wilty firing with or without an Adrenaline-triggered revive, and Vegetative's skip).
  - A resolve call taking the chosen action and applying it plus every consequence today's
    `_act()`/`_run_actions()` chain already handles (multi-hit sequences, Uprooted's extra-action
    loop, Clouded Judgement's swap, meter fill/consumption), returning `list[BattleEvent]`.
  - The enemy's full turn stays one automatic call — pre-turn checks, `GreedyAI`'s decision, and
    resolution together — since `GreedyAI` never needs external input and there is nothing for a
    driver to be asked.
  - `ActionChooser` itself is unchanged in shape and stays exactly where it already lives
    (`eye/combat/ai.py`); it simply has no player-side implementation to satisfy anymore.
    `ScriptedChooser` remains available for scripting the enemy side in tests where that's useful.
  - A thin, explicitly test/headless-only helper wraps the query/resolve loop behind a plain
    "pick an action" callable, driving a full battle to completion in one call — the `unfold()`
    shape floated during design, kept as sugar over the granular API for tests and any future
    headless simulation/tuning use, not the domain's primary interface, and free to change without
    touching the seam a real driver uses.
- **`Game`/`Generation` drop the player `ActionChooser` constructor parameter entirely.**
  `Game.__init__` no longer takes `player_chooser`; nothing at the composition-root level threads a
  player-side chooser anywhere. `eye/tui/save.py`'s `load_or_new(rng, chooser, save_store)` loses
  its `chooser` parameter for the same reason.
- **`eye/tui/chooser.py`'s `TUIActionChooser` is removed.** `eye/tui/app.py`'s `_play_generation`
  restructures: on `EnemyEncountered`, it calls `generation.start_battle(...)`, drives a nested
  combat loop calling the query/resolve pair directly — rendering combatant state and the action
  menu, reading input — then `generation.finish_battle(...)` once the battle is over. The rendering
  and input-parsing logic `TUIActionChooser` used (`render.combatant_state`, the numbered-menu
  print, `_input.py`'s parsing) is reused from where it already lives, just called inline from
  `app.py`'s combat loop instead of from inside an injected chooser object. Exact module
  organization (a new `eye/tui/combat.py`, or inline in `app.py`) is an implementation call.
- **This amends ADR 0001's chooser section** (the player side of "player and enemy action selection
  share one `ActionChooser` protocol" no longer holds — only the enemy side does now) **and closes
  the open item ADR 0004's Consequences left for a future UI epic** ("reconcile blocking-call
  `choose()` semantics with pygbag") — there is no longer a blocking call to reconcile, because the
  player never goes through an injected chooser at all. Both by reference; neither ADR's body is
  edited, per this project's established supersede/amend-by-reference convention.

## Consequences

- A future pygame combat-screen adapter drives `Battle` exactly the way the TUI now does: call the
  query, render and await input, call resolve, repeat. This composes naturally with an async main
  loop because the suspension point — waiting for player input — lives entirely in the driver's own
  code, not inside any domain call. This closes the open problem ADR 0001/0004/0007 each deferred to
  the next epic, without introducing generators, coroutines, or a decision-request protocol to do
  it.
- `eye/combat/battle.py`'s public surface changes for the first time since ADR 0001 (Accepted):
  `take_round()` is replaced by the player query/resolve pair plus a single automatic enemy-turn
  call; `player_chooser` leaves the constructor.
- `Battle`'s and `Generation`'s existing tests need real restructuring: anything built around
  `ScriptedChooser` queuing player actions and draining `take_round()`/`advance()` to completion
  moves to explicit per-round query/resolve calls (or the new test-only simulate helper), which is
  more verbose per test but states each round's action explicitly rather than through a pre-loaded
  queue popped from inside the domain.
- Issue #99 is resolved as a byproduct of this Epic rather than by a dedicated patch — whichever
  sub-issue changes `Generation`'s battle-driving shape closes it.
- The full design rationale (API-shape alternatives considered — a `.send()`-driven coroutine
  protocol, a unified generator-based chooser interface — and why both were rejected in favor of
  this shape) lived in a working spec during design that was not committed to this repository. This
  ADR is the durable record; per-component GitHub sub-issues under the tracking Epic carry the
  implementation-level detail forward.
