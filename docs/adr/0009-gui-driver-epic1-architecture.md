# 0009 — GUI driver, Epic 1: scaffolding and full minimal loop

**Status:** Accepted
**Date:** 2026-09-01

## Context

Combat (ADR 0001), exploration (ADR 0002), skill tree (ADR 0003), the composition root (ADR
0004), persistence (ADR 0005), and the TUI adapter (ADR 0006) are all complete: a fully tested
engine, already proven playable and fun end-to-end via `eye/tui/`. Nothing renders it with pygame
yet — `eye/main.py` is a disposable movement stub (a filled background, a WASD-steered circle),
explicitly called out as unrelated by ADR 0006. `pygame-ce`, `pygbag`, and `platformdirs` are
already project dependencies.

ADR 0008 (driver-owned battle stepping, Accepted the same day as this ADR) built `Battle.turn_phase`
specifically for a frame-based main loop to poll "what should happen right now," rather than
blocking synchronously the way the TUI's combat loop does — this Epic is the first real consumer
of that seam. ADR 0005 already resolved save/load for both runtime targets
(`default_save_store()` branches on `sys.platform == "emscripten"` for browser `localStorage` vs.
a caller-supplied desktop filesystem path), so this Epic has no persistence design work left, only
wiring, the same way the TUI wired it via `platformdirs`.

## Decision

- **Scope for this Epic is driver scaffolding plus every screen the full generational loop
  needs** (exploration, combat, skill tree, rebirth), all placeholder-drawn — not exploration
  alone. Screens are procedurally generated with random triggers (PROJECT_BRIEF.md §6);
  `EnemyEncountered` is one of them, so there is no way to build only an exploration screen
  honestly — hitting an enemy trigger has to go somewhere. Real combat-screen rendering (polished,
  animated, art-backed) deserves its own future epic, but *a* combat screen — however minimal —
  has to exist for exploration to be playable or testable at all in this one. This mirrors the TUI
  epic's own reasoning for shipping the whole loop at once rather than a narrower slice: here,
  what's being proven is that the scene/rendering architecture holds up across every screen type,
  not just one. Real art/sprites, animation, sound, the platformer-movement stretch goal (§6), and
  multi-Biome/multi-Strain content (§8, still open) are explicitly out of scope, deferred to later
  epics that plug into the seams below without touching scene structure.
- **New top-level package `eye/gui/`, same status as `eye/tui/`**: imports `Game`/`Generation`/
  `eye.persistence`, nothing imports back into it. Not named `eye/pygame/` — that would shadow the
  `pygame` import inside its own modules. `eye/main.py` stops being the movement stub and becomes
  the real entry point (async `main()`, same `asyncio.run(...)` / cooperative-yield shape it
  already has for pygbag); `make run`/`make serve` need no changes.
- **Module split:**
  ```
  eye/gui/
    scenes/
      exploration.py   # ExplorationScene
      combat.py         # CombatScene
      skilltree.py      # SkillTreeScene
    assets.py            # SpriteAtlas, SpriteKey, build_placeholder_atlas()
    widgets.py           # BuffIcon, SkillTreeLeaf protocols + placeholder implementations
    save.py              # save-path resolution + persist()/load_or_new() wrapper
    app.py               # window/clock, main loop, scene switching
  ```
  Each `Scene` implements a small protocol: `handle_event(event) -> None`,
  `update(dt) -> Scene | None`, `draw(surface) -> None`. `update()` returns the next `Scene` to
  switch to, already constructed, or `None` to stay — this is how a scene signals a transition;
  there's no separate callback or shared mutable "pending transition" field. `app.py` owns the
  pygame window and clock, the async main loop, and a single "current scene" reference: each frame
  it calls `current_scene.update(dt)` and, if the result isn't `None`, replaces `current_scene`
  with it before drawing. No generic scene stack — nesting never goes deeper than one level:
  `ExplorationScene.update()` returns a `CombatScene` on `EnemyEncountered`; `CombatScene.update()`
  returns a fresh `ExplorationScene` once the battle is resolved and the generation survived, or a
  `SkillTreeScene` if it didn't (see below); `SkillTreeScene.update()` returns a fresh
  `ExplorationScene` once `game.start_generation()` starts the next life.
- **`save.py` mirrors `eye/tui/save.py`**: `default_save_store()` plus `platformdirs` for the
  desktop path, no path needed under emscripten. Same trigger policy as the TUI — persist after
  every event that changes cross-generation state (`SessionEvent`s `SeedsMatured`/`SporesAwarded`,
  and the `SkillTreeEvent` `NodePurchased`), not only on quit.
- **Rendering is primitives now, behind a swappable asset seam for later.** `SpriteAtlas` wraps a
  `Mapping[SpriteKey, pygame.Surface]` with a single `get(key) -> Surface`. `SpriteKey` (a
  `StrEnum`) names only what this Epic actually renders as an entity/background — the player,
  `Strain.BRAMBLE`, the seed, turf, a per-screen background — not menu chrome, borders, or the
  action list, which stay plain `pygame.draw`/`pygame.font` calls in scene code, since there's no
  open question about what those look like later, only what color.
  `build_placeholder_atlas() -> SpriteAtlas` draws each key's primitive shape (a solid-color rect
  or circle) into its own freshly created `Surface` once at startup — marked as a placeholder the
  same way `tuning.py` constants are, so it's grep-discoverable as exactly what a future art epic
  replaces. Scenes take `atlas: SpriteAtlas` as a constructor parameter (the same DI convention
  already used for choosers and `random.Random`) and only ever call `atlas.get(key)` + `blit` for
  entities — never `pygame.draw` for one directly. A future art epic swaps in
  `build_art_atlas(assets_dir: Path)` (loading PNGs via `pygame.image.load(...).convert_alpha()`
  per key) at the one call site in `app.py` that constructs the atlas today; no scene changes.
- **A `Protocol`-based seam for compound widgets whose composition is still open:** buff/debuff
  display and skill-tree node display are both elements whose eventual composition (icon + text +
  state styling, in some combination not yet decided) is genuinely undecided — unlike a plain
  entity sprite, a single `Surface` swap won't be enough for these later. Mirrors `ActionChooser`
  (`eye/combat/ai.py`) and `SaveStore` (`eye/persistence/port.py`) — swappable implementation
  behind a stable interface, a pattern already established in this codebase:
  ```python
  class BuffIcon(Protocol):
      def render(self, surface: pygame.Surface, pos: pygame.Vector2) -> None: ...

  class SkillTreeLeaf(Protocol):
      def render(self, surface: pygame.Surface, rect: pygame.Rect, node: SkillNode, locked: bool) -> None: ...
  ```
  This Epic ships exactly one implementation of each — `TextBuffIcon` draws a buff/debuff's name
  as text, colored to distinguish buff from debuff; `TextSkillTreeLeaf` draws a node's name and
  cost as text, colored to distinguish locked from unlocked. Scenes take a factory function as a
  constructor parameter (same DI convention as
  the atlas) rather than constructing widgets themselves, so a future epic can swap the factory for
  one returning e.g. `SpriteBuffIcon(icon: Surface, label: str)` combining atlas art with text —
  no scene-code change. Deliberately *not* applied elsewhere: HP bars, the action menu, borders,
  and generic chrome stay plain draw calls, since there's no open composition question for those
  and the extra seam would be unjustified ceremony.
- **`CombatScene` is the first real consumer of `turn_phase`.** On construction, immediately after
  `generation.start_battle(encounter)` hands it the `Battle`, it calls `battle.start()` once
  (resolving the Lifespan Resonance meter-prefill, PROJECT_BRIEF.md §5.6) before entering the
  per-frame loop — mirroring the TUI's `play_battle` precedent; skipping this call would silently
  make Resonance a no-op in the GUI. Each frame it then reads `battle.turn_phase` and acts on it
  directly:
  - awaiting a player query → call `battle.query_player_turn()` once. This returns either
    `PlayerTurnNeedsAction` (cached for the round; the menu renders from it and the scene waits
    for input) or `PlayerTurnConcluded` (Wilty/Vegetative resolved the turn without one — its
    events are recorded for the recap and the scene proceeds straight to the next `turn_phase`
    read, no menu shown).
  - a chosen action arrives → call `battle.resolve_player_turn(action)`.
  - awaiting the enemy's turn → call `battle.resolve_enemy_turn()` automatically, no input needed.
  - `battle.is_over` → call `generation.finish_battle(battle)`, then branch on
    `generation.died` (the only path to 0 HP is combat, per ADR 0004 — exploration only heals):
    if `False`, return a fresh `ExplorationScene`; if `True`, call `game.end_generation(generation)`
    and return a `SkillTreeScene` instead — mirroring the TUI's `_play_generation`, which routes a
    dead generation straight to the skill-tree menu rather than back into exploration. Returning to
    `ExplorationScene` unconditionally here would soft-lock on a dead character, since
    `Generation.advance()` returns `[]` once `died` is true.
- **Input is keyboard-only for this Epic** — number/arrow keys select menu entries, mirroring the
  TUI's numbered-menu precedent. Mouse/click support is deferred, not blocking, and isolated
  entirely inside each scene's `handle_event()`, so adding it later touches no other scene or the
  app loop.
- **Tests run headless via `SDL_VIDEODRIVER=dummy`** (set before `pygame.init()`), the standard
  pygame CI-without-a-display pattern. Assertions target scene-transition state and the calls made
  into `Game`/`Generation`/`Battle` — which scene is active after an `EnemyEncountered` event,
  `finish_battle()`/`end_generation()` firing at the right point, `turn_phase` driving the right
  method — not pixel output, mirroring the TUI's structural-assertion approach over asserting on
  rendered content byte-for-byte. `SpriteAtlas`/`build_placeholder_atlas()` are unit-tested
  directly (right `SpriteKey`s present, `Surface`s of the expected size);
  `TextBuffIcon`/`TextSkillTreeLeaf` are tested for correct constructor state and that `render()`
  is callable without raising under the dummy driver, not pixel-asserted.

## Consequences

- A future art/animation/sound epic plugs into the seams established here — `build_art_atlas()`
  swapped in at `app.py`'s one atlas-construction call site, new `BuffIcon`/`SkillTreeLeaf`
  implementations swapped in at their factory call sites — with no scene-structure changes.
- Mouse/click input, the platformer-movement stretch goal (§6), and multi-Biome/multi-Strain
  content (§8) all remain open, each addable later without restructuring `eye/gui/` — input
  handling is isolated per-scene, and `SpriteKey` is extensible without changing `SpriteAtlas`
  itself.
- `eye/main.py`'s current movement-stub content is fully replaced; nothing in this Epic depends on
  it surviving.
- Full design rationale (the exploration-only vs. full-minimal-loop scoping question, and the
  reasoning behind the compound-widget seam) lived in a working spec during design that was not
  committed to this repository. This ADR is the durable record; per-component GitHub issues under
  the tracking Epic carry the implementation-level detail forward.
