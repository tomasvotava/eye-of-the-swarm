# 0017 — Menu, save slots, and settings

**Status:** Accepted
**Date:** 2026-09-13

## Context

The game currently has no menu: `App._initial_scene()` (`eye/gui/app.py`) boots straight into
`GameDriver`, which resolves a single implicit save via `save.load_or_new()`
(`eye/persistence/save.py`) — `app.py`'s own module docstring already names this as the seam ("a
future splash/menu epic adds screens here without touching `App`"). Submission is tomorrow and the
jam entry needs a real front door: New Game/Continue across 3 save slots, a Settings screen
(combat-animation speed now, window scale as a stretch item), and a Credits screen.

ADR 0005 designed `SaveStore` as deliberately single-slot ("the brief has no multi-save-slot UI, so
the port takes no `key` parameter"). That epic is closed and delivered — this ADR doesn't rewrite
it, and the `SaveStore` Protocol itself (`load() -> str | None`, `save(data: str) -> None`) is
unchanged. What changes is the layer above it: `default_save_store()` and `eye/persistence/save.py`
gain a namespace concept so the same port/adapters serve three independent game slots plus one
global settings blob, instead of one implicit file/key.

## Decision

- **`default_save_store` takes a `namespace: str` instead of assuming one fixed key**:
  ```python
  def default_save_store(namespace: str, filesystem_path: Path | None = None) -> SaveStore:
      if sys.platform == "emscripten":
          import platform
          return LocalStorageSaveStore(platform.window.localStorage, key=f"eye-of-the-swarm-{namespace}")
      if filesystem_path is None:
          raise ValueError("filesystem_path is required outside emscripten")
      return FilesystemSaveStore(filesystem_path)
  ```
  `FilesystemSaveStore`/`LocalStorageSaveStore` themselves don't change — they already take a path
  or key as a constructor argument (ADR 0005); only the thing that picks that path/key gains a
  namespace. This keeps the port and both adapters exactly as delivered.
- **`eye/persistence/save.py` adds slot/settings helpers**, alongside the existing
  `load_or_new`/`persist`:
  ```python
  def store_for_slot(slot: int) -> SaveStore:            # slot in {1, 2, 3}
      return default_save_store(f"save-{slot}", _default_save_path(f"save-{slot}"))

  def settings_store() -> SaveStore:
      return default_save_store("settings", _default_save_path("settings"))

  def _default_save_path(namespace: str) -> Path:
      return Path(platformdirs.user_data_dir(_APP_NAME)) / f"{namespace}.json"

  def peek(save_store: SaveStore) -> GameSnapshot | None:
      raw = save_store.load()
      return None if raw is None else decode(raw, CATALOG.values())   # SaveDataError propagates
  ```
  `peek()` exists for the menu to read a slot's status without constructing a `Game` — it lets
  `SaveDataError` bubble rather than swallowing it the way `load_or_new()` does, because the menu
  needs to *tell the player* a slot is corrupt (see below), not silently start fresh.
  `default_store()` (used only by the TUI, which has no slot picker) becomes
  `store_for_slot(1)` — the TUI always plays slot 1, unchanged in practice.
- **New `eye/persistence/settings.py`**, structurally parallel to `codec.py` but independent of
  `Game`/`SkillTree`:
  ```python
  @dataclass(frozen=True, slots=True)
  class SettingsSnapshot:
      schema_version: int
      combat_speed_multiplier: float

  def encode_settings(settings: SettingsSnapshot) -> str: ...
  def decode_settings(data: str) -> SettingsSnapshot: ...   # raises SaveDataError, same posture as codec.py
  ```
  Stored via the same `SaveStore` port/adapters as game saves, under the `"settings"` namespace —
  one global blob, not per-slot, since window scale/combat speed are player preferences, not game
  progress. A stretch window-scale setting (see below) is an additive field on this snapshot, not a
  schema change requiring its own ADR revision.
- **Menu slot display**: for each of the 3 slots, the menu calls `peek(store_for_slot(n))` and
  shows one of:
  - **Empty** — `peek()` returned `None`. Action offered: **New Game**.
  - **Corrupt** — `peek()` raised `SaveDataError`. Shown distinctly from Empty so the player isn't
    surprised, but the only action offered is still **New Game** — choosing it drives the same
    `GameDriver`/`load_or_new()` path, which already treats undecodable data as "start fresh" (ADR
    0005). The menu adds no new overwrite/repair logic of its own.
  - **Valid save** — shown as spores available (`GameSnapshot.spores_available`) and progression
    (`max(GameSnapshot.matured_turf_positions, default=0)` — the same "furthest matured position"
    expression `Game.start_generation()` already uses for the spawn screen, reused rather than
    inventing a second progress metric). Action offered: **Continue**.
  - **Deliberately out of scope**: overwriting a slot that already has a valid save (starting a
    *new* game over an existing one). Not offered in v1 — keeps the menu's action model to one
    button per slot instead of a destructive-confirmation flow, matching this project's existing
    "no defensive validation/dispel-style mechanics" posture elsewhere. If wanted later, it's a
    small additive follow-up (a confirm dialog before calling `store.save()` on a fresh `Game`),
    not a redesign.
- **`App`'s initial scene is `TitleScene(MenuScene(atlas, rng, audio))`**, replacing today's
  direct-to-`GameDriver` boot — the seam `app.py`'s docstring already reserved, with one addition
  to the original design: a `TitleScene` ahead of `MenuScene`, not `MenuScene` directly. A static
  screen — "The Eye of the Swarm" in the `buse` font over a smaller "Press Enter to continue" in
  `ithaca` (the footer, matching every other scene's own footer font) — and `K_RETURN`, not any
  `KEYDOWN`, hands off to the `MenuScene` it was constructed with, mirroring `CreditsScene`'s
  existing `next_scene`/`back_scene` constructor pattern. "Any key" was the original design and
  proved too lenient in playtesting: some OS/window-manager window operations (a fullscreen
  toggle) deliver a synthetic keydown that skipped the screen outright (GOTCHAS.md). The `EYE_DEV_ASSET_VIEWER` escape hatch is
  unaffected: it still short-circuits straight to `DevAssetViewerScene`, bypassing both screens.
  Both `TitleScene` and `MenuScene` fit `App`'s existing `Scene` protocol
  (`update(dt) -> Scene | None`) without any change to `App` itself: picking a slot's action
  constructs and returns a
  `GameDriver(atlas, rng, audio, save_store=store_for_slot(n), combat_speed_multiplier=settings.combat_speed_multiplier)`
  the same way any other scene transition already works.
- **`MenuScene` gains two more actions, `OPEN_SETTINGS`/`OPEN_CREDITS`** (`K_s`/`K_c`), returning
  `SettingsScene(self)`/`CreditsScene(self)` — both scenes already existed (#260/#255) and already
  took a `back_scene` for exactly this handoff, but nothing wired `MenuScene` to either until this
  addition. Returning `self` rather than a fresh `MenuScene` means the slot cursor position (and
  the slot views themselves) survive a round trip through Settings or Credits unchanged.
- **`GameDriver` and `CombatScene` both gain a `combat_speed_multiplier: float = 1.0` constructor
  parameter.** `GameDriver` threads it into every `CombatScene(...)` it constructs. `CombatScene`
  divides its `eye/gui/tuning.py` `BATTLE_*` phase/tween/hold durations by it when building
  `Phase`s (ADR 0013) — a higher multiplier plays faster. This is GUI-only pacing, the same
  category of change ADR 0013 already scoped as "how `CombatScene` walks through and displays one
  call's events," not a domain change.
- **Settings is also reachable in-game, from `ExplorationScene`, via Escape.** A new
  `OpenSettings` member of `PlaySceneTransition` (`eye/gui/play_scene.py`) carries the request.
  `ExplorationScene` raises it only while the player is idle (`RESOLVED`/`AT_ENTRY`) with no card
  or narration up, and never from the keypress that dismisses narration. `GameDriver.update()`
  intercepts it before `_resolve()` and returns `SettingsScene(self, on_change=...)` to `App`: an
  outer-level swap, the same mechanism `MenuScene` uses. `GameDriver` keeps its inner scene as is,
  frozen while Settings is up because nothing updates it; ambient music keeps playing. Combat and
  the skill tree do not open Settings.
- **`SettingsScene` takes an optional `on_change: Callable[[SettingsSnapshot], None]`**, called
  after every persisted change. `GameDriver` uses it to update its combat-speed multiplier, so the
  next `CombatScene` it constructs plays at the new speed. No `CombatScene` exists while Settings
  is open, since only exploration opens it.
- **Window-scale setting.** A `WindowScale` StrEnum (`AUTO`/`X1`/`X2`/`X3`/`X4`/`FULLSCREEN`) in
  `eye/persistence/settings.py`, stored as `SettingsSnapshot.window_scale` (default `AUTO`) and
  encoded as its string value. A blob without the key decodes as `AUTO`, so `schema_version`
  stays 1; an unrecognised value raises `SaveDataError`, which `load_settings()` already turns
  into all-default settings. `AUTO` is the size SDL picks for the `SCALED` window at boot, i.e.
  the behaviour before this setting existed.
  - Applied by `eye/gui/window.py` through `pygame.Window.from_display_module()`: `set_mode()`
    cannot choose a `SCALED` window's scale, but resizing the display module's `Window` can,
    while the logical surface stays 640x480. `run()` applies the saved scale right after the
    first `set_mode()`, so the window briefly appears at the `AUTO` size first. The Settings
    scene applies it again on every change. Leaving `FULLSCREEN` calls `set_windowed()` before
    resizing, and the window is recentred after each resize.
  - `Xn` options larger than the desktop (`pygame.display.get_desktop_sizes()`) are not offered.
  - Under emscripten the browser owns the canvas size: the Settings scene hides the window row
    and applying a scale is a no-op.
  - Manual window resizing by the OS/user is not tracked or reconciled.

## Consequences

- `eye/persistence`'s public surface grows by one parameter (`namespace` on
  `default_save_store`) and five functions (`store_for_slot`, `settings_store`,
  `narration_store_for_slot`, `peek`, `load_settings`) — no change to the `SaveStore` Protocol or
  either adapter, so ADR 0005 stands as written; this ADR only revises how a `SaveStore` gets
  picked, not what one is. `LocalStorageSaveStore`/`FilesystemSaveStore` gain no new constructor
  parameters.
- Save files/keys move from one implicit location to three (`save-1`/`save-2`/`save-3`) plus
  `settings` — a save written before this Epic (single implicit slot) has no automatic migration
  path into slot 1. Given the jam timeline and that no external save data exists in the wild yet,
  this is accepted without a migration shim.
- A corrupt slot's only recovery path is overwriting it via New Game — there is no repair or
  partial-recovery attempt, consistent with `GameSnapshot.decode()`'s existing all-or-nothing
  validation (ADR 0005).
- `CombatScene`'s phase-duration math now depends on an injected multiplier rather than reading
  `eye/gui/tuning.py` constants as fixed values directly — any future per-phase-kind speed tuning
  builds on this seam rather than re-threading a new parameter.
- `GameDriver` takes the multiplier at construction (from `MenuScene._confirm()`) and updates it
  through `SettingsScene`'s `on_change` when Settings is opened in-game. A `CombatScene` keeps the
  multiplier it was built with, which is safe only because Settings can't be opened mid-battle;
  opening it from combat later would need the scene to accept a live value.
- `pygame.Window.from_display_module()` is deprecated in pygame-ce 2.5.8 (it emits a
  `DeprecationWarning`), yet it is the only way to resize a `SCALED` display-module window.
  Accepted risk: `eye/gui/window.py` is its single caller and suppresses the warning there, so a
  pygame-ce release that removes it needs a fix in that one module.
