# 0018 — Sound wiring

**Status:** Accepted
**Date:** 2026-09-14

## Context

PROJECT_BRIEF.md doesn't specify sound design at all — this is a stretch item (#258, sub-issue of
Epic #253). The 8 `.ogg` files at `eye/gui/sound/` (sibling to `eye/gui/sprites/`/`eye/gui/fonts/`)
arrive with a specific behavioral spec:

- `menu.ogg` plays on `TitleScene`/`MenuScene` (ADR 0017); `exploration.ogg` plays during
  `ExplorationScene`. Both are simple looping ambience — no state machine.
- On battle start, `fight_cue_in.ogg` plays once, and *the same exact frame it ends*,
  `fight_loop.ogg` starts playing in a loop, on what should probably be a single channel. Meeting
  Phidizvik or Golem swaps in `boss_fight_cue_in.ogg`/`boss_fight_loop.ogg` instead.
- On battle conclusion, the current loop fades out while `fight_won.ogg` (win) or `fight_lost.ogg`
  (loss *or* tie — both map to the same track) fades in. This needs a separate channel from the
  loop so the two can overlap during the crossfade.

This introduces a genuinely new architectural concept — an audio subsystem with real playback
state (which track is cueing/looping, mid-crossfade) — that nothing in this codebase has needed
before, so it gets its own ADR rather than landing as an implicit implementation detail, matching
this Epic's own established pattern (ADR 0017 landed alone in PR #252 before any of its
sub-issues' implementation PRs).

## Decision

- **`eye/gui/audio.py`, new module.** `SoundKey(StrEnum)` — one member per shipped file (`MENU`,
  `EXPLORATION`, `FIGHT_CUE_IN`, `FIGHT_LOOP`, `BOSS_FIGHT_CUE_IN`, `BOSS_FIGHT_LOOP`,
  `FIGHT_WON`, `FIGHT_LOST`) — loaded lazily and cached from `eye/gui/sound/<key>.ogg`, mirroring
  `eye/gui/fonts/fonts.py::get_font`'s `_FONT_CACHE` pattern (a path resolved relative to the
  module's own directory, one dict keyed by the enum member, loaded once on first use).
- **`AudioManager`, an instantiated class threaded through scene constructors — like
  `SpriteAtlas`, not a module-level cache like `fonts.py`'s.** Unlike the font cache, this carries
  real mutable per-battle state (which track is cueing vs. looping, whether a crossfade is in
  flight); this codebase always wraps state like that in an owned object (`Battle`,
  `ExplorationRun`, `NarrationTriggers`), never a module global. One instance is built in
  `app.py::run()` and passed down through `MenuScene`/`GameDriver`/`ExplorationScene`/
  `CombatScene`, the same way `atlas` already is. `TitleScene` takes no `audio` of its own --
  see the `TitleScene`/`MenuScene` wiring bullet below for why.
- **Channel access goes through a small `MixerChannel` `Protocol`**, not `pygame.mixer.Channel`
  directly:
  ```python
  class MixerChannel(Protocol):
      def play(self, sound: pygame.mixer.Sound, loops: int = 0, *, fade_ms: int = 0) -> None: ...
      def queue(self, sound: pygame.mixer.Sound) -> None: ...
      def get_queue(self) -> pygame.mixer.Sound | None: ...
      def fadeout(self, ms: int) -> None: ...
      def stop(self) -> None: ...
  ```
  `pygame.mixer.Channel` already satisfies this structurally — the real adapter is just
  `pygame.mixer.Channel(i)` passed straight into `AudioManager.__init__`, no wrapper class needed. `fade_ms` is keyword-only because `Channel.play`'s real signature is
  `(sound, loops, maxtime, fade_ms)` — a positional `fade_ms` here would bind to `maxtime` and the
  Protocol would not be satisfied at all.
  This is the same mock-at-the-infrastructure-boundary posture as `SaveStore` (ADR 0005): a test
  double (`FakeMixerChannel` — a `busy`/`queued_sound` state plus call recording) drives
  `AudioManager`'s state machine deterministically, without real audio decoding or real-time waits.
  This isn't optional ceremony — when SDL_mixer actually moves a queued sound from "waiting" to
  "now playing" is driven by its own real-time clock, not by the `dt` argument
  `CombatScene.update()` passes around, so unlike every other timed mechanic in this codebase
  (`Phase.duration_seconds`, walk timers, animator clips), the cue-in→loop handoff below *cannot*
  be fast-forwarded deterministically through `dt` alone. `AudioManager.__init__` also takes a
  sound-loader callable, defaulting to the real `.ogg` loader, for the same reason.
- **Three fixed channels**, addressed by name rather than a general pool — one ambient track and
  one battle fight ever play at a time, and the crossfade needs the outgoing and incoming battle
  tracks live simultaneously:
  - **ambient** — `play_ambient(key: SoundKey) -> None`. No-op if `key` is already the ambient
    channel's current track (avoids restarting, and audibly popping, a track a caller asks for
    again while it's still playing); otherwise `channel.play(sound, loops=-1)`. Needs no per-frame
    polling — `loops=-1` handles the "forever" part natively.
  - **battle-primary** — `start_battle_music(*, boss: bool) -> None` first stops the ambient
    channel (a fight has its own music; nothing should keep looping underneath it) and clears the
    remembered ambient key, so a later `play_ambient()` call for whatever was playing before battle
    (`EXPLORATION`, once combat resolves) isn't mistaken for still-playing and skipped; it also
    stops the battle-result channel, in case a previous fight's `fight_won`/`fight_lost` is still
    fading in. It then plays `(boss_)fight_cue_in` once and **immediately queues** `(boss_)
    fight_loop` behind it via `Channel.queue()` — this hands the cue-in→loop splice to SDL_mixer
    itself, sample-accurate, rather than this module noticing the cue-in ended and calling `play()`
    again a frame or more late (which is both an audible gap *and*, independently, a source of an
    audible click at the join if the two files don't already line up exactly — `queue()` fixes only
    the first). `update(dt: float) -> None`, polled every frame but **only from
    `CombatScene.update()`** (nothing else has a splice to keep fed): whenever
    `battle_primary_channel.get_queue()` reads `None` — meaning SDL_mixer has moved whatever was
    queued from "waiting" to "now playing," freeing the one queue slot — re-queues the loop track
    again. This repeats indefinitely, so the *only* mechanism is `queue()`; `loops=-1` is
    deliberately never used for the loop track, since calling `play()` again to restart a native
    loop would reintroduce the exact gap/click this design avoids. Each iteration is several
    seconds to tens of seconds long (`fight_loop` 13.1s, `boss_fight_loop` 55.6s), so there's ample
    per-frame slack to notice a freed slot well before the current iteration actually ends.
  - **battle-result** — `resolve_battle_music(*, won: bool) -> None`:
    `battle_primary_channel.fadeout(ms)` and `battle_result_channel.play(fight_won_or_lost,
    fade_ms=ms)` in the same call — native SDL_mixer fades (`pygame.mixer.Channel.fadeout`/
    `Channel.play(..., fade_ms=...)`), no manual volume-ramp polling needed for the crossfade
    itself. `fadeout()` also drops anything queued on the channel (confirmed against pygame-ce
    directly; undocumented), so a trailing `update()` re-queue racing this is not a concern.
- **Boss detection reads `encounter.strain` directly** (`EnemyEncountered.strain`, already a
  `CombatScene` constructor argument): `encounter.strain in (Strain.GOLEM, Strain.PHIDIZVIK)`.
  Confirmed as the domain's two rare/deep-exploration Strains via `eye/exploration/tuning.py`'s
  `STRAIN_MIN_DISTANCE_GOLEM`/`STRAIN_MIN_DISTANCE_PHIDIZVIK` (8/5 screens — the two largest
  encounter-gating distances) — there is no literal `is_boss` flag in the domain, and this ADR
  doesn't add one. Deliberately *not* routed through `CombatScene`'s enemy sprite-key resolution
  (`_resolve_enemy_sprite_key`, used for art): that falls back to `SpriteKey.UNKNOWN` when art is
  missing for a Strain, which would silently downgrade boss music to the regular fight track if
  Golem's or Phidizvik's art ever went missing — an art-pipeline problem quietly becoming an
  audio-pipeline problem. Reading the domain's own `Strain` avoids that coupling entirely.
- **Win/lose is read off the `BattleEnded` event itself**: `won=winner is self._battle.player`, so
  a loss *and* a draw (`winner is None`) both map to `fight_lost`. See the `CombatScene` wiring
  point below for *when* it fires — the event's reveal, not the scene's conclusion.
- **Wiring points** (split across the two follow-up sub-issues below, not this ADR's own PR —
  only `eye/gui/audio.py` and its tests land here):
  - `app.py::run()` calls `pygame.mixer.init()` alongside `pygame.init()`, builds one
    `AudioManager`.
  - `MenuScene.__init__`: `play_ambient(SoundKey.MENU)`. `TitleScene` takes no `audio` of its own
    and never calls `play_ambient` — it always wraps an already-constructed `MenuScene`
    (`TitleScene(MenuScene(atlas, rng, audio))`), so `MenuScene`'s own constructor has already
    started `MENU` by the time the title screen shows. This holds only because `TitleScene`/
    `MenuScene` have exactly one production construction site, together, in `app.py`; a future
    `TitleScene` built with some other `next_scene` needs its own `play_ambient()` call (recorded
    in `GOTCHAS.md`, since nothing in `title.py` itself hints at the dependency).
  - `ExplorationScene` (`for_new_generation`/`resuming_after_combat`):
    `play_ambient(SoundKey.EXPLORATION)`.
  - `CombatScene.__init__`: `start_battle_music(boss=...)`; `update()`: `audio.update(dt)`. Win/lose
    resolution fires from the `BattleEnded` event's own reveal (`_phases_for`'s `on_start`), the
    same frame the "You win!"/"You lose!" text appears — not from `_conclude()`, which only runs
    once that announcement's full hold has *already* elapsed and every other reveal has finished,
    which would mean the music arrives well after the text, once the scene is already handing off
    to exploration.
  - `GameDriver`: takes `audio` too, passes it through to whichever inner scene it constructs; also
    calls `play_ambient(SoundKey.MENU)` in `_resolve_battle_concluded()` on a death, right before
    handing off to `SkillTreeScene` — that scene has no track of its own, so without this call the
    result track (`fight_lost`, ~10.7s) finishes fading and the
    entire between-generations spend screen — where a roguelite player spends a real share of their
    session — plays in total silence.
  - **Not wired**: `SettingsScene`/`CreditsScene` (#280) — no ambient call needed on entry to
    either, since neither one changes what should be playing; whatever brought the player there
    (`MENU`, always, since both are only reachable from `MenuScene`) correctly keeps looping.
  - **Ambient-over-result-fanfare overlap, deliberately left as-is**: moving win/lose resolution
    earlier (above) means more of `fight_won`/`fight_lost`'s fade-in has already played by the time
    `ExplorationScene.resuming_after_combat()` calls `play_ambient(EXPLORATION)`, but the two can
    still briefly overlap depending on how much announcement/narration plays in between. Whether
    that reads as an intentional "victory fanfare over the returning ambience" or needs an explicit
    delay is a playtesting call, not an architectural one — noted here so it isn't mistaken for an
    oversight when it's revisited.
- **Not affected by `combat_speed_multiplier` (ADR 0017).** Audio plays at real, wall-clock speed
  regardless of the combat-pacing setting — pitch-shifting or resampling playback to match a faster
  visual pace was never asked for and is out of scope here.
- **Sub-issue split, filed under #258 once this ADR's content is settled**: ambient wiring
  (Title/Menu/Exploration `play_ambient` calls — small, mechanical, no blockers) and the battle
  music state machine (cue-in→loop, boss variant, win/lose crossfade in `CombatScene` — the actual
  complexity). Both depend only on `eye/gui/audio.py` existing, which this ADR's own PR adds, not
  on each other.

## Consequences

- `eye/gui/` gains a `pygame.mixer` dependency it didn't have before. `tests/gui/conftest.py`'s
  existing `SDL_VIDEODRIVER=dummy` headless-display fixture gains a matching
  `SDL_AUDIODRIVER=dummy` + `pygame.mixer.init()`, so `AudioManager` (via `FakeMixerChannel`, not
  the real dummy-driver channel — see above) is exercisable in CI the same way video already is.
- **No audio device is a supported configuration, not an error.** A headless machine, a container
  and some CI/judging environments have none, and `pygame.mixer.init()` raises there. `run()`
  suppresses that `pygame.error` and boots anyway; `AudioManager` latches
  `_available = pygame.mixer.get_init() is not None` at construction and every public method
  returns early on it, so no `Sound` is ever constructed (which would raise in turn) and the game
  simply plays silently. `_default_channel()` returns a `_SilentMixerChannel` rather than
  `pygame.mixer.Channel(i)` for the same reason — constructing a real channel raises with a dead
  mixer, so the fallback has to happen before `_available` is ever consulted.
- Ambient and battle music are governed by two entirely separate mechanisms (`loops=-1` for
  ambient, an explicit polled state machine for battle) rather than one shared abstraction — a
  deliberate asymmetry, not an oversight: ambient never needs a cue-in or a crossfade, and forcing
  it through the battle machinery's polling would cost a `SoundKey` state check every frame for no
  behavior it needs.
- Browser (pygbag) support for `pygame.mixer.Channel`-based playback, including `fadeout`/
  `fade_ms`, is assumed from pygame-ce's documented API but not verified against a native web
  smoke test as part of this ADR — flag if pygbag's SDL_mixer build behaves differently, per the
  same class of native-vs-web surprise already logged in `GOTCHAS.md` for other pygame subsystems.
- The 8 `.ogg` files are tracked via Git LFS (`.gitattributes`), matching every other binary asset
  in this repo (`*.png`/`*.jpg`) — landing them as regular blobs would have permanently grown
  `.git` by ~10% for content that gains nothing from zlib delta-compression (already-compressed
  Vorbis).
- **Asset provenance is not recorded anywhere** — `CreditsScene`'s one attribution line covers the
  Midjourney/Claude/Mistral-generated art, and says nothing about where the 8 music tracks came
  from or under what terms. Tracked as #295.
