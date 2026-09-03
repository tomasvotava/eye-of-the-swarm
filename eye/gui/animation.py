"""Time-driven animation state machine, generic over each entity's own state enum (ADR 0011)."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import pygame


@dataclass(frozen=True, slots=True)
class AnimationClip:
    frames: tuple[pygame.Surface, ...]
    frame_duration_seconds: float

    def __post_init__(self) -> None:
        if not self.frames:
            raise ValueError("AnimationClip requires at least one frame")
        if self.frame_duration_seconds <= 0:
            raise ValueError(f"frame_duration_seconds must be positive, got {self.frame_duration_seconds!r}")


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
        if state == self._state:
            return
        self._state = state
        self._frame_index = 0
        self._elapsed_seconds = 0.0

    def update(self, dt: float) -> None:
        clip = self._clips[self._state]
        self._elapsed_seconds += dt
        while self._elapsed_seconds >= clip.frame_duration_seconds:
            self._elapsed_seconds -= clip.frame_duration_seconds
            self._frame_index = (self._frame_index + 1) % len(clip.frames)

    def current_frame(self) -> pygame.Surface:
        return self._clips[self._state].frames[self._frame_index]
