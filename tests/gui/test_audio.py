from __future__ import annotations

import time

import pygame
import pytest

from eye.gui.audio import (
    _BATTLE_PRIMARY_CHANNEL_ID,
    AudioManager,
    SoundKey,
    _default_channel,
    _load_sound,
    _silence,
    _SilentMixerChannel,
)
from tests.gui.doubles import SpyAudioManager, build_spy_audio_manager

_Rig = SpyAudioManager


@pytest.fixture
def rig() -> _Rig:
    return build_spy_audio_manager()


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
    queue_calls_after_resolve = len(rig.battle_primary.queue_calls)
    rig.battle_primary.queued_sound = None
    rig.manager.update(0.016)

    assert len(rig.battle_primary.queue_calls) == queue_calls_after_resolve


def test_resolve_battle_music_displaces_the_pending_loop_before_fading_out(rig: _Rig) -> None:
    # fadeout() promotes a pending queued sound instead of dropping it (GOTCHAS.md), so leaving the
    # loop queued restarts it at full volume under the result track. Queueing over it is the fix,
    # and it has to land before the fadeout() call, not after.
    rig.manager.start_battle_music(boss=False)
    assert rig.battle_primary.queue_calls[-1] == rig.sounds[SoundKey.FIGHT_LOOP]

    rig.manager.resolve_battle_music(won=True)

    assert rig.battle_primary.queue_calls[-1] != rig.sounds[SoundKey.FIGHT_LOOP]
    assert rig.battle_primary.queue_calls[-1].get_length() < 0.01  # inaudible, not another track
    assert rig.battle_primary.fadeouts == [1000]
    # What the fade actually promotes, which is the whole bug: silence, never the loop again.
    assert rig.sounds[SoundKey.FIGHT_LOOP] not in rig.battle_primary.promoted


def test_battle_primary_channel_falls_silent_after_the_crossfade_on_real_channels() -> None:
    # The one test driven by real pygame channels rather than FakeMixerChannel: a fake cannot model
    # SDL_mixer promoting a queued sound when the channel it is waiting on stops, which is exactly
    # the behavior that let the combat loop play on over exploration music after a fight.
    manager = AudioManager()
    manager.start_battle_music(boss=False)
    manager.update(0.016)

    manager.resolve_battle_music(won=True)
    # Outlasts _BATTLE_RESULT_CROSSFADE_MILLISECONDS: the promotion happens at the *end* of the
    # fade, so a shorter wait passes even against the unfixed code.
    time.sleep(1.5)

    assert pygame.mixer.Channel(_BATTLE_PRIMARY_CHANNEL_ID).get_busy() is False


@pytest.mark.parametrize("key", list(SoundKey))
def test_every_sound_key_resolves_to_a_shipped_file(key: SoundKey) -> None:
    # Exercises the real eye/gui/sound/<key>.ogg loader -- every test above injects a fake, so a
    # SoundKey whose value drifts from its filename would otherwise only surface as a
    # FileNotFoundError on the first frame of a battle, never at test time.
    assert isinstance(_load_sound(key), pygame.mixer.Sound)


def test_methods_are_no_ops_when_the_mixer_is_unavailable(rig: _Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    # No audio device (a headless machine, a container, some CI/judging environments) must not
    # crash the game -- app.py::run() still boots even if pygame.mixer.init() failed.
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)

    def _raise_if_called(key: SoundKey) -> pygame.mixer.Sound:
        raise AssertionError(f"_load_sound must not be called while unavailable, got {key!r}")

    manager = AudioManager(
        ambient_channel=rig.ambient,
        battle_primary_channel=rig.battle_primary,
        battle_result_channel=rig.battle_result,
        sound_loader=_raise_if_called,
    )

    manager.play_ambient(SoundKey.MENU)
    manager.start_battle_music(boss=False)
    manager.update(0.016)
    manager.resolve_battle_music(won=True)

    assert rig.ambient.played == []
    assert rig.battle_primary.played == []
    assert rig.battle_result.played == []


def test_default_channel_falls_back_to_silent_when_the_mixer_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)

    assert isinstance(_default_channel(0), _SilentMixerChannel)


def test_default_channel_uses_a_real_channel_when_the_mixer_is_available() -> None:
    assert isinstance(_default_channel(0), pygame.mixer.Channel)


def test_silence_is_inaudibly_short_and_matches_the_mixers_own_format() -> None:
    silence = _silence()

    assert silence.get_length() < 0.01
    assert silence.get_raw() == bytes(len(silence.get_raw()))  # every sample is zero


def test_silence_is_cached_rather_than_rebuilt_per_call() -> None:
    assert _silence() is _silence()


def test_silence_refuses_to_build_without_an_initialized_mixer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)

    with pytest.raises(RuntimeError, match="initialized mixer"):
        _silence()


def test_silent_mixer_channel_methods_are_all_safe_no_ops() -> None:
    channel = _SilentMixerChannel()
    sound = next(iter(build_spy_audio_manager().sounds.values()))

    channel.play(sound, loops=-1, fade_ms=500)
    channel.queue(sound)
    channel.fadeout(500)
    channel.stop()

    assert channel.get_queue() is None
