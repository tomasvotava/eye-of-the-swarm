from enum import StrEnum

import pygame
import pytest

from eye.gui.animation import AnimationClip, Animator, crop_to_cover, scale_clip, scale_sprite


class _State(StrEnum):
    IDLE = "idle"
    WALK = "walk"


class _SingleState(StrEnum):
    IDLE = "idle"


def _clip(frame_count: int, frame_duration_seconds: float = 0.1, *, loop: bool = True) -> AnimationClip:
    frames = tuple(pygame.Surface((1, 1)) for _ in range(frame_count))
    return AnimationClip(frames=frames, frame_duration_seconds=frame_duration_seconds, loop=loop)


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


def test_animator_state_reports_the_current_state() -> None:
    clips = {_State.IDLE: _clip(2), _State.WALK: _clip(3)}
    animator = Animator(clips, initial_state=_State.IDLE)

    animator.set_state(_State.WALK)

    assert animator.state is _State.WALK


def test_scale_sprite_is_a_no_op_passthrough_at_factor_one() -> None:
    sprite = pygame.Surface((4, 4))

    assert scale_sprite(sprite, 1) is sprite


def test_scale_sprite_scales_dimensions_by_factor() -> None:
    sprite = pygame.Surface((4, 6))

    scaled = scale_sprite(sprite, 3)

    assert scaled.get_size() == (12, 18)


def test_scale_clip_is_a_no_op_passthrough_at_factor_one() -> None:
    clip = _clip(2)

    assert scale_clip(clip, 1) is clip


def test_scale_clip_scales_every_frame_and_preserves_other_fields() -> None:
    clip = AnimationClip(
        frames=(pygame.Surface((2, 2)), pygame.Surface((2, 2))), frame_duration_seconds=0.1, loop=False
    )

    scaled = scale_clip(clip, 4)

    assert [frame.get_size() for frame in scaled.frames] == [(8, 8), (8, 8)]
    assert scaled.frame_duration_seconds == clip.frame_duration_seconds
    assert scaled.loop is False


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


def test_animation_clip_total_duration_seconds_is_frame_count_times_frame_duration() -> None:
    clip = _clip(4, frame_duration_seconds=0.05)

    assert clip.total_duration_seconds == pytest.approx(0.2)


def test_set_state_to_the_same_non_looping_state_restarts_the_clip() -> None:
    clips = {_SingleState.IDLE: _clip(2, frame_duration_seconds=0.1, loop=False)}
    animator = Animator(clips, initial_state=_SingleState.IDLE)
    animator.update(0.1)
    assert animator.current_frame() is clips[_SingleState.IDLE].frames[1]

    animator.set_state(_SingleState.IDLE)  # a combo's second hit re-requesting the same state

    assert animator.current_frame() is clips[_SingleState.IDLE].frames[0]


def test_update_freezes_on_the_last_frame_of_a_non_looping_clip() -> None:
    clips = {_SingleState.IDLE: _clip(2, frame_duration_seconds=0.1, loop=False)}
    animator = Animator(clips, initial_state=_SingleState.IDLE)

    animator.update(0.1)
    assert animator.current_frame() is clips[_SingleState.IDLE].frames[1]

    animator.update(0.1)
    assert animator.current_frame() is clips[_SingleState.IDLE].frames[1]


def test_update_freezes_on_the_last_frame_under_an_oversized_dt_for_a_non_looping_clip() -> None:
    clips = {_SingleState.IDLE: _clip(3, frame_duration_seconds=0.1, loop=False)}
    animator = Animator(clips, initial_state=_SingleState.IDLE)

    animator.update(10.0)  # far exceeds total_duration_seconds -- must not wrap past the last frame

    assert animator.current_frame() is clips[_SingleState.IDLE].frames[2]


def test_crop_to_cover_returns_exactly_the_target_size() -> None:
    surface = pygame.Surface((1456, 816))  # 16:9, wider than the 4:3 target -- overflow on x

    cropped = crop_to_cover(surface, (640, 480))

    assert cropped.get_size() == (640, 480)


def test_crop_to_cover_preserves_aspect_ratio_via_uniform_scale() -> None:
    # A pure-vertical source (portrait prop-style art) overflows on y once scaled to cover a
    # square target -- crop_to_cover must scale up by the SAME factor on both axes, not stretch
    # x and y independently the way pygame.transform.scale would.
    surface = pygame.Surface((768, 1536))

    cropped = crop_to_cover(surface, (200, 200))

    assert cropped.get_size() == (200, 200)


def test_crop_to_cover_is_a_noop_sized_copy_when_source_already_matches_target() -> None:
    surface = pygame.Surface((640, 480))

    cropped = crop_to_cover(surface, (640, 480))

    assert cropped.get_size() == (640, 480)
