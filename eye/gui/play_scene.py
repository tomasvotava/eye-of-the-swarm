"""PlayScene: the protocol and transition-request seam for GameDriver's inner scenes (ADR 0010) --
`exploration.py`/`combat.py`/`skilltree.py` reference only this module, never each other, so the
real cycle between them (exploration hands off to combat and back) never has an import to close.
Mirrors `eye/gui/scene.py`'s own role at the outer, `app.py`-facing level, one tier down: this
module imports no concrete scene either.
"""

from dataclasses import dataclass
from typing import Protocol

import pygame

from eye.exploration.events import EnemyEncountered


@dataclass(frozen=True)
class EnterCombat:
    encounter: EnemyEncountered


@dataclass(frozen=True)
class BattleConcluded:
    pass


@dataclass(frozen=True)
class Continue:
    pass


type PlaySceneTransition = EnterCombat | BattleConcluded | Continue


class PlayScene(Protocol):
    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> PlaySceneTransition | None: ...
    def draw(self, surface: pygame.Surface) -> None: ...
