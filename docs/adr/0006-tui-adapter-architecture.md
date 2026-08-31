# 0006 — TUI adapter architecture

**Status:** Accepted
**Date:** 2026-08-31

## Context

Combat (ADR 0001), exploration (ADR 0002), skill tree (ADR 0003), the composition root (ADR
0004), and persistence (ADR 0005) are all complete: a fully tested, pygame-free engine covering
every mechanic in PROJECT_BRIEF.md §4–§6. Nothing has ever driven it interactively — `eye/main.py`
is an unrelated pygame movement stub, and every domain's own ADR named a real `ActionChooser`
adapter and a driving main loop as "a future UI epic's" job. This ADR is that epic's design: a
playable console (TUI) adapter, built to prove the primitives are fun before any pygame rendering
work is considered.

Three gaps existed before this could be built, each explicitly deferred by a prior ADR: (1) no
concrete `ActionChooser` beyond the test-only `ScriptedChooser` and `GreedyAI`; (2) no loop wiring
`Game.start_generation()` → `Generation.advance()`/`plant_seed()` → `Game.end_generation()` →
skill-tree spend → rebirth; (3) no real save path or call sites for `eye.persistence`'s
already-built port/codec/adapters (ADR 0005 resolved a `default_save_store()` factory but left
"a real filesystem path, deciding when to call `save()`/`load()`, and deciding what happens on a
`SaveDataError`" to this epic).

## Decision

- **New top-level package `eye/tui/`, pygame-free, same status as `eye/session/` or
  `eye/persistence/`**: imports `Game`/`Generation`/`eye.persistence`, nothing imports back into
  it. Renders via `rich`; resolves the per-OS save directory via `platformdirs` — both added as
  runtime dependencies via `uv add`. Launched with `python -m eye.tui` and a new `make play`
  target, parallel to the existing `make run`/`make serve`. `eye/main.py` is untouched — it stays
  the pygame stub until a real pygame epic exists; the TUI is a separate, complete entry point,
  not a replacement for it.
- **First playable milestone is the full generational loop in one sitting** — birth, screen-by-
  screen exploration with interactive combat, seed planting, death, skill-tree spend, rebirth, all
  persisted across process restarts — not a narrower combat-only or exploration-only slice. The
  engine underneath is already complete end-to-end, so slicing narrower would only defer proving
  the actual thing this epic exists to test: whether the self-vs-hive loop is fun to play.
- **Module split, five focused units:**
  - `chooser.py` — `TUIActionChooser(ActionChooser)`. Each `choose(actor, opponent, available)`
    call renders the live combat state (both combatants' HP/meter/active effects) via `render.py`,
    then blocks on a numbered-menu input until a valid choice is made.
  - `render.py` — free functions dispatching on `ExplorationEvent`/`BattleEvent`/`SessionEvent`
    (`match`/`case`, mirroring the ordered-event-list convention every domain already returns) to
    print via a `rich.Console`. Pure with respect to game state — events and combatant snapshots
    in, printed lines out, no mutation.
  - `skilltree_menu.py` — the between-generations spend screen: lists nodes by
    branch/sub-branch/tier with cost and lock state, loops accepting a node id to `purchase()`
    (catching and displaying the domain's raise on an invalid purchase) or a command to continue.
  - `save.py` — resolves the save path via `platformdirs.user_data_dir(...)`, wraps
    `eye.persistence`: `load_or_new(rng, chooser) -> Game` and `persist(game) -> None`.
  - `app.py` (+ `__main__.py`) — the main loop tying the above together; see below.
- **Combat rendering happens entirely through the chooser, not through `advance()`'s return
  value, and this requires no change to `Generation`/`Battle`.** `Generation.advance()` resolves
  an entire encountered battle synchronously inside one call, via the blocking chooser (ADR 0001's
  "future pygame combat-screen adapter... owns all pacing" seam, realized here). So real-time
  interaction during a fight happens through repeated `TUIActionChooser.choose()` calls, each
  rendering current combatant state before prompting; the `BattleEvent`s in `advance()`'s return
  are a recap printed after the fight ends, alongside the exploration recap for that screen. An
  alternative considered and rejected: giving `Generation` a round-by-round battle-stepping API so
  the TUI could drive `Battle.take_round()` itself for live per-round outcome rendering — rejected
  because it would change the public surface of Accepted, fully-tested composition-root code for a
  cosmetic gain (a mid-fight damage narration a line later), against house-rules' "prefer adding a
  module that plugs in over editing a shared core type."
- **Skill-tree spending is enforced as between-generations only**, at the interface level — the
  domain's `SkillTree.purchase()` stays callable at any time (ADR 0004 deliberately left this a
  UI-policy choice, not a domain constraint). `app.py`'s loop only ever calls into
  `skilltree_menu.run()` after `end_generation()`, matching PROJECT_BRIEF.md §4 ("between runs,
  spend Spores").
- **Exploration paces one screen per keypress.** Each `advance()` call's result renders before the
  loop blocks on input to continue, and `plant_seed()` is offered whenever `is_seed_ready` — a
  deliberate, readable pace over an auto-advancing loop with timed pauses, and trivially
  deterministic to test (no wall-clock dependency).
- **Save policy: persist after every `SessionEvent` that changes cross-generation state** —
  right after `end_generation()` (`SeedsMatured`/`SporesAwarded`) and after every accepted
  skill-tree purchase — not only on an explicit quit. Matches ADR 0005's own framing that death,
  not process exit, is the game's checkpoint: an accidental `Ctrl+C` should only ever cost the
  current generation's in-progress exploration, never a previously-completed one.
- **Startup always attempts `store.load()`.** No save → fresh `Game`, silently (the ordinary
  first-run path). A `SaveDataError` (corrupt data, or a purchased node no longer in `CATALOG`) is
  caught, a warning naming the problem is printed, and a fresh `Game` is constructed — the old save
  file is left on disk untouched (not overwritten) until the next successful `persist()`, so a
  player who cares can inspect or recover it manually. No new-game/continue menu exists for v1: the
  single-slot design (ADR 0005) makes "load if present, else start fresh" the entire startup
  policy.
- **Quitting mid-generation is expected to lose that generation's progress**, consistent with the
  point above — `app.py` catches `KeyboardInterrupt` at the top level to print a short "progress
  since your last generation ended is not saved" notice and exit cleanly, rather than a raw
  traceback, but does not attempt to persist mid-life state. This was already ADR 0005's decision
  ("mid-life `Generation` state... is explicitly not persisted"); this epic doesn't reopen it.
- **Combat renders as a scrolling log (`console.print()` per round), not a redrawing
  `rich.live.Live` panel.** Chosen for testability — captured `Console(file=io.StringIO())` output
  can be asserted on directly — over `Live`'s terminal-control-code redraws, which would require
  asserting on renderable objects instead of text. Matches PROJECT_BRIEF.md §7's "minimal UI"
  guardrail for this stage.
- **Tests assert on output structurally, not byte-for-byte, and don't assert on color/style
  codes.** `render.py`/`chooser.py`/`skilltree_menu.py` tests check for the presence and order of
  the substantive text a scene should contain (e.g. an HP number, an action name, a prompt), not
  exact rendered strings — so a deliberate, cosmetic rendering tweak doesn't cascade into failing
  every TUI test. `TUIActionChooser`'s input side is tested via a fake input source (an
  `Iterator[str]`-backed stand-in passed to its constructor), the same role `ScriptedChooser`
  already plays for combat tests. `save.py` is tested against `eye.persistence`'s existing
  `SaveStore` fakes, with a separate, narrow test for the real `platformdirs`-based path resolver.
  `app.py` gets one end-to-end smoke test: a seeded `random.Random`, a scripted input queue, and a
  fake `SaveStore`, asserting the loop runs a generation to death, reaches the skill-tree menu, and
  persists — no real stdin/stdout/disk.

## Consequences

- A future pygame/rendering epic (if one ever happens) reuses the same `Game`/`Generation`
  composition root and `eye.persistence` port this TUI epic wires up for the first time — only
  `eye/tui/`'s adapters (chooser, render, save's path resolution) would need pygame-side
  equivalents, not the loop structure itself.
- Multi-Biome/multi-Strain content growth (PROJECT_BRIEF.md §8, still open) is orthogonal to this
  epic — `render.py`'s event-dispatch design already renders whatever `Strain`/`Biome` a future
  bestiary/encounter change introduces, with no TUI-side change required.
- No save-slot selection, no mid-life persistence, and no skill-tree access outside the
  between-generations window exist after this epic, matching the scope decided above — any of
  these becoming a real ask later is new scope, not a gap in this design.
- This ADR is the durable record; per-component GitHub issues (an Epic plus its sub-issues) carry
  the implementation-level detail forward, following the pattern every prior domain epic in this
  project used.
