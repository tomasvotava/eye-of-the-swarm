import pygame

from eye.gui.scene import EnterSkillTree, Scene, SceneTransition
from eye.session.game import Game
from tests.session.doubles import ScriptedEncounterRandom


class _StubScene:
    def __init__(self) -> None:
        self.handled_pygame_events: list[pygame.event.Event] = []
        self.updates: list[float] = []

    def handle_pygame_event(self, pygame_event: pygame.event.Event) -> None:
        self.handled_pygame_events.append(pygame_event)

    def update(self, dt: float) -> SceneTransition | None:
        self.updates.append(dt)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")


def test_stub_scene_satisfies_scene_protocol() -> None:
    scene: Scene = _StubScene()

    event = pygame.event.Event(pygame.QUIT)
    scene.handle_pygame_event(event)
    next_scene = scene.update(0.016)
    scene.draw(pygame.Surface((1, 1)))

    assert isinstance(scene, _StubScene)
    assert scene.handled_pygame_events == [event]
    assert scene.updates == [0.016]
    assert next_scene is None


def test_update_can_signal_a_scene_transition() -> None:
    class _TransitioningScene(_StubScene):
        def update(self, dt: float) -> SceneTransition | None:
            super().update(dt)
            return EnterSkillTree(game=Game(ScriptedEncounterRandom(())))

    next_transition = _TransitioningScene().update(0.016)

    assert isinstance(next_transition, EnterSkillTree)


def test_headless_surface_construction() -> None:
    surface = pygame.Surface((64, 48))

    assert surface.get_size() == (64, 48)
