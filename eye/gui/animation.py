"""Time-driven animation state machine, generic over each entity's own state enum (ADR 0011)."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum

import pygame


@dataclass(frozen=True, slots=True)
class AnimationClip:
    frames: tuple[pygame.Surface, ...]
    frame_duration_seconds: float
    loop: bool = True

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("AnimationClip requires at least one frame")
        if self.frame_duration_seconds <= 0:
            raise ValueError(f"frame_duration_seconds must be positive, got {self.frame_duration_seconds!r}")

    @property
    def total_duration_seconds(self) -> float:
        return len(self.frames) * self.frame_duration_seconds


def scale_sprite(sprite: pygame.Surface, factor: float) -> pygame.Surface:
    """Scale a single sprite by `factor`, a no-op passthrough at `factor == 1`.

    Meant for a caller building a scene's own animator/static fallback once, up front -- an
    entity's scale factor is fixed, so nothing is gained by recomputing it on every draw() call.
    """
    return sprite if factor == 1 else pygame.transform.scale_by(sprite, factor)


def scale_clip(clip: AnimationClip, factor: float) -> AnimationClip:
    """Scale every frame of `clip` by `factor`, a no-op passthrough at `factor == 1`."""
    if factor == 1:
        return clip
    return replace(clip, frames=tuple(scale_sprite(frame, factor) for frame in clip.frames))


class Animator[TState: StrEnum]:
    def __init__(self, clips: Mapping[TState, AnimationClip], initial_state: TState) -> None:
        missing = [member for member in type(initial_state) if member not in clips]
        if missing:
            raise ValueError(f"missing animation clips for states: {missing}")
        self._clips = clips
        self._state = initial_state
        self._frame_index = 0
        self._elapsed_seconds = 0.0

    def set_state(self, state: TState) -> None:
        # Re-entering the *same* looping state is a no-op (avoids restarting an idle loop every
        # frame it's requested); a one-shot clip must restart even when re-entered from itself --
        # otherwise, once frozen on its last frame, it could never play again (e.g. a combo's
        # second hit re-requesting the same HIT state on a target already flinching from the
        # first).
        if state == self._state and self._clips[state].loop:
            return
        self._state = state
        self._frame_index = 0
        self._elapsed_seconds = 0.0

    def update(self, dt: float) -> None:
        clip = self._clips[self._state]
        if not clip.loop and self._frame_index == len(clip.frames) - 1:
            return  # already frozen on a one-shot clip's last frame
        self._elapsed_seconds += dt
        while self._elapsed_seconds >= clip.frame_duration_seconds:
            self._elapsed_seconds -= clip.frame_duration_seconds
            self._frame_index = (self._frame_index + 1) % len(clip.frames)
            if not clip.loop and self._frame_index == 0:
                # Just wrapped past a one-shot clip's last frame -- snap back and freeze instead.
                self._frame_index = len(clip.frames) - 1
                self._elapsed_seconds = 0.0
                break

    @property
    def state(self) -> TState:
        return self._state

    def current_frame(self) -> pygame.Surface:
        return self._clips[self._state].frames[self._frame_index]

    def duration_of(self, state: TState) -> float:
        return self._clips[state].total_duration_seconds
