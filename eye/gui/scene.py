from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pygame

from eye.exploration.events import EnemyEncountered
from eye.session.game import Game
from eye.session.generation import Generation


@dataclass(frozen=True)
class EnterCombat:
    generation: Generation
    game: Game
    encounter: EnemyEncountered


@dataclass(frozen=True)
class EnterExploration:
    generation: Generation
    game: Game


@dataclass(frozen=True)
class EnterSkillTree:
    game: Game


type SceneTransition = EnterCombat | EnterExploration | EnterSkillTree


class Scene(Protocol):
    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None: ...
    def update(self, dt: float) -> SceneTransition | None: ...
    def draw(self, surface: pygame.Surface) -> None: ...
