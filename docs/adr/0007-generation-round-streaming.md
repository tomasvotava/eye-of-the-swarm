# 0007 — Generation round-by-round battle event streaming

**Status:** Superseded by [0008](0008-driver-owned-battle-stepping.md)
**Date:** 2026-08-31

## Context

`Battle.take_round()` already returns per-round `list[BattleEvent]` (ADR 0001) — that primitive
is correct: multi-hit actions, deaths, revives, and DoT ticks are already ordered, discrete events
within a round. The gap is one level up: `Generation._resolve_battle()` drains the entire
`while not battle.is_over: events.extend(battle.take_round())` loop internally and only returns
once the fight is fully decided, so the round-by-round granularity that already exists is
flattened into one batch before any driver ever sees it. Per direct playtesting feedback
(Epic #94), a future pygame renderer needs to animate a fight hit-by-hit — health bars ticking
down, effect icons appearing, death/revive animations — which requires getting control back
between rounds, not a batch of already-resolved events handed over all at once.

ADR 0006 already considered and rejected a round-stepping API for `Generation`, on the grounds
that it would only be "a cosmetic gain" for the TUI's scrolling-log adapter, which has no
live-pacing requirement. That call was correct for what it was deciding — a scrolling log has no
live-pacing need — but it did not anticipate a real-time renderer needing the same seam for a
non-cosmetic reason. This ADR reverses that specific call. ADR 0006 itself is not edited: its
epic (the TUI epic) is already merged, so the Accepted record stays as originally written; this
ADR supersedes only the one bullet about round-stepping, by reference.

## Decision

- **`Generation.advance()` changes from `list[SessionEvent]` to `Iterator[list[SessionEvent]]` —
  a generator.** Each yield is one increment of progress: the screen's exploration events (one
  yield, unchanged in content from today); if that screen was `EnemyEncountered`, `battle.start()`'s
  events as one yield followed by one yield per `battle.take_round()` until `battle.is_over`; and
  finally `[GenerationEnded()]` as a last yield, only if the character died. The `Character`
  HP write-back and spore-award bookkeeping that today runs after the battle's `while` loop keeps
  running after the yielding loop, before the generator returns — still atomic domain state, just
  now interleaved with driver control between yields.
- **No changes to `eye/combat/battle.py` or `eye/exploration/run.py`** — `Battle.take_round()` was
  already the right primitive; `Generation` was the only place eagerly draining it.
  `Generation.plant_seed()` is unaffected (a single atomic action, no round structure).
- **This is a scoped amendment to CLAUDE.md's "mutable aggregates return an ordered
  `list[...Event]` per call" convention**, for `Generation.advance()` only: "per call" now means
  "per yielded increment," not "per Python call." `Battle.take_round()`, `ExplorationRun.advance()`,
  and `SkillTree`'s mutators keep their existing one-call-one-list contract; none of them have a
  comparable multi-increment need.
- **`eye/tui/app.py`'s `_play_generation` drains the generator and renders each chunk as
  produced**, replacing today's single `render.events(console, generation.advance())` call with a
  loop over `generation.advance()`. No changes to `eye/tui/chooser.py` (already renders
  per-decision at each `choose()` call) or `eye/tui/render.py` (`events()` already accepts a flat
  `Sequence[SessionEvent]`, which each yielded chunk already is).
- **Deliberately no new pacing added to the TUI.** No per-round pause or redraw — ADR 0006's
  scrolling-log UX stays exactly as decided. This migration proves the new interface end-to-end
  without reopening ADR 0006's already-settled "no live redraw for TUI" call, which stays out of
  scope here. Rendered output for a TUI player is identical in content and order to today's.

## Consequences

- A future pygame combat-screen adapter can drive `Generation.advance()` directly in an
  `async def` main loop — the generator's natural suspend-at-`yield` behavior composes with
  pygbag's cooperative-yield requirement without a callback/threading layer, which ADR 0004's
  consequences had left as an open problem for that epic to solve for `ActionChooser.choose()`.
  This doesn't solve `choose()`'s own blocking-call problem, but round delivery won't add a second
  instance of the same unsolved problem.
- `eye/session/generation.py` and `eye/tui/app.py` are the only two files whose public/observable
  behavior changes; `eye/combat/`, `eye/exploration/`, `eye/tui/chooser.py`, and
  `eye/tui/render.py` are untouched.
- `Generation`'s existing tests move from asserting on a returned list to draining the generator,
  plus new tests asserting on individual yielded chunks where round-by-round structure adds value
  (e.g. the chunk containing a lethal hit also contains the `Death` event, with nothing after it).
- The full design rationale (interface-shape alternatives considered, TUI-pacing trade-off) lived
  in a working spec during design that was not committed to this repository. This ADR is the
  durable record; per-component GitHub sub-issues under Epic #94 carry the implementation-level
  detail forward.
