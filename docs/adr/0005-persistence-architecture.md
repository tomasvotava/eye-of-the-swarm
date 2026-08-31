# 0005 — Persistence architecture

**Status:** Accepted
**Date:** 2026-08-31

## Context

Combat (ADR 0001), exploration (ADR 0002), skill tree (ADR 0003), and the composition root
(ADR 0004) are all complete. `Game` (`eye/session/game.py`) owns everything that crosses
generation boundaries — a `SkillTree` (purchased nodes, spore balance) and
`matured_turf_positions` — but holds it in memory only. ADR 0004 named this gap explicitly in its
Consequences: "A future persistence epic owns: serializing/deserializing `SkillTree`'s
purchased-node set and spore balance, and `Game`'s `matured_turf_positions`, across process
restarts." This ADR is that epic's design.

The game ships to two runtime targets: a desktop Python process and a pygbag/Pyodide WASM build
running in the browser. `sys.platform == "emscripten"` is how pygbag signals the browser runtime;
under it, the (pygbag-shimmed, not stdlib) `platform` module exposes `platform.window`, giving
access to the browser's JS `window` object and, through it, `localStorage.getItem`/`.setItem`.
Outside emscripten, `platform.window` doesn't exist — code must branch on `sys.platform`
explicitly rather than duck-type. This means the two targets need genuinely different storage
adapters, which is exactly what the DI pattern already used throughout this codebase (choosers,
`random.Random`, `ActionChooser` as constructor parameters) is suited for.

## Decision

- **Scope for this epic is `Game`-level state only** — `SkillTree.purchased_nodes` /
  `spores_available`, and `Game.matured_turf_positions`. Mid-life `Generation` state (current
  screen, HP, active effects, an in-progress `Battle`) is explicitly **not** persisted. Death is
  the game's own natural checkpoint (PROJECT_BRIEF.md §4/§5.5 — "not you died and respawned, you
  are the next individual"); losing an in-progress run to a tab close or crash is consistent with
  that framing, not a gap to close. This also keeps the epic's surface small: no need to serialize
  `Character`, `ExplorationRun`, or mid-`Battle` `Combatant` state.
- **This epic delivers a port, a codec, and two adapters — fully tested in isolation — and
  nothing else.** It does not wire save-triggering into `eye/session/`, and it does not touch
  `main.py` (still a pygame stub with no real composition root or app loop to wire into yet).
  `Game`/`SkillTree` stay I/O-free, matching "domain aggregates don't do I/O" — a driver (the
  future UI/rendering epic's main loop) is responsible for calling `store.save(encode(game))`
  after whatever `SessionEvent`s it decides warrant a save (e.g. `SeedsMatured`, `SporesAwarded`,
  `NodePurchased`). Same "domain/orchestration first, adapters later" sequencing already used for
  combat → exploration → skill tree → composition root.
- **New top-level package `eye/persistence/`**, structurally the same status as `eye/session/`:
  allowed to import `Game`/`SkillTree` (to read state for encoding), but no domain package ever
  imports back into it. Pygame-free; the one emscripten-only import (`platform`) is deferred to
  inside the selection factory's function body, not module-level, so importing `eye.persistence`
  never fails under desktop CPython without pygbag installed.
  ```
  eye/persistence/
    port.py                    # SaveStore Protocol
    codec.py                   # GameSnapshot + encode()/decode()
    adapters/
      filesystem.py            # FilesystemSaveStore
      local_storage.py         # LocalStorageSaveStore + JSStorage Protocol
    select.py                  # default_save_store() factory
  ```
- **`SaveStore` port is synchronous, single-slot:**
  ```python
  class SaveStore(Protocol):
      def load(self) -> str | None: ...   # None = no save yet
      def save(self, data: str) -> None: ...
  ```
  Synchronous because `localStorage` is a blocking JS property access (unlike IndexedDB) — no
  `asyncio` needed at the port level; reconciling a blocking call with pygbag's cooperative-yield
  main loop is the same kind of adapter-side concern ADR 0004 already left to a future UI epic for
  `ActionChooser`. Single implicit slot — the brief has no multi-save-slot UI, so the port takes no
  `key` parameter; a `key`/namespace, where an adapter needs one, is an adapter constructor
  argument instead.
- **Codec is a plain dataclass plus two pure functions**, decoupled from `Game`/`SkillTree`
  themselves:
  ```python
  @dataclass(frozen=True, slots=True)
  class GameSnapshot:
      schema_version: int
      spores_available: int
      purchased_nodes: frozenset[SkillNodeId]
      matured_turf_positions: tuple[int, ...]

  def encode(game: Game) -> str: ...
  def decode(data: str, catalog: Iterable[SkillNode]) -> GameSnapshot: ...  # raises SaveDataError on malformed/unknown-version/unknown-node data
  ```
  `schema_version` is written (starts at `1`) but only that version is understood in v1 —
  `decode()` raises rather than attempting a migration; no migration framework exists yet and
  isn't built speculatively. `decode()` validates JSON shape (required fields, types, known enum
  values) and that each purchased node exists in an injected `catalog: Iterable[SkillNode]` —
  matching the resolver-function convention already established in `eye/skilltree/resolve.py`
  (`resolved_stats(base, tree, catalog)` and friends): `decode()` takes `catalog` as a required
  parameter with no default, so the codec doesn't reach into `eye.skilltree.catalog.CATALOG`
  itself — the caller injects it, the same way callers of the skilltree resolvers already do. A
  syntactically well-formed but nonexistent node (valid enum names, valid int tier, but no such
  node in the injected catalog — e.g. one renumbered or removed since the save was written) raises
  `SaveDataError` rather than decoding successfully and silently granting credit for it once
  reconstituted into a `SkillTree` (see the direct-reconstitution decision below). `decode()` does
  not check that purchased nodes form a valid prerequisite chain — that stays out of scope,
  matching v1's existing "no defensive validation" posture elsewhere (e.g. no cleanse/dispel
  mechanic) and is deliberately punted, not overlooked — see Consequences.
- **`SkillTree.__init__` gains a `purchased_nodes: Iterable[SkillNodeId] = ()` parameter**,
  mirroring how `Game.__init__` already accepts `matured_turf_positions` directly rather than
  replaying history. Considered and rejected: persisting the ordered purchase history and
  replaying it through `SkillTree.purchase()` on load — rejected because it requires storing
  purchase *order* (not just the final set) and re-resolving each `SkillNodeId` against the
  *current* `CATALOG`, which breaks the moment a node is renamed or removed between game versions.
  Direct reconstitution also makes a genuine `Game → encode → decode → reconstruct` round-trip
  test possible within this epic, which is what motivated including this small, targeted change to
  a domain package (`eye/skilltree/`) inside a persistence epic rather than treating it as
  out-of-scope.
- **Adapters:**
  - `FilesystemSaveStore(path: Path)` — `load()` returns `None` on `FileNotFoundError`; `save()`
    writes atomically (temp file + `os.replace`) so a crash mid-write can't corrupt the save file —
    a recurring-class risk worth closing once rather than leaving as a latent bug.
  - `LocalStorageSaveStore(storage: JSStorage, key: str)` — `JSStorage` is a small Protocol
    (`getItem`/`setItem`) matching the subset of the Web Storage API this needs. The adapter takes
    the storage object as a constructor parameter rather than importing `platform` itself, so it's
    unit-testable under plain CPython/pytest with a fake, without pygbag installed.
- **Selection factory takes the filesystem path as an optional parameter, required only when it's
  actually needed:**
  ```python
  def default_save_store(filesystem_path: Path | None = None) -> SaveStore:
      if sys.platform == "emscripten":
          import platform
          return LocalStorageSaveStore(platform.window.localStorage, key="eye-of-the-swarm-save")
      if filesystem_path is None:
          raise ValueError("filesystem_path is required outside emscripten")
      return FilesystemSaveStore(filesystem_path)
  ```
  Resolving a real default location (XDG config dir on Linux, `%AppData%\Roaming` on Windows,
  `~/Library/Application Support` on macOS, or something simpler like a cwd-relative path) is
  deliberately left to whichever future epic calls this — it's a UI/deployment concern, not a
  storage-format or platform-detection one, and this epic has no basis yet for picking a
  convention it can't exercise end-to-end. Making the parameter required unconditionally was
  considered and rejected: under emscripten, "filesystem path" isn't a concept the caller should
  have to invent a meaningless value for just to satisfy the signature. The requirement moves from
  the type signature to a runtime guard clause instead — the same trade `Generation`/`Game`
  already make for their own preconditions (`RuntimeError` on misuse rather than encoding the
  constraint in types).

## Consequences

- A future UI/rendering epic owns: calling `default_save_store()` (or constructing an adapter
  directly) with a real filesystem path, deciding when to call `save()`/`load()` against
  `Game`/`SkillTree`, and deciding what happens on a `SaveDataError` (start fresh with a warning,
  surface an error to the player, etc.) — this epic only defines that the error is raised, not how
  it's handled.
- No save-data migration framework exists. If `SkillNode`s or `GameSnapshot`'s shape change later,
  a save written under `schema_version: 1` fails to `decode()` outright rather than upgrading —
  acceptable for a jam-scale v1, but the first breaking change to persisted shape needs its own
  ADR addendum or a new ADR for a migration strategy. This now also covers `CATALOG` drift: a save
  referencing a node renamed or removed since it was written fails `decode()` for the same reason,
  not just a `schema_version` bump.
- Mid-life run state (current screen, HP, active effects, an in-progress `Battle`) is never
  persisted by this design. If a future decision reverses that (e.g. players complain about losing
  progress on an accidental tab close), it's new scope — serializing `Character`/`ExplorationRun`/
  `Combatant` markedly increases surface (in particular, an in-progress `Battle` has no obvious
  "safe to snapshot" point mid-round) and deserves its own design pass, not a bolt-on here.
- Full design rationale (rejected alternatives, package-layout reasoning) lived in a working spec
  during design that was not committed to this repository. This ADR is the durable record;
  per-component GitHub issues carry the implementation-level detail forward.
