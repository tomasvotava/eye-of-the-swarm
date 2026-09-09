# 0013 — Battle event animation

**Status:** Accepted
**Date:** 2026-09-05 (amended 2026-09-07 — see Amendment note below)

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

## Amendment note (2026-09-07)

The original decision below paced revelation on a single fixed-interval timer, one `BattleEvent`
per tick, log-only. That shipped as issue #164 (PR #169). Asked to also animate HP-bar deltas,
the actual intent turned out to be bigger than log pacing: every event should drive real
animation — a hit switches the target's sprite to a `HIT` state and waits for *that specific
clip* to finish (which varies per enemy) before the HP bar rolls; a buff/debuff shows as a large
center-screen icon with a description; there is ultimately no persistent on-screen log. A single
shared timer can't express "wait exactly as long as this enemy's hit animation takes." This
amendment replaces the fixed-timer reveal queue with phase-sequenced playback, superseding
issues #164/#165/#167 as originally scoped (see the working spec at
`docs/superpowers/specs/2026-09-07-battle-event-phase-playback-design.md` for the full
brainstorm). PR #169 was closed unmerged rather than landed-then-reworked, since its core timing
mechanism is exactly what this amendment replaces.

## Decision

- **`CombatScene` gains a phase-sequenced playback queue**, not a fixed-timer reveal queue. Each
  domain call's returned events land in `_pending_events`, unchanged in shape from the original
  decision. What changes is how they're paced: each `BattleEvent` maps to an explicit,
  exhaustively-matched `list[Phase]` (`_phases_for`, same `assert_never` discipline as the
  existing `_describe_event`), and `CombatScene` plays through one event's phases before moving
  to the next.
- **`Phase` is one generic, data-only type**, not a closed union of phase kinds:
  ```python
  @dataclass(frozen=True, slots=True)
  class Phase:
      duration_seconds: float
      on_start: Callable[[], None] = lambda: None
      on_progress: Callable[[float], None] = lambda fraction: None  # fraction in [0, 1]
      on_complete: Callable[[], None] = lambda: None
  ```
  A zero-duration phase (e.g. an instant sprite-state switch) completes in the same call it
  starts; a phase with real duration consumes that call's `dt` and blocks until the next frame.
  This makes "reveal the first event of a batch immediately, but pace everything after that"
  fall out of the driver's own control flow rather than needing a dedicated flag — see
  Consequences.
- **Every `BattleEvent` variant gets an explicit phase list**, built from three reusable
  treatments:
  - **Animation-driven** (`Death`, `HitLanded`, `HitReflected`, `SelfDamageTaken`, `Revive`): sets
    one or more combatants' animation state and, where relevant, tweens `DisplayedCombatantState`
    toward the event's own `_after` field. Duration for "wait for this clip" is precomputed from
    the clip's own data (`len(frames) * frame_duration_seconds`, exposed as
    `AnimationClip.total_duration_seconds`) — exact given `AnimationClip`'s single uniform
    `frame_duration_seconds`, not queried from a live "is this animator done" signal, which would
    reintroduce per-kind polymorphism into `Phase` for no additional correctness. `HitLanded` can
    drive two animators at once from one phase's `on_start` (attacker's `ATTACK`, target's `HIT`),
    since animators tick unconditionally every frame regardless of which phase is active — no
    separate "windup" event needed even for multi-hit combos.
  - **`Announcement`** (icon + short text + hold, one shared visual language): `EffectApplied`,
    `EffectExpired`, `TurnSkipped`, `ExtraActionTriggered`, `BattleEnded`. Where it is anchored
    follows what it is about: an effect card carries the combatant the effect landed on and is
    drawn over that combatant's own half of the screen — typeset to that half's width, so which of
    the two it concerns is readable without parsing the subtitle — while a plain announcement
    (`TurnSkipped`/`ExtraActionTriggered`/`BattleEnded`) concerns the fight rather than one side of
    it and stays centered.
  - **`Overlay`** (lighter, target-local — reuses the `HIT` animation state plus a small icon at
    the target's position, naming the effect and the signed HP it moved, not a card of its own):
    `DotTicked`, `HealApplied`. These can repeat every turn; a full `Announcement` each time would
    get old fast. The label sits *beside* the icon rather than stacked above it, so the block stays
    exactly one icon tall — the HUD panel leaves no room above the taller of the two sprites, and a
    block that grows upward runs into it, while one that grows sideways from the sprite's own
    centre has no such ceiling. The HP it names is the movement the bar will actually make, derived
    from `target_hp_after` rather than the event's nominal `damage`/`amount`: the domain caps a heal
    at `max_hp` and lets a lethal tick's `target_hp_after` go negative, so a label reading the
    nominal field would contradict the bar it exists to explain.
  - **`Tween`** alone (no animation-state change): `MeterFilled`, `MeterConsumed`.
  - `ActionChosen` is the one variant that's legitimately phase-less (`[]`).
- **`AnimationClip` gains `loop: bool = True`.** One-shot states (`HIT`, `ATTACK`, `DEAD`) set
  `loop=False`; `Animator.update()` freezes on the final frame instead of wrapping once such a
  clip finishes — fixes a real bug (a slow frame re-triggering a hit flinch mid-clip),
  independent of how phase duration is computed.
- **`DisplayedCombatantState` numeric fields are `float`**, not `int` (rounded only at draw
  time), so `on_progress` can interpolate smoothly. Otherwise unchanged from the original
  decision: seeded from the live `Combatant` at `CombatScene` construction, before
  `battle.start()`'s own events are queued; mutated only by phase callbacks, never by live
  `Combatant` reads.
- **`CombatScene` gains its own combat-facing animation-state enum** (`IDLE`/`ATTACK`/`HIT`/
  `DEAD`), mirroring `dev_assets.py`'s preview-only `EnemyAnimationState` (that file's own
  docstring already says combat wiring must define its own type, not reuse the preview one).
  This is load-bearing for phase durations, not a decorative layer added after visuals land —
  originally scoped as a separate, later sub-issue (#167), now foundational.
- **New `eye/gui/tuning.py` constants** replace `BATTLE_EVENT_REVEAL_INTERVAL_SECONDS`:
  `BATTLE_VALUE_TWEEN_SECONDS` (HP/meter tweens) and `BATTLE_ANNOUNCEMENT_HOLD_SECONDS`
  (`Announcement` hold time) — playtesting-driven placeholders, same convention. `Overlay` and
  every animation-driven phase need no new constant; their duration comes from clip data.
- **The log is kept as a data structure, not as a default on-screen widget.** Every event still
  gets a description appended to `self._log` (now unbounded, not the current rolling
  `maxlen`-4 window) — cheap to expose via an on-demand recall view later — but `_draw_log`'s
  always-on rendering is removed now. Building that recall UI is separate, low-priority future
  work, not part of this epic.
- **Gating invariant, restated for the phase model** (same substance as the original decision,
  now covering two collections instead of one): the next domain call (`query_player_turn` /
  `resolve_player_turn` / `resolve_enemy_turn`), the action menu becoming interactive, and the
  `BattleConcluded` transition are all withheld while `self._current_phases or
  self._pending_events` is truthy. `Battle` itself may already be internally ahead of what the
  player has seen; `CombatScene` only acts on that once nothing is left to play.
- **Sub-issue split**, superseding the original #164/#165/#167 split (filed against Epic #163):
  1. `Phase` primitive + driver + `AnimationClip`/`Animator` loop support — foundational, no
     domain change.
  2. `DisplayedCombatantState` + combat-facing animation enum + animation-driven phases for
     combat swings (`Death`/`HitLanded`/`HitReflected`/`SelfDamageTaken`/`Revive`). Blocked by 1.
  3. `Announcement` + `Tween`-only mapping (`EffectApplied`/`EffectExpired`/`TurnSkipped`/
     `ExtraActionTriggered`/`BattleEnded`/`MeterFilled`/`MeterConsumed`). Blocked by 1, parallel
     to 2 (no animation-state dependency).
  4. `Overlay` + `DotTicked`/`HealApplied` mapping. Blocked by 1 and 2 (reuses the `HIT` state
     and animator wiring 2 introduces).
- **Full post-battle report** (win/loss, spores earned, round count, duration) is explicitly out
  of scope here — a screen after `BattleConcluded` fires, not a phase, orthogonal to this design.

## Consequences

- `CombatScene.update()`'s control flow keeps its "reveal in progress" branch checked before any
  domain call, `is_over` check, or transition — now driven by `_advance_phases(dt)` rather than a
  fixed-interval timer. Zero-duration phases (and `ActionChosen`'s empty list) cascade through a
  single call for free; a phase with real duration consumes that call's entire `dt` and blocks.
  This makes the original decision's "first event of a batch reveals immediately, but pacing
  applies after that" fall out of the driver's control flow by construction, rather than through
  the `_revealed_this_call` flag PR #169 needed after an independent review caught a
  double-reveal-per-call bug at batch boundaries — that class of bug is structurally impossible
  here, not just guarded against.
- Structural tests (mirroring the original decision's, extended): `_advance_phases` never
  consumes more than one call's `dt` against more than one real-duration phase; zero-duration
  phases and empty phase-lists cascade within a single call; the gating invariant holds across
  both collections; `DisplayedCombatantState` reflects only fully-completed phases, never live
  `Combatant`; `_phases_for` is exhaustive over `BattleEvent`; `Animator` with `loop=False`
  freezes on the last frame under an oversized `dt`; the log records every event even though
  `_draw_log` no longer renders it by default.
- A future skip/fast-forward affordance (if playtesting wants faster repeat fights), and a future
  on-demand log-recall view, both build on top of what this amendment establishes rather than
  needing their own traversal model — unchanged in spirit from the original decision.
- No domain change: `eye/combat/`, `Battle`, `Generation` untouched. `eye/gui/scenes/combat.py`
  and `eye/gui/animation.py` (for the `loop` field) are the modules affected, plus
  `eye/gui/tuning.py` for the new constants.
