import asyncio

import pygame
import pygame.typing

MOVE_SPEED = 300
MAX_FPS = 60


class TestGame:
    def __init__(self) -> None:
        self._running = False
        self._screen: pygame.Surface | None = None
        self._clock: pygame.Clock | None = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def screen(self) -> pygame.Surface:
        if self._screen is None:
            raise RuntimeError("Initialize pygame first")
        return self._screen

    @property
    def clock(self) -> pygame.Clock:
        if self._clock is None:
            raise RuntimeError("Initialize pygame first")
        return self._clock

    def init_pygame(self) -> None:
        pygame.init()
        self._screen = pygame.display.set_mode((1280, 720))
        self._clock = pygame.time.Clock()

    async def run(self) -> None:
        self.init_pygame()

        self._running = True
        dt: float = 0
        player_pos = pygame.Vector2(self.screen.get_width() / 2, self.screen.get_height() / 2)

        while self._running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
            self.screen.fill("purple")
            pygame.draw.circle(self.screen, "red", player_pos, 40)

            keys = pygame.key.get_pressed()
            move = pygame.Vector2(keys[pygame.K_d] - keys[pygame.K_a], keys[pygame.K_s] - keys[pygame.K_w])
            if move.length_squared() > 0:
                player_pos += move.normalize() * MOVE_SPEED * dt
            pygame.display.flip()
            dt = self.clock.tick(MAX_FPS) / 1000
            await asyncio.sleep(0)


def main() -> None:
    game = TestGame()
    asyncio.run(game.run())


if __name__ == "__main__":
    main()
