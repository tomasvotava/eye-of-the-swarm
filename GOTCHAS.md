# Gotchas

## 2026-09-09 - Placeholder atlas hides geometry bugs

A test asserted an icon's on-screen size and position, passed, and the real build still drew the
icon at half the screen's height.

`build_placeholder_atlas()` returns a 32x32 square for *every* key, and the `tmp_path` helpers in
the scene tests write 4x4 sprites. The shipped art is 210x210, and enemy frames are 64x64 against
the player's 32x32 — so a placeholder-backed test reproduces the player's geometry on both sides
and cannot see a sizing bug at all.

Anything asserting real size or position builds from `build_art_atlas(Path("eye/gui/sprites"))`.
Placeholder atlases are for behaviour, never for geometry.

## 2026-09-09 - `get_variant_set` returns the art unscaled

A bar icon blitted straight from `get_variant_set` covered a large part of the screen.

It hands back the raw `Surface` as loaded from disk — 210x210 for every shipped icon. Only
`SpriteIcon.render` (and `SpriteBuffIcon` through it) smoothscales to the box you ask for.

Route icons through `SpriteIcon`. Never blit a variant surface directly.

## 2026-09-09 - A new `SpriteKey` without a placeholder shape crashes at startup

Adding a key and expecting ADR 0011's per-key fallback to cover the missing art. It does cover
missing art — it does not cover a missing placeholder.

`build_art_atlas` calls `_build_placeholder_surface(key)` for *every* member of the enum, and that
indexes `_PLACEHOLDER_SHAPES[key]`. A key with no entry is a hard `KeyError` before the game draws
anything. `build_placeholder_atlas` iterates the map rather than the enum, so it fails later and
differently, which makes the two easy to confuse.

Add the `_PLACEHOLDER_SHAPES` entry in the same commit as the key.

## 2026-09-09 - `get_variant_set` is all-or-nothing

Adding a `BORDERED` member to `IconVariant` for symmetry, since there is clearly a bordered form.

`_resolve_named_set` raises `ValueError` if *any* member of the enum has no matching file. The
bordered form is the reserved `sprite.png`, not a `bordered.png`, so a `BORDERED` member would make
every call raise. The same all-or-nothing rule means a variant-less atlas raises too, which is why
`has_variant_set` exists.

`IconVariant` carries only the variants that exist as their own files. Guard with
`has_variant_set` before asking.

## 2026-09-09 - `Battle.is_over` can go back to False

Reasoning that nothing un-sets `is_over` once a combatant drops.

It is a computed property — `player.current_hp <= 0 or enemy.current_hp <= 0` — and `_revive()`
sets `current_hp = ADRENALINE_REVIVE_HP`. An Adrenaline revive flips it straight back.

Never cache it or build an argument on it being monotonic. Where it genuinely holds, the reason is
the caller's own control flow, not the flag.

## 2026-09-09 - Heals are clamped, damage-over-time is not

A GUI label read `+3 HP` while the bar beside it moved by 1, and a lethal Toxicity tick reported
negative HP.

The two ticks are asymmetric. `_tick_nourished` clamps at `max_hp` but still reports the nominal
`NOURISHED_HEAL_PER_TURN` in `HealApplied.amount`, so the amount overstates the change near full
health. `_tick_toxicity` subtracts with no floor at all, so `DotTicked.target_hp_after` goes
negative on a killing tick while the HP bar floors at empty.

Derive anything displayed from `*_hp_after` against the value already on screen, never from the
event's nominal `amount`/`damage`.

## 2026-09-09 - `HitReflected` reads backwards

Treating `.source` as the combatant taking the damage, the way it works in `HitLanded`.

`.source` is the Spiky Skin holder doing the reflecting. `.target` is the original attacker, now
taking the damage back. So the combatant a reflect happens *to* does not hold the effect that
caused it.

Anything drawn on `.target` must not claim they hold Spiky Skin — name the event, not the effect.

## 2026-09-09 - `ActionChosen` arrives after the choice, not before

Driving "whose turn is it" from `ActionChosen`, then finding it named the enemy throughout the
player's own menu.

`_resolve_swing` emits it, so it exists only once an action has been picked. For the whole window
where the player is choosing, the most recent `ActionChosen` is still the enemy's from last round.

Latch turn ownership at the `update()` branch that drives the turn, not from an event.

## 2026-09-09 - Colour-key tests must not key on a colour the scene paints

A card-fit test measured the drawn block as 11px narrower and 18px shorter than it really was, and
passed.

It keyed on black to find "undrawn" pixels, while the card's own backdrop panel is black at
alpha 200. The backdrop went unmeasured.

Fill with a sentinel colour nothing paints, and assert the measured rect is non-empty — an empty
rect is contained by any region and satisfies every containment check silently.

## 2026-09-09 - pre-commit stashes unstaged changes

A commit shipped without the fixes made during the review pass, despite the files being edited.

`pre-commit` stashes unstaged work while it runs. Staging before the review means the review's own
edits stay unstaged and never enter the commit.

Stage after the review pass, and confirm with `git show --stat` that the commit holds what you
think it does.

## 2026-09-12 - Source art doesn't always arrive as `.png`

A delivered Biome's background and props were `.jpg`, while the other two Biomes' were `.png`.

`build_art_atlas` only globs `*.png` (ADR 0011) — a `.jpg` sitting in a `SpriteKey` directory is
silently invisible to it, no error, just a placeholder as if the file weren't there at all.

Convert to `.png` when landing the art, before it goes under `eye/gui/sprites/` — not something the
loader should special-case. A source format conversion doesn't imply the art itself is complete:
converting a no-alpha `.jpg` to `.png` still has no alpha channel, it just renders as an opaque
rectangle now instead of failing to load at all.

## 2026-09-13 - pygbag's `ignoreDirs` needs a leading slash, or subdirectories still get packed

A `pygbag.ini` entry of `"tests"` (no leading slash) excluded the top-level `tests/` folder from
the archive, but every file inside `tests/persistence/`, `tests/combat/`, etc. still got packed.

pygbag's `filtering.py` matches each candidate folder two ways: `folder.match(block)` (true only
when the folder's own last path segment equals the pattern) and `fx.startswith(f"{block}/")`
where `fx` always starts with `/`. A bare `"tests"` never satisfies the second form, so only the
directory literally named `tests` at the walked root is rejected — everything nested under it
passes straight through.

Always write `ignoreDirs` entries as `"/tests"`, matching pygbag's own default list's style
(`/build`, `/.git`, …).

## 2026-09-13 - pygbag does not actually skip dot-directories by default

Assuming `pygbag .` (pointed at the repo root) would leave `.venv` alone the way it leaves `.git`
alone. It does not — a full `.venv` (including `pygame`'s own bundled examples/tests) got walked
into the packed archive.

`filtering.py` has a `if fx.startswith("."): continue` check that looks like a blanket dot-folder
skip, but `gathering.py` always builds `fx` as `Path("/").joinpath(...)`, so it starts with `/`,
never `.`. That check is dead code. Only directories named explicitly in the (non-configurable)
default `IGNORE` list — `/.git`, `/.github`, `/.mypy_cache`, etc. — are actually skipped; `/.venv`
is not among them.

List every dot-directory you need excluded explicitly in `pygbag.ini`'s `ignoreDirs`
(`/.venv`, `/.ruff_cache`, `/.pytest_cache`, …) — never rely on the dot prefix alone.

## 2026-09-13 - `eye/gui/*` needs `from __future__ import annotations` for the web build

A module-level constant (`_TEXT_COLOR: pygame.typing.ColorLike = "white"`) raised
`AttributeError: module 'pygame' has no attribute 'typing'` in the browser, despite working
natively and passing mypy. The same class of error later hit `pygame.Surface` and `pygame.K_1`
in different files, each only surfacing once the previous one was fixed.

This project targets Python 3.14, which defers annotation evaluation by default (PEP 649) — so
an annotation referencing anything not yet a real binding (a `TYPE_CHECKING`-only import, or a
`pygame.*` attribute pygame-ce's WASM build populates asynchronously after `import pygame`
returns) never actually gets evaluated natively. pygbag's browser runtime is CPython 3.12, which
has no such default, so the same annotation is evaluated eagerly and blows up.

Any module whose annotations reference a `TYPE_CHECKING`-only import or a `pygame.*` attribute
needs `from __future__ import annotations` as its first statement after the module docstring, if
it has one. Nothing in the toolchain catches a missing one — there's no 3.12 job, and mypy/ruff
both target 3.14.

## 2026-09-13 - a web-reachable module must not import a dependency it won't actually use there

`eye/persistence/save.py` called `platformdirs.user_data_dir(...)` unconditionally to build a
fallback save path, even though `eye/persistence/select.py::default_save_store` throws that path
away unread on `sys.platform == "emscripten"` in favor of `LocalStorageSaveStore`. That eager,
unnecessary call dragged `platformdirs` into the browser build's import graph, where pygbag
either has to be told about it upfront (a PEP 723 header in `main.py`) or it falls into pygbag's
reactive dependency installer — which hangs indefinitely rather than failing, the moment anything
reaches it, regardless of whether the underlying install itself succeeds.

Check `sys.platform` before computing anything a browser-reachable code path won't use, not just
before choosing what to do with it — an unused eager `import`/call is invisible right up until it
either needs pygbag's fragile install machinery or hangs it.
