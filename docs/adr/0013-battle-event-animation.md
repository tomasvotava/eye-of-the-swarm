# 0013 — Battle event animation

**Status:** Accepted
**Date:** 2026-09-05

## Context

PROJECT_BRIEF.md §9.5 asks for a combat round's events to reveal one at a time — "a debuff roll,
a struck hit, an applied effect, recoil damage — each with a short pause before the next appears"
— rather than all at once. Today, `CombatScene.update()` calls into `Battle` every frame as soon
as `turn_phase` says the next step is ready, and `CombatScene._record()` dumps every event from
that call into the log deque in the same instant. HP bars, meter bars, and buff icons all read
live `Combatant` state directly. The result: a whole round — multi-hit combos, reflects, DoT
ticks, deaths — appears fully resolved in one frame, with the log text as the only (already
instant) narration of it.

`Battle`'s methods (`query_player_turn`, `resolve_player_turn`, `resolve_enemy_turn`) are atomic
(ADR 0008): one call already mutates every `Combatant` involved and returns the *complete*
`list[BattleEvent]` for everything that happened. There is no intermediate domain state to poll
mid-call. Pacing has to be a GUI-side concern layered on top of the returned list, not a way of
calling the domain more slowly — the same shape ADR 0012 used for `ExplorationRun.advance()`:
the domain call still fires exactly when its trigger condition is met; only the GUI's *reveal* of
what it returned is deferred.

Nothing in `eye/combat/`, `eye/session/`, or any other domain module changes. `Battle`'s public
surface, its atomicity, and `CombatScene`'s existing eager-call-when-`turn_phase`-is-ready pattern
are all untouched; only when the GUI acts on what a call already returned changes.

## Decision

- **`CombatScene` gains a GUI-side reveal queue.** A domain call's returned events land in
  `_pending_events` instead of being applied to the log immediately. `update(dt)` reveals at most
  one event per call, gated by a fixed interval: new `eye/gui/tuning.py` constant
  `BATTLE_EVENT_REVEAL_INTERVAL_SECONDS` — a playtesting-driven placeholder (PROJECT_BRIEF.md §8),
  same convention ADR 0012 used for its own walk-pacing constants. **No skip/fast-forward this
  epic** — purely auto-timed, matching §9.5's own wording ("rather than waiting on a keypress")
  and ADR 0012's precedent of no early-arrival input; a follow-up can add one later if pacing
  proves too slow in practice.
- **Gating invariant — the thing this ADR has to state explicitly, the same way ADR 0012 had to
  re-derive the plant-decision window for exploration:** the next domain call
  (`query_player_turn` / `resolve_player_turn` / `resolve_enemy_turn`), the action menu becoming
  interactive, and the `BattleConcluded` transition are all withheld until `_pending_events` is
  empty. `Battle` itself may already be internally several events ahead of what the player has
  seen — `battle.is_over` can already be `True`, `battle.turn_phase` can already have moved past
  the round currently mid-reveal — `CombatScene` only acts on that once nothing is left to
  reveal. This is a pure GUI-side hold on when `CombatScene` next looks at `Battle`'s state or
  calls one of its methods; nothing about `Battle`'s contract changes.
- **Event-synced display state, not log-only pacing.** HP/meter bars and buff icons stop reading
  live `Combatant` state and instead read a small per-side displayed-state struct (`Combatant` →
  displayed HP, meter, active `EffectName` set) that `CombatScene` owns:
  - Seeded from the live `Combatant` at `CombatScene` construction, *before* `battle.start()`'s
    events (e.g. a Resonance meter prefill) are queued — so a pre-existing effect the combatant
    entered battle already holding (e.g. carried Fibrous) shows immediately, unpaced, while
    anything battle.start() itself causes still animates in normally through the queue.
  - Mutated only as each event is revealed, driven by that event's own `_after` field
    (`target_hp_after`, `meter_after`, etc.) and by `EffectApplied`/`EffectExpired` for the active-
    effect set.
  - `_draw_combatant`/`_draw_buff_icons` read this struct instead of `combatant.current_hp` /
    `combatant.effects.has(...)`.
  - Rejected alternative: pacing only the log text and leaving bars/icons on live `Combatant`
    reads. Cheaper, but the bars would then visibly "know the outcome" before the log narrates
    it — the exact instant-reveal problem this ADR exists to fix, just moved from the log to the
    bars instead of removed.
- **Sub-issue split** (mirrors Epic #146's #152/#153 shape — state machine first, then wire
  visuals into it), in dependency order:
  1. Paced reveal queue + the gating invariant above; log text paced through it; new
     `eye/gui/tuning.py` constant.
  2. Event-synced display state for HP/meter bars and buff icons, reading the per-side struct
     instead of live `Combatant`. Blocked by (1) — needs the queue to derive displayed state from.

## Consequences

- `CombatScene.update()`'s control flow gains an explicit "reveal in progress" branch checked
  before any domain call, `is_over` check, or transition — every one of those call sites needs the
  `not self._pending_events` guard added, not just the ones obviously related to display.
- Structural tests (mirroring ADR 0012's): queue drains one event per tick; next domain call
  withheld while the queue is non-empty; `BattleConcluded` withheld until the last event (e.g.
  `BattleEnded`) is revealed; displayed HP/meter/effects reflect only-revealed-so-far state (not
  live `Combatant`) mid-reveal; pre-existing effects seeded correctly at construction. These
  extend `tests/gui/scenes/test_combat.py`'s existing single-call-reveals-everything assertions.
- A future skip/fast-forward affordance (if playtesting wants faster repeat fights) builds on top
  of the reveal queue established here — drain multiple/all pending events in one `update(dt)`
  call on input — rather than needing its own traversal model.
- No domain change: `eye/combat/`, `Battle`, `Generation` untouched. `eye/gui/scenes/combat.py`
  and `eye/gui/tuning.py` are the only modules affected.
