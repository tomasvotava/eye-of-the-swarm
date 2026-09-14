"""AudioManager: ambient and battle-music playback (ADR 0018). Channel access goes through the
`MixerChannel` Protocol rather than `pygame.mixer.Channel` directly -- `pygame.mixer.Channel`
already satisfies it structurally, so the real adapter is just `pygame.mixer.Channel(i)` passed
in, but a test double can drive the cue-in-to-loop handoff deterministically. That handoff cannot
be driven by `dt` the way every other timed mechanic in this codebase is: when SDL_mixer actually
moves a queued sound from "waiting" to "now playing" runs on its own real-time clock, not on the
`dt` argument `CombatScene.update()` passes around -- `Channel.get_queue()` is how this module
observes that happened.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import pygame

_SOUND_ASSETS_DIR = Path(__file__).parent / "sound"

_AMBIENT_CHANNEL_ID = 0
_BATTLE_PRIMARY_CHANNEL_ID = 1
_BATTLE_RESULT_CHANNEL_ID = 2

# Playtesting-driven placeholder (PROJECT_BRIEF.md §8), like every other GUI-pacing constant.
_BATTLE_RESULT_CROSSFADE_MILLISECONDS = 1000


class SoundKey(StrEnum):
    MENU = "menu"
    EXPLORATION = "exploration"
    FIGHT_CUE_IN = "fight_cue_in"
    FIGHT_LOOP = "fight_loop"
    BOSS_FIGHT_CUE_IN = "boss_fight_cue_in"
    BOSS_FIGHT_LOOP = "boss_fight_loop"
    FIGHT_WON = "fight_won"
    FIGHT_LOST = "fight_lost"


class MixerChannel(Protocol):
    # fade_ms is keyword-only, unlike pygame.mixer.Channel.play's own positional `maxtime` sitting
    # between loops and fade_ms in the real signature -- every call site here already passes it by
    # keyword, and this is what makes pygame.mixer.Channel structurally satisfy this Protocol at
    # all (a positional fade_ms would collide with Channel's own maxtime slot).
    def play(self, sound: pygame.mixer.Sound, loops: int = 0, *, fade_ms: int = 0) -> None: ...
    def queue(self, sound: pygame.mixer.Sound) -> None: ...
    def get_queue(self) -> pygame.mixer.Sound | None: ...
    def fadeout(self, ms: int) -> None: ...
    def stop(self) -> None: ...


class _SilentMixerChannel:
    """A `MixerChannel` that does nothing -- `AudioManager`'s real-channel default when no audio
    device is available (`pygame.mixer.init()` failed: a headless machine, a container, some
    CI/judging environments). Pure Python, touches no pygame API, so it's always safe to
    construct regardless of mixer state."""

    def play(self, sound: pygame.mixer.Sound, loops: int = 0, *, fade_ms: int = 0) -> None:
        pass

    def queue(self, sound: pygame.mixer.Sound) -> None:
        pass

    def get_queue(self) -> pygame.mixer.Sound | None:
        return None

    def fadeout(self, ms: int) -> None:
        pass

    def stop(self) -> None:
        pass


def _default_channel(channel_id: int) -> MixerChannel:
    if pygame.mixer.get_init() is None:
        return _SilentMixerChannel()
    return pygame.mixer.Channel(channel_id)


def _sound_path(key: SoundKey) -> Path:
    if not (path := _SOUND_ASSETS_DIR / f"{key.value}.ogg").exists():
        raise FileNotFoundError(f"no sound file found at {path.as_posix()}.")
    return path


_SOUND_CACHE: dict[SoundKey, pygame.mixer.Sound] = {}


def _load_sound(key: SoundKey) -> pygame.mixer.Sound:
    if key not in _SOUND_CACHE:
        _SOUND_CACHE[key] = pygame.mixer.Sound(_sound_path(key))
    return _SOUND_CACHE[key]


class AudioManager:
    """Owns three fixed channels: ambient (looping title/menu/exploration music), and a
    battle-primary/battle-result pair for the cue-in-then-loop-then-crossfade-to-result sequence a
    fight plays (ADR 0018). One instance is built in `app.py::run()` and threaded through scene
    constructors the same way `atlas` already is -- not a module-level cache like
    `fonts.py::get_font`'s, since this carries real mutable per-battle state.
    """

    def __init__(
        self,
        ambient_channel: MixerChannel | None = None,
        battle_primary_channel: MixerChannel | None = None,
        battle_result_channel: MixerChannel | None = None,
        sound_loader: Callable[[SoundKey], pygame.mixer.Sound] = _load_sound,
    ) -> None:
        self._ambient_channel = (
            ambient_channel if ambient_channel is not None else _default_channel(_AMBIENT_CHANNEL_ID)
        )
        self._battle_primary_channel = (
            battle_primary_channel
            if battle_primary_channel is not None
            else _default_channel(_BATTLE_PRIMARY_CHANNEL_ID)
        )
        self._battle_result_channel = (
            battle_result_channel if battle_result_channel is not None else _default_channel(_BATTLE_RESULT_CHANNEL_ID)
        )
        self._load_sound = sound_loader
        # Guards every public method below against calling _load_sound (a real pygame.mixer.Sound
        # construction, which raises with no mixer initialized) -- app.py::run() still boots the
        # game rather than crashing when pygame.mixer.init() fails, with sound silently
        # unavailable, matching the real-channel fallback above.
        self._available = pygame.mixer.get_init() is not None
        self._ambient_key: SoundKey | None = None
        self._battle_active = False
        self._battle_is_boss = False

    def play_ambient(self, key: SoundKey) -> None:
        """Loops `key` on the ambient channel. A no-op if `key` is already the ambient channel's
        current track -- guards against restarting (and audibly popping) a track that a caller
        asks for again while it's still playing.
        """
        if not self._available or self._ambient_key is key:
            return
        self._ambient_key = key
        self._ambient_channel.play(self._load_sound(key), loops=-1)

    def start_battle_music(self, *, boss: bool) -> None:
        """Stops the ambient channel and any still-fading previous result track, then plays the
        cue-in once on the battle-primary channel with the loop immediately queued to follow it --
        `Channel.queue()` hands the splice to SDL_mixer itself, sample-accurate, rather than this
        module noticing the cue-in ended and calling `play()` again a frame or more late (an
        audible gap, and -- independent of any gap -- an audible click at the join if the two
        files don't already line up exactly, which `queue()` cannot fix either). Stopping ambient
        here (rather than leaving it to whoever calls this) also clears `_ambient_key`, so a later
        `play_ambient()` call for the same track that was playing before battle (e.g.
        `EXPLORATION`, once combat resolves) is not mistaken for a still-playing one and skipped.
        """
        if not self._available:
            return
        self._ambient_channel.stop()
        self._ambient_key = None
        self._battle_result_channel.stop()  # a previous fight_won/fight_lost must not bleed into this one
        self._battle_is_boss = boss
        cue_key = SoundKey.BOSS_FIGHT_CUE_IN if boss else SoundKey.FIGHT_CUE_IN
        loop_key = SoundKey.BOSS_FIGHT_LOOP if boss else SoundKey.FIGHT_LOOP
        self._battle_primary_channel.play(self._load_sound(cue_key))
        self._battle_primary_channel.queue(self._load_sound(loop_key))
        self._battle_active = True

    def update(self, dt: float) -> None:
        """Polled every frame, but only from `CombatScene.update()` -- ambient music needs no
        polling (`loops=-1` handles "forever" natively). `dt` is unused: `get_queue()` returning
        `None` means SDL_mixer has already moved the queued sound from "waiting" to "now playing"
        -- checked every call, not timed against `dt` -- at which point the next loop iteration is
        re-queued, keeping the splice gapless indefinitely without ever calling `play()` again
        (which would itself restart from sample 0 and reintroduce exactly the gap/click this is
        avoiding). `loops=-1` is deliberately never used for the loop track for the same reason.
        """
        if not self._available:
            return
        if self._battle_active and self._battle_primary_channel.get_queue() is None:
            loop_key = SoundKey.BOSS_FIGHT_LOOP if self._battle_is_boss else SoundKey.FIGHT_LOOP
            self._battle_primary_channel.queue(self._load_sound(loop_key))

    def resolve_battle_music(self, *, won: bool) -> None:
        """Fades the battle-primary channel out while fading `fight_won`/`fight_lost` in on the
        battle-result channel, so the two overlap during the crossfade. `fadeout()` also drops
        anything queued on the channel (undocumented pygame-ce behavior, not just an assumption),
        so a trailing `update()` re-queueing the loop one more time first is not a race with this.
        """
        if not self._available:
            return
        self._battle_primary_channel.fadeout(_BATTLE_RESULT_CROSSFADE_MILLISECONDS)
        result_key = SoundKey.FIGHT_WON if won else SoundKey.FIGHT_LOST
        self._battle_result_channel.play(self._load_sound(result_key), fade_ms=_BATTLE_RESULT_CROSSFADE_MILLISECONDS)
        self._battle_active = False
