# 0011 — Sprite asset pipeline & animation framework

**Status:** Accepted
**Date:** 2026-09-02

## Context

v2 (PROJECT_BRIEF.md §9) is presentation-layer work on top of the complete v1 engine. §9.9
anticipates real art landing incrementally through the `SpriteAtlas` seam (ADR 0009) but leaves
the actual pipeline unspecified. The first real delivery is a 5-frame player idle animation as a
160×32 spritesheet (32×32 frames) — `SpriteAtlas.get(key) -> Surface` (ADR 0009) has no way to
represent a multi-frame, time-driven sprite, only a single static image per key.

Hand-cutting every spritesheet the artist sends is a recurring, avoidable cost — pre-cutting only
earns its keep for irregular/packed atlases, and a uniform-grid spritesheet doesn't need it: a
manifest describing frame geometry plus one grid-slice pass at atlas-build time is strictly
simpler, adds no dependency (no Pillow), and produces no generated-file clutter to gitignore.
Building the atlas already happens once at process startup (`app.py`), so "slicing at load time"
costs nothing perceptible.

Separately, some sprites need multiple *state-driven*, non-animated variants rather than frames —
e.g. a skill-tree leaf icon with locked/owned/available/active states (§9.6, not built by this
ADR). Conflating that with time-driven animation would be wrong: one is driven by elapsed time,
the other by external game state (purchase status, cursor focus).

`pygbag`'s packer (`pygbag/app.py::set_args`, `pygbag/pack.py::archive`) only walks and bundles the
folder given on its command line — `make serve` invokes `pygbag eye`, so only `eye/`'s contents
reach the web build. A top-level `assets/` directory would silently be excluded from it.

## Decision

- **All sprite sources live under `eye/gui/sprites/`** (not repo-root), so desktop and pygbag web
  builds see identical contents.
- **One directory per `SpriteKey`, named files inside it — never one directory per state/variant
  combination** (avoids Windows path-length growth for entities with several variants):
  ```
  eye/gui/sprites/
    player/
      idle.png   idle.json      # .json sibling present -> sliced as an animation clip
      walk.png   walk.json      # ships as a byte-for-byte duplicate of idle.* for now
    seed/
      sprite.png                 # reserved name: no variants, just the one static sprite
    skill_nasty_tendrils/
      active.png                 # no .json sibling -> static named variants, one file each
      locked.png
      available.png
  ```
  Rule: a `.json` sibling next to `<name>.png` means "slice this as an animation clip"; its
  absence means "load as one static named variant." `sprite.png` is the reserved name for the
  no-variants case, keeping today's static keys (SEED, TURF, BACKGROUND, UNKNOWN, and BRAMBLE
  until it gets animated art) on an unchanged `SpriteAtlas.get(key)`.
- **Manifest is flat — one spritesheet is one clip, single row, left-to-right:**
  `{"frame_width": 32, "frame_height": 32, "frame_count": 5, "fps": 8}`. A manifest that doesn't
  evenly divide the sheet's actual width is a startup-time `ValueError` — an authoring/pipeline
  bug, not a runtime condition to degrade around. The loader calls `.convert_alpha()` on the
  loaded sheet immediately after `pygame.image.load()`, before slicing, so every sliced-out frame
  subsurface inherits the fast blit format.
- **New `eye/gui/animation.py`, generic over a *per-entity* state enum — there is no shared
  `AnimationState` enum spanning every animated entity in the game:**
  ```python
  @dataclass(frozen=True, slots=True)
  class AnimationClip:
      frames: tuple[pygame.Surface, ...]
      frame_duration: float  # seconds per frame

  class Animator[TState: StrEnum]:
      def __init__(self, clips: Mapping[TState, AnimationClip], initial_state: TState) -> None:
          missing = [member for member in type(initial_state) if member not in clips]
          if missing:
              raise ValueError(f"missing animation clips for states: {missing}")
          ...

      def set_state(self, state: TState) -> None: ...   # resets frame/elapsed on actual change
      def update(self, dt: float) -> None: ...             # advances/wraps frames
      def current_frame(self) -> pygame.Surface: ...

  # consumer side, e.g. eye/gui/scenes/exploration.py:
  class PlayerAnimationState(StrEnum):
      IDLE = "idle"
      WALK = "walk"

  self._player_animator: Animator[PlayerAnimationState] = Animator(
      atlas.get_animation_set(SpriteKey.PLAYER, PlayerAnimationState),
      initial_state=PlayerAnimationState.IDLE,
  )
  ```
  Each animated entity defines its own complete `StrEnum` of the states *it* has — `PlayerAnimationState`
  with `IDLE`/`WALK`, and, whenever an enemy Strain gets animated in a future epic, e.g. a
  `BrambleAnimationState` with whatever states that Strain actually needs — rather than every
  entity drawing from one shared taxonomy. A single shared `AnimationState` enum plus a
  separately-declared `required_states: frozenset[...]` parameter was considered and rejected: that
  shape asks a caller to redeclare, by hand, a subset it could instead just *name* by picking its
  own enum type, and it can't stop the shared enum itself from accumulating every entity's states
  in one place. With a per-entity enum, `TState` (bound to `StrEnum`, not bare
  `str` — the bound needs to be iterable so the exhaustiveness check below can walk every member)
  *is* the required-state declaration: `Animator.__init__` iterates `type(initial_state)` and
  raises `ValueError` if `clips` is missing a clip for any of its members, at construction time —
  catching missing art on disk (a typo'd manifest filename, forgotten art delivery) the moment an
  entity is constructed rather than lazily the first time a rarely-triggered state (an exotic
  attack that might not roll for many playtests, per PROJECT_BRIEF.md §5.7's `T^k`-weighted action
  selection) is actually requested. `set_state(state: TState)` accepting only `PlayerAnimationState`
  members is then just an ordinary generic-type constraint, not a separate narrowing mechanism —
  mypy (already strict in this project) rejects an out-of-enum `set_state()` call before the code
  ever runs, with no extra `Literal[...]` alias needed at the call site.

  No `GameObject`/`AnimatedSprite` wrapper class is introduced. Only the player is animated in
  this Epic, so a wrapper for one consumer would be premature; the owning scene holds
  `self._player_animator: Animator[PlayerAnimationState]` directly and blits `current_frame()`
  itself. Worth extracting once a second animated entity creates real duplication.
- **`SpriteAtlas` (`eye/gui/assets.py`) gains two accessors alongside the unchanged `get(key)`:**
  `get_animation_set(key: SpriteKey, state_type: type[TState]) -> Mapping[TState, AnimationClip]`
  — internally the atlas holds each key's loaded clips keyed by raw string name (whatever the
  directory scan produced), and this method maps each `state_type` member to
  `raw[member.value]`, raising `ValueError` for any member with no corresponding file; and a
  `get_variant_set(key: SpriteKey, variant_type: type[TVariant]) -> Mapping[TVariant, Surface]`
  *contract*, mirroring `get_animation_set`'s per-consumer-enum shape for static named variants
  (e.g. a future `SkillLeafVisualState` enum with `LOCKED`/`AVAILABLE`/`ACTIVE` members), that is
  not built or wired to any consumer by this ADR — nothing needs it yet; §9.6's skill icons are
  its first real consumer, in a future epic.
- **New `build_art_atlas(assets_dir: Path) -> SpriteAtlas`, resolving per-key, not
  all-or-nothing:** for each `SpriteKey`, a missing `assets_dir / key.value` directory falls back
  to today's placeholder shape (`_PLACEHOLDER_SHAPES`, unchanged); a `sprite.png` inside it loads
  as a static `Surface`; `<name>.json` files inside it build the raw string-keyed clip mapping
  `get_animation_set` resolves against a caller's enum. BRAMBLE/SEED/TURF/BACKGROUND stay exactly
  as placeholder as they are today while only PLAYER gets real art in this Epic — each future art
  delivery drops in independently, per §9.9's "placeholder art swappable through that seam"
  intent. `app.py`'s one atlas-construction call site swaps `build_placeholder_atlas()` for
  `build_art_atlas(Path("eye/gui/sprites"))`.
- **`DevAssetViewerScene` (ADR 0009) gains animation preview**, ticking the `Animator` for
  animated keys — a concrete, visual proof of the pipeline, tested the same structural way as
  today (callable under `SDL_VIDEODRIVER=dummy`, not pixel-asserted).

## Consequences

- A future art epic for any other entity (enemy Strains, backgrounds, skill icons) drops sprite
  files into `eye/gui/sprites/<key>/` and gets real art with no atlas or scene-code change, per
  key, independently of every other key's art status.
- `get_variant_set` remains an open contract until §9.6 (skill icon presentation) actually
  consumes it — no code exists for it yet.
- Each animated entity's own state enum grows (a `BrambleAnimationState.ATTACK`, say) only when a
  concrete consumer needs a concrete new state with real art behind it, not speculatively — and
  growing one entity's enum never touches any other entity's.
- ADR 0012 (screen-walking movement) is the first real consumer of `Animator`/`get_animation_set`,
  and is blocked on this ADR's implementation landing first.
