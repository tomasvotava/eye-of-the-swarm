# 0010 — GUI driver: `GameDriver` split from `App`

**Status:** Accepted
**Date:** 2026-09-02

## Context

PR #135's review flagged that `eye/gui/scenes/exploration.py` and `combat.py` imported each other to
construct the scene each hands off to on a transition, closed only by a function-local deferred
import — tracked as issue #136. PR #140 fixed the import cycle: `Scene.update()` returned a
`SceneTransition` value (`EnterCombat`/`EnterExploration`/`EnterSkillTree`) instead of a
constructed `Scene`, and `app.py` became the only module importing every concrete scene,
resolving requests into instances via a `_resolve_transition()` match.

That fix was incomplete. It removed the *import* coupling but not the *policy* coupling:
`CombatScene._conclude()` still decided "not died → explore, died → skill tree" itself, and every
scene still threaded `game`/`atlas`/`save_store` through transition payloads regardless of whether
it used them directly — `ExplorationScene` carried a `save_store` it never touched, purely to hand
to the `CombatScene` it built. Review of PR #140 surfaced the underlying cause: `app.py` had no
persistent notion of "the current game" the way a driver should, so every scene had to carry that
state itself and pass it forward.

`eye/tui/`, which this GUI epic (ADR 0009) already treats as precedent throughout, already solves
this correctly and had done so since it was written. `eye/tui/combat.py::play_battle(console,
generation, encounter, input_source)` takes no `game` parameter and never decides what happens
after the battle — it runs the battle and returns. All of "what happens next" — `end_generation`,
`save.persist`, routing to the skill-tree menu vs. looping back into exploration — lives in
`eye/tui/app.py::_play()`'s outer loop, which holds `game`/`generation` as loop-scoped state and
checks `generation.died` itself once `_play_generation()` returns. `combat.py` and
`skilltree_menu.py` never import each other and never decide routing; the driver does.

Separately: this repo will need a splash/credits screen and a main menu before publication (author
credits, "new game"/"continue" entry points). `app.py`, as PR #140 left it, is hard-wired to boot
straight into the generational loop and already imports `Game`/`Generation`/`eye.persistence` to
do so — there is no seam for a top-level screen that isn't "play the game."

## Decision

- **New `GameDriver` (`eye/gui/game_driver.py`) owns the entire generational loop**, mirroring
  `eye/tui/app.py::_play()`/`_play_generation()`/`combat.py::play_battle()` combined into one
  frame-driven object: `self._game: Game`, `self._generation: Generation`, `self._save_store:
  SaveStore`, `self._atlas: SpriteAtlas`, and its own current inner scene (`Exploration`/`Combat`/
  `SkillTree`). It implements the same `Scene` protocol app.py already uses
  (`handle_pygame_event`/`update`/`draw`), so `app.py` treats it as just another top-level screen —
  it does not know, and does not need to know, that a `GameDriver` runs a generational loop inside
  itself.
- **Inner scenes shrink to exactly what they use for their own logic and drawing** — no scene holds
  a reference merely to forward it:
  - `ExplorationScene(generation, game, atlas)` — unchanged from PR #140; `game` is genuinely used
    for the matured-turf HUD icon.
  - `CombatScene(generation, encounter, atlas)` — drops `game` and `save_store` entirely, matching
    `play_battle`'s signature. `update()` on `battle.is_over` calls `generation.finish_battle(battle)`
    for the recap log (as before) and returns a bare `BattleConcluded()` with no payload and no
    win/death branch of its own.
  - `SkillTreeScene(game, atlas, on_purchase: Callable[[], None])` — drops the `SaveStore`-typed
    parameter for a plain callback, mirroring `eye/tui/app.py::_play()`'s own
    `skilltree_menu.run(..., on_purchase=lambda: save.persist(game, save_store))`. The scene no
    longer imports `eye.persistence` at all; it just invokes the hook after a purchase.
- **`GameDriver` owns the win/death/continue policy**, reading `self._generation.died` -- the same
  mutable `Generation` its inner `CombatScene` just operated on -- exactly mirroring `_play()`'s
  post-loop check:
  ```python
  def _resolve(self, transition: PlaySceneTransition) -> PlayScene:
      match transition:
          case EnterCombat(encounter=encounter):
              return CombatScene(self._generation, encounter, self._atlas)
          case BattleConcluded():
              if self._generation.died:
                  self._game.end_generation(self._generation)
                  save.persist(self._game, self._save_store)
                  return SkillTreeScene(self._game, self._atlas, on_purchase=self._persist)
              return ExplorationScene(self._generation, self._game, self._atlas)
          case Continue():
              self._generation = self._game.start_generation()
              return ExplorationScene(self._generation, self._game, self._atlas)
  ```
  `self._persist` is `lambda: save.persist(self._game, self._save_store)`, the same hook threaded
  into `SkillTreeScene`.
- **Two tiers, two transition mechanisms, each sized to the cycle it actually has to break.**
  `eye/gui/scene.py` keeps exactly one thing: the outer `Scene` protocol, back to ADR 0009's
  original shape (`update(dt) -> Scene | None`, a constructed scene or nothing) — the module still
  imports no concrete scene. This is sufficient at `app.py`'s level because there is no cycle there:
  `DevAssetViewerScene` and `GameDriver` are peer top-level screens picked once at construction
  (today; a future splash/menu screen joins the same set), never constructing each other. The inner
  cycle (`Exploration` ⟷ `Combat`) is real, so it keeps needing the request/resolve indirection from
  PR #140 — but that indirection (`PlayScene` protocol, `PlaySceneTransition` union, `EnterCombat`/
  `BattleConcluded`/`Continue`) now lives entirely inside `eye/gui/game_driver.py`, private to its
  one consumer, rather than being forced on `app.py` and every top-level screen regardless of
  whether they have a cycle to break.
- **`app.py` becomes fully domain- and persistence-agnostic.** It owns the pygame window/clock, the
  async main loop, the `SpriteAtlas` (still shared infrastructure any top-level screen might draw
  with), and picks the initial top-level `Scene` — `DevAssetViewerScene` or `GameDriver`. It stops
  importing `Game`/`Generation`/`eye.persistence`/`SaveStore` altogether; it only forwards the
  `save_store`/`rng` constructor arguments it already took into `GameDriver`'s constructor, exactly
  the way it already forwards `screen`/`clock` without interpreting them.
- **Building a menu/splash/credits screen is explicitly out of scope for this ADR** — this only
  builds the seam that makes `app.py` capable of hosting one later (any `Scene` implementation can
  already be swapped in as the initial or a returned top-level screen) without touching `GameDriver`
  or any inner scene. Mirrors ADR 0009's own deferral of the art epic: the seam ships now, the
  content ships later.

## Consequences

- Supersedes PR #140/issue #136's `app.py`-level `SceneTransition` design. Issue #136's original
  complaint (no scene module should import another to construct it) is still fully satisfied as a
  side effect: `ExplorationScene`, `CombatScene`, and `SkillTreeScene` remain mutually import-free,
  and `GameDriver` is the only module that imports all three.
- `eye.persistence`/`SaveStore` imports in `eye/gui/` are now confined to `game_driver.py`; no
  scene module imports them.
- A future splash/menu epic adds new top-level `Scene` implementations and wires `app.py` to start
  on one of them (and to transition into `GameDriver` on "New Game"/"Continue") without touching
  `GameDriver`'s internals or any inner scene -- the exact seam this ADR exists to establish.
- `GameDriver`'s tests (construction, routing on win/death/continue, persistence timing) replace the
  transition-focused tests PR #140 added to `test_app.py`; `test_app.py` goes back to testing pure
  scene-hosting mechanics (event forwarding, draw-on-step, swap-on-non-`None`) against a generic
  stub, with no domain knowledge.
