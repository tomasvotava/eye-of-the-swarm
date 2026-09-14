"""Shared GUI test doubles, mirroring tests/persistence/doubles.py's/tests/session/doubles.py's
convention of one small module per test package rather than scattering fakes across test files.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from eye.gui.audio import AudioManager, SoundKey


@dataclass
class FakeMixerChannel:
    """A `MixerChannel` double whose `queued_sound`/`busy` state is set directly by a test, rather
    than driven by SDL_mixer's own real-time clock -- the whole reason `AudioManager` depends on
    the `MixerChannel` Protocol instead of `pygame.mixer.Channel` (ADR 0018)."""

    busy: bool = False
    played: list[tuple[pygame.mixer.Sound, int, int]] = field(default_factory=list)
    fadeouts: list[int] = field(default_factory=list)
    queue_calls: list[pygame.mixer.Sound] = field(default_factory=list)
    queued_sound: pygame.mixer.Sound | None = None

    def play(self, sound: pygame.mixer.Sound, loops: int = 0, fade_ms: int = 0) -> None:
        self.played.append((sound, loops, fade_ms))
        self.busy = True
        self.queued_sound = None

    def queue(self, sound: pygame.mixer.Sound) -> None:
        self.queue_calls.append(sound)
        self.queued_sound = sound

    def get_queue(self) -> pygame.mixer.Sound | None:
        return self.queued_sound

    def fadeout(self, ms: int) -> None:
        self.fadeouts.append(ms)
        self.busy = False
        self.queued_sound = None

    def stop(self) -> None:
        self.busy = False
        self.queued_sound = None


def silent_sound(key: SoundKey) -> pygame.mixer.Sound:
    """A tiny in-memory `Sound`, real enough to satisfy `AudioManager`'s
    `Callable[[SoundKey], pygame.mixer.Sound]` typing without decoding a real `.ogg` file."""
    del key
    return pygame.mixer.Sound(buffer=bytes(4))


def build_fake_audio_manager() -> AudioManager:
    """An `AudioManager` wired to fresh `FakeMixerChannel`s and `silent_sound`, for scenes that
    need a real `AudioManager` instance (it's a required constructor dependency, matching `atlas`)
    but whose test doesn't care about audio playback itself."""
    return AudioManager(
        ambient_channel=FakeMixerChannel(),
        battle_primary_channel=FakeMixerChannel(),
        battle_result_channel=FakeMixerChannel(),
        sound_loader=silent_sound,
    )


@dataclass
class SpyAudioManager:
    """`build_spy_audio_manager()`'s return value -- the `AudioManager` plus its own fake channels
    and the exact `Sound` object each `SoundKey` resolves to, for a test that needs to assert what
    was actually played rather than just needing a valid `AudioManager` to construct a scene with."""

    manager: AudioManager
    ambient: FakeMixerChannel
    battle_primary: FakeMixerChannel
    battle_result: FakeMixerChannel
    sounds: dict[SoundKey, pygame.mixer.Sound]


def build_spy_audio_manager() -> SpyAudioManager:
    ambient = FakeMixerChannel()
    battle_primary = FakeMixerChannel()
    battle_result = FakeMixerChannel()
    sounds = {key: silent_sound(key) for key in SoundKey}
    manager = AudioManager(
        ambient_channel=ambient,
        battle_primary_channel=battle_primary,
        battle_result_channel=battle_result,
        sound_loader=sounds.__getitem__,
    )
    return SpyAudioManager(manager, ambient, battle_primary, battle_result, sounds)
