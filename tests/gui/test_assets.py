import pygame

from eye.gui.assets import PLACEHOLDER_SPRITE_SIZE, SpriteAtlas, SpriteKey, build_placeholder_atlas


def test_build_placeholder_atlas_has_a_surface_for_every_sprite_key() -> None:
    atlas = build_placeholder_atlas()

    for key in SpriteKey:
        surface = atlas.get(key)
        assert isinstance(surface, pygame.Surface)
        assert surface.get_size() == (PLACEHOLDER_SPRITE_SIZE, PLACEHOLDER_SPRITE_SIZE)


def test_build_placeholder_atlas_creates_a_distinct_surface_per_key() -> None:
    atlas = build_placeholder_atlas()

    surfaces = [atlas.get(key) for key in SpriteKey]

    assert len({id(surface) for surface in surfaces}) == len(surfaces)


def test_sprite_atlas_get_returns_the_wrapped_surface() -> None:
    surface = pygame.Surface((4, 4))
    atlas = SpriteAtlas({SpriteKey.PLAYER: surface})

    assert atlas.get(SpriteKey.PLAYER) is surface
