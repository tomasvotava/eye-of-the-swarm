import pygame

from eye.gui.scene import Scene


class _StubScene:
    def __init__(self) -> None:
        self.handled_events: list[pygame.event.Event] = []
        self.updates: list[float] = []

    def handle_event(self, event: pygame.event.Event) -> None:
        self.handled_events.append(event)

    def update(self, dt: float) -> Scene | None:
        self.updates.append(dt)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        surface.fill("black")


def test_stub_scene_satisfies_scene_protocol() -> None:
    scene: Scene = _StubScene()

    event = pygame.event.Event(pygame.QUIT)
    scene.handle_event(event)
    next_scene = scene.update(0.016)
    scene.draw(pygame.Surface((1, 1)))

    assert isinstance(scene, _StubScene)
    assert scene.handled_events == [event]
    assert scene.updates == [0.016]
    assert next_scene is None


def test_update_can_signal_a_scene_transition() -> None:
    class _TransitioningScene(_StubScene):
        def update(self, dt: float) -> Scene | None:
            super().update(dt)
            return _StubScene()

    next_scene = _TransitioningScene().update(0.016)

    assert isinstance(next_scene, _StubScene)


def test_headless_surface_construction() -> None:
    surface = pygame.Surface((64, 48))

    assert surface.get_size() == (64, 48)
