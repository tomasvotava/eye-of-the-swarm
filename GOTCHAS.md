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

## 2026-09-13 - annotations still need `from __future__ import annotations`

A module-level constant (`_TEXT_COLOR: pygame.typing.ColorLike = "white"`) raised
`AttributeError: module 'pygame' has no attribute 'typing'` in the browser, despite working
natively and passing mypy. The same class of error later hit `pygame.Surface` and `pygame.K_1`
in different files, each only surfacing once the previous one was fixed.

Native now targets 3.12, matching pygbag's browser runtime, so both eagerly evaluate
annotations (no PEP 649). An annotation referencing a `TYPE_CHECKING`-only import, a `pygame.*`
attribute pygame-ce's WASM build populates asynchronously after `import pygame` returns, or a
not-yet-bound forward reference to a name defined later in the same module still needs
`from __future__ import annotations` as the module's first statement after its docstring.

ruff (target-version now `py312`) catches the forward-reference case as F821. It cannot catch the
`pygame.*` late-population case — `pygame.typing`/`pygame.Surface` are real, resolvable names
natively, so nothing short of running in the browser surfaces that one.

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

## 2026-09-13 - `GameDriver`'s boot screen keys off whether a save loaded, not whether it decoded

Choosing "New Game" on a save slot with corrupt data boots into the skill-tree screen with 0
spores and nothing purchasable, instead of a fresh exploration run.

`GameDriver.__init__` sets `had_existing_save = self._save_store.load() is not None` before calling
`save.load_or_new()`, which falls back to a fresh `Game` on undecodable data (ADR 0005) — but
`load()` already returned the corrupt raw string, so `had_existing_save` is `True` regardless. The
boot-scene choice and the save-decoding fallback disagree with each other.

Fixing it means deriving `had_existing_save` from decodability (e.g. via `save.peek()`), not from
whether `load()` returned anything — out of scope for whatever change surfaces it; file a follow-up
rather than patching it inline.

## 2026-09-14 - No matured turf means `distance_to_nearest_matured_turf` is `inf`, not "close"

`FIRST_PROXIMITY_FALLOFF`/`FIRST_METER_FULL` narration cannot fire during a generation that has no
matured turf yet -- including every brand-new save's entire first life -- and that is correct, not
a bug to "fix" by loosening the guard back up.

`ExplorationRun.distance_to_nearest_matured_turf` returns `math.inf` when `_matured_turfs` is empty
(no turf has matured this generation). `distance_falloff_scale(inf, ...)` is `0.0`, so the player's
meter-fill rate is genuinely scaled to zero for that whole life -- the meter can never reach
capacity, so `FIRST_METER_FULL` never has a real occasion to fire. `FIRST_PROXIMITY_FALLOFF`
excludes the `inf` case on purpose (`math.isfinite(distance)` in `exploration.py`) because "you've
ventured too far from home" is a lie on turn one, before the player has taken a step -- re-including
`inf` reintroduces that exact bug.

Both triggers work as intended from generation 2 onward, once a real matured turf gives a finite
distance to walk away from.

## 2026-09-14 - Hiding an announcement behind narration isn't the same as pausing it

`CombatScene._draw_announcement` gained a guard to stop it drawing over an active narration
overlay, and a real battle then lost its "You lose!" banner and an effect card entirely -- neither
was ever seen, on any frame.

`_announcement`'s lifetime is driven by a `Phase` with a real-time hold
(`BATTLE_ANNOUNCEMENT_HOLD_SECONDS`), ticked by `_advance_phases(dt)` from `update()` on every
frame regardless of what's being drawn. Gating the draw call alone hides the announcement without
pausing its clock, so its hold can run out -- and its `on_complete` clear `_announcement` -- while
narration sits on top of it, undismissed. A first-time narration entry has no timeout of its own;
the player can read it for as long as they like, comfortably longer than 1.5 seconds.

`update()` now returns before calling `_advance_phases` at all while `self._narration.queue.is_active`,
freezing the whole phase pipeline (not just the announcement) rather than only its rendering.
Anything with a real-time hold or auto-clear needs its own timer paused when it's not on screen,
not just its draw call skipped -- hiding and pausing are different guarantees.

## 2026-09-14 - A narration trigger can fire on the same frame a card is already up

`ExplorationScene`'s fix for "the same press only dismisses narration, never the action it names"
forwards a dismissed press's action into `_pending_action` -- but only when `self._card is None`.
Dropping that half of the guard still passes the entire suite; nothing else catches it.

`_check_narration_triggers()` runs unconditionally every `update()`, regardless of `self._card`.
`FIRST_SEED_READY` is level-checked (`_can_plant_seed()`), not edge-triggered, so it can raise on
the very frame a screen's own pickup card is already showing (the advance that makes the seed
ready is also the advance that reveals the pickup). Forwarding the action there would plant the
seed while the card still stands, bypassing the card gate entirely.

Any future "dismiss-and-act" forwarding needs its own `self._card is None` check, not just "queue
now empty" -- and needs a test that actually reaches card-up-plus-narration-active, not just one
that dismisses narration alone.

## 2026-09-14 - `TitleScene` has music only because of what constructs it, not anything it does

`app.py::_initial_scene()` builds `TitleScene(MenuScene(atlas, rng, audio))` -- `TitleScene` itself
takes no `audio` parameter and never calls `play_ambient()`. The title screen has `MENU` playing
anyway, because `MenuScene.__init__` (which runs first, as the inner constructor call) already
started it before `TitleScene` exists.

`TitleScene.__init__(next_scene: Scene)` accepts any `Scene` -- reading `title.py` alone gives no
indication that its music depends on `next_scene` already having primed the ambient channel. The
invariant holds only because `TitleScene`/`MenuScene` have exactly one production construction
site, together, in `app.py`.

A future `TitleScene` built with some other `next_scene` (or a test asserting the title screen
plays music on its own) needs its own `play_ambient()` call -- don't assume `TitleScene` carries
this behavior itself.

## 2026-09-14 - `TitleScene` dismissing on "any key" fires from an OS/WM fullscreen toggle too

Playtesting: switching the game window to fullscreen (a window-manager shortcut, not a key the
game defines) skipped straight past the title screen to the menu, on the very first frame.

The original `handle_pygame_event` treated any `pygame.KEYDOWN` as "continue" -- SDL/pygame
delivers a synthetic keydown for at least some OS-level window operations, and there was nothing
distinguishing that from an actual player keypress.

`TitleScene` now only dismisses on `pygame.K_RETURN`. Any future "press any key" style prompt
should default to a specific key (or a small explicit set) rather than literally any `KEYDOWN`,
unless it's verified the surface it's shown on never receives synthetic OS-level key events.

## 2026-09-14 - `Channel.fadeout()`/`stop()` *promote* a queued sound instead of dropping it

Playtesting: after a fight ended, the combat loop kept playing over the exploration music --
`fight_won` faded in as designed, but the loop it was supposed to be replacing came back at full
volume and ran for another full iteration (13.1s) alongside the ambient track.

`AudioManager` keeps the next loop iteration queued on the battle-primary channel at all times
(ADR 0018 -- that is what makes the loop gapless). `resolve_battle_music()` called
`fadeout(1000)` on that channel assuming the fade would take the queued sound with it. It does
not. Measured on pygame-ce 2.5.8 / SDL 2.32.10: the fade runs to completion, and *then* pygame's
channel-finished handling starts whatever is queued -- at full volume, ignoring the fade entirely.

`stop()` behaves the same way and is worse for being non-obvious: one `stop()` halts the playing
sound and promotes the queued one, leaving `get_busy()` still `True`; it takes a second `stop()`
to actually silence the channel.

pygame exposes no unqueue. The remedy is to displace the pending sound by queueing something
inaudible over it (`_silence()`, a few frames of zeros in the mixer's own format) *before* the
`fadeout()`/`stop()` call -- `queue()` replaces whatever was already pending.

Any future code that stops or fades a channel this module has queued a sound on has to do the
same. The unit tests cannot catch this on their own: `FakeMixerChannel` has no notion of SDL
promoting a queued sound, which is why `tests/gui/test_audio.py` keeps one real-channel test
(`test_battle_primary_channel_falls_silent_after_the_crossfade_on_real_channels`) with a real
wall-clock wait.

## 2026-09-25 - PyInstaller builds "successfully" with no game assets

`make exe` reported success, and the build had no sprites, sounds or fonts in it.

`collect_data_files("eye")` imports `eye` in a subprocess to find its files. `eye` isn't installed
into the venv, and the `pyinstaller` entry point doesn't put the repo root on `sys.path`, so that
import fails. It only logs `skipping data collection for module 'eye' as it is not a package`.
The Python modules are still bundled, so nothing else looks wrong.

`eye.spec` puts `SPECPATH` on `sys.path` for this reason. After touching the spec, check the build
for `_internal/eye/gui/sprites`. Asset lookups must also stay package-relative
(`Path(__file__).parent / ...`), never CWD-relative: the frozen game runs from wherever the player
launched it.

## 2026-09-26 - itch.io keeps playing an old web zip after a successful `html5` push

The release run's `butler push` to `html5` succeeded, and the itch.io page said "updated N hours
ago", but the browser embed still ran the jam-era build.

`butler push` updates only the upload behind its channel. "This file will be played in the
browser" is a per-upload checkbox, and a web zip uploaded by hand is a separate upload with no
channel. If that manual upload has the checkbox ticked, the embed keeps serving it. Nothing in
the butler output shows this.

Keep exactly one web upload on the game's Edit game → Uploads page: the `html5` channel one,
with the checkbox ticked. Delete any manually uploaded web zip.
