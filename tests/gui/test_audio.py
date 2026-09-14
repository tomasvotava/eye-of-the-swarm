from __future__ import annotations

from dataclasses import dataclass, field

import pygame
import pytest

from eye.gui.audio import AudioManager, SoundKey, _load_sound


def _silent_sound() -> pygame.mixer.Sound:
    return pygame.mixer.Sound(buffer=bytes(4))


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


@dataclass
class _Rig:
    manager: AudioManager
    ambient: FakeMixerChannel
    battle_primary: FakeMixerChannel
    battle_result: FakeMixerChannel
    sounds: dict[SoundKey, pygame.mixer.Sound]


@pytest.fixture
def rig() -> _Rig:
    sounds = {key: _silent_sound() for key in SoundKey}
    ambient = FakeMixerChannel()
    battle_primary = FakeMixerChannel()
    battle_result = FakeMixerChannel()
    manager = AudioManager(
        ambient_channel=ambient,
        battle_primary_channel=battle_primary,
        battle_result_channel=battle_result,
        sound_loader=sounds.__getitem__,
    )
    return _Rig(manager, ambient, battle_primary, battle_result, sounds)


def test_play_ambient_starts_the_track_looped(rig: _Rig) -> None:
    rig.manager.play_ambient(SoundKey.MENU)

    assert rig.ambient.played == [(rig.sounds[SoundKey.MENU], -1, 0)]


def test_play_ambient_is_a_no_op_if_already_playing_that_key(rig: _Rig) -> None:
    rig.manager.play_ambient(SoundKey.MENU)
    rig.manager.play_ambient(SoundKey.MENU)

    assert len(rig.ambient.played) == 1  # not restarted -- would pop on a scene reconstruction


def test_play_ambient_switches_tracks_when_the_key_changes(rig: _Rig) -> None:
    rig.manager.play_ambient(SoundKey.MENU)
    rig.manager.play_ambient(SoundKey.EXPLORATION)

    played_sounds = [sound for sound, _, _ in rig.ambient.played]
    assert played_sounds == [rig.sounds[SoundKey.MENU], rig.sounds[SoundKey.EXPLORATION]]


def test_start_battle_music_stops_the_ambient_channel(rig: _Rig) -> None:
    # Otherwise exploration/menu music keeps looping underneath the entire fight.
    rig.manager.play_ambient(SoundKey.EXPLORATION)
    rig.ambient.busy = True

    rig.manager.start_battle_music(boss=False)

    assert rig.ambient.busy is False


def test_start_battle_music_stops_a_still_fading_previous_result_track(rig: _Rig) -> None:
    # Otherwise a previous fight_won/fight_lost keeps fading in underneath the next fight's cue-in.
    rig.manager.start_battle_music(boss=False)
    rig.manager.resolve_battle_music(won=True)
    rig.battle_result.busy = True

    rig.manager.start_battle_music(boss=False)

    assert rig.battle_result.busy is False


def test_start_battle_music_lets_the_same_ambient_track_replay_afterward(rig: _Rig) -> None:
    # Stopping ambient for battle must also forget which key was playing -- otherwise a later
    # play_ambient(EXPLORATION) call (once combat resolves) reads as "already playing" and skips.
    rig.manager.play_ambient(SoundKey.EXPLORATION)

    rig.manager.start_battle_music(boss=False)
    rig.manager.play_ambient(SoundKey.EXPLORATION)

    played_sounds = [sound for sound, _, _ in rig.ambient.played]
    assert played_sounds == [rig.sounds[SoundKey.EXPLORATION], rig.sounds[SoundKey.EXPLORATION]]


def test_start_battle_music_plays_the_cue_in_once_not_looped(rig: _Rig) -> None:
    rig.manager.start_battle_music(boss=False)

    assert rig.battle_primary.played == [(rig.sounds[SoundKey.FIGHT_CUE_IN], 0, 0)]


def test_start_battle_music_immediately_queues_the_loop_to_follow_gaplessly(rig: _Rig) -> None:
    rig.manager.start_battle_music(boss=False)

    assert rig.battle_primary.queue_calls == [rig.sounds[SoundKey.FIGHT_LOOP]]


def test_start_battle_music_plays_the_boss_cue_in_when_boss(rig: _Rig) -> None:
    rig.manager.start_battle_music(boss=True)

    assert rig.battle_primary.played == [(rig.sounds[SoundKey.BOSS_FIGHT_CUE_IN], 0, 0)]


def test_start_battle_music_queues_the_boss_loop_when_boss(rig: _Rig) -> None:
    rig.manager.start_battle_music(boss=True)

    assert rig.battle_primary.queue_calls == [rig.sounds[SoundKey.BOSS_FIGHT_LOOP]]


def test_update_does_not_requeue_while_something_is_still_queued(rig: _Rig) -> None:
    rig.manager.start_battle_music(boss=False)

    rig.manager.update(0.016)

    assert len(rig.battle_primary.queue_calls) == 1  # the initial queue from start_battle_music


def test_update_requeues_the_loop_once_sdl_mixer_starts_playing_the_queued_track(rig: _Rig) -> None:
    rig.manager.start_battle_music(boss=False)
    rig.battle_primary.queued_sound = None  # simulate SDL_mixer moving the loop to "now playing"

    rig.manager.update(0.016)

    assert rig.battle_primary.queue_calls[-1] == rig.sounds[SoundKey.FIGHT_LOOP]


def test_update_requeues_the_boss_loop_once_sdl_mixer_starts_playing_the_queued_track(rig: _Rig) -> None:
    rig.manager.start_battle_music(boss=True)
    rig.battle_primary.queued_sound = None

    rig.manager.update(0.016)

    assert rig.battle_primary.queue_calls[-1] == rig.sounds[SoundKey.BOSS_FIGHT_LOOP]


def test_update_keeps_requeueing_the_loop_every_time_the_queue_slot_frees_up(rig: _Rig) -> None:
    # Each re-queue keeps exactly one loop iteration lined up, indefinitely -- this is what makes
    # the loop-to-loop wrap gapless too, not just the cue-in-to-loop handoff.
    rig.manager.start_battle_music(boss=False)

    for _ in range(5):
        rig.battle_primary.queued_sound = None
        rig.manager.update(0.016)

    assert len(rig.battle_primary.queue_calls) == 6  # 1 initial (start_battle_music) + 5 re-queues


def test_update_is_a_no_op_before_any_battle_music_has_started(rig: _Rig) -> None:
    rig.manager.update(0.016)

    assert rig.battle_primary.played == []
    assert rig.battle_primary.queue_calls == []


def test_resolve_battle_music_fades_out_the_primary_and_fades_in_the_won_track(rig: _Rig) -> None:
    rig.manager.start_battle_music(boss=False)

    rig.manager.resolve_battle_music(won=True)

    assert rig.battle_primary.fadeouts == [1000]
    assert rig.battle_result.played == [(rig.sounds[SoundKey.FIGHT_WON], 0, 1000)]


def test_resolve_battle_music_fades_in_the_lost_track_when_not_won(rig: _Rig) -> None:
    rig.manager.start_battle_music(boss=False)

    rig.manager.resolve_battle_music(won=False)

    assert rig.battle_result.played == [(rig.sounds[SoundKey.FIGHT_LOST], 0, 1000)]


def test_resolve_battle_music_stops_the_cue_in_loop_handoff(rig: _Rig) -> None:
    # A crossfade mid-cue-in must not have a later update() clobber the result track with a loop
    # re-queue it was about to make.
    rig.manager.start_battle_music(boss=False)

    rig.manager.resolve_battle_music(won=True)
    rig.battle_primary.queued_sound = None
    rig.manager.update(0.016)

    assert len(rig.battle_primary.queue_calls) == 1  # only the initial queue -- no re-queue after resolve


@pytest.mark.parametrize("key", list(SoundKey))
def test_every_sound_key_resolves_to_a_shipped_file(key: SoundKey) -> None:
    # Exercises the real eye/gui/sound/<key>.ogg loader -- every test above injects a fake, so a
    # SoundKey whose value drifts from its filename would otherwise only surface as a
    # FileNotFoundError on the first frame of a battle, never at test time.
    assert isinstance(_load_sound(key), pygame.mixer.Sound)
