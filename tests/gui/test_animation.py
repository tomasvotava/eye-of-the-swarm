from enum import StrEnum

import pygame
import pytest

from eye.gui.animation import AnimationClip, Animator


class _State(StrEnum):
    IDLE = "idle"
    WALK = "walk"


class _SingleState(StrEnum):
    IDLE = "idle"


def _clip(frame_count: int, frame_duration_seconds: float = 0.1) -> AnimationClip:
    frames = tuple(pygame.Surface((1, 1)) for _ in range(frame_count))
    return AnimationClip(frames=frames, frame_duration_seconds=frame_duration_seconds)


def test_animation_clip_rejects_zero_frames() -> None:
    with pytest.raises(ValueError, match="at least one frame"):
        AnimationClip(frames=(), frame_duration_seconds=0.1)


@pytest.mark.parametrize("frame_duration_seconds", [0.0, -0.1])
def test_animation_clip_rejects_a_non_positive_frame_duration(frame_duration_seconds: float) -> None:
    with pytest.raises(ValueError, match="frame_duration_seconds must be positive"):
        AnimationClip(frames=(pygame.Surface((1, 1)),), frame_duration_seconds=frame_duration_seconds)


def test_animator_construction_succeeds_when_every_state_has_a_clip() -> None:
    clips = {_State.IDLE: _clip(2), _State.WALK: _clip(3)}

    animator = Animator(clips, initial_state=_State.IDLE)

    assert animator.current_frame() is clips[_State.IDLE].frames[0]


def test_animator_construction_raises_when_a_state_has_no_clip() -> None:
    clips = {_State.IDLE: _clip(2)}

    with pytest.raises(ValueError, match="WALK"):
        Animator(clips, initial_state=_State.IDLE)


def test_set_state_to_a_new_state_resets_frame_and_elapsed_time() -> None:
    clips = {_State.IDLE: _clip(2, frame_duration_seconds=0.1), _State.WALK: _clip(3, frame_duration_seconds=0.1)}
    animator = Animator(clips, initial_state=_State.IDLE)
    animator.update(0.1)
    assert animator.current_frame() is clips[_State.IDLE].frames[1]

    animator.set_state(_State.WALK)

    assert animator.current_frame() is clips[_State.WALK].frames[0]


def test_set_state_to_the_same_state_is_a_no_op() -> None:
    clips = {_SingleState.IDLE: _clip(2, frame_duration_seconds=0.1)}
    animator = Animator(clips, initial_state=_SingleState.IDLE)
    animator.update(0.1)
    assert animator.current_frame() is clips[_SingleState.IDLE].frames[1]

    animator.set_state(_SingleState.IDLE)

    assert animator.current_frame() is clips[_SingleState.IDLE].frames[1]


def test_update_advances_the_frame_once_enough_time_has_accumulated() -> None:
    clips = {_SingleState.IDLE: _clip(3, frame_duration_seconds=0.1)}
    animator = Animator(clips, initial_state=_SingleState.IDLE)

    animator.update(0.05)
    assert animator.current_frame() is clips[_SingleState.IDLE].frames[0]

    animator.update(0.05)
    assert animator.current_frame() is clips[_SingleState.IDLE].frames[1]


def test_update_wraps_back_to_the_first_frame_after_the_last() -> None:
    clips = {_SingleState.IDLE: _clip(2, frame_duration_seconds=0.1)}
    animator = Animator(clips, initial_state=_SingleState.IDLE)

    animator.update(0.1)
    assert animator.current_frame() is clips[_SingleState.IDLE].frames[1]

    animator.update(0.1)
    assert animator.current_frame() is clips[_SingleState.IDLE].frames[0]


def test_update_wraps_through_multiple_frames_in_a_single_large_dt() -> None:
    clips = {_SingleState.IDLE: _clip(3, frame_duration_seconds=0.1)}
    animator = Animator(clips, initial_state=_SingleState.IDLE)

    animator.update(0.25)

    assert animator.current_frame() is clips[_SingleState.IDLE].frames[2]
