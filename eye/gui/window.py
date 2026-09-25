"""window.py: applies a `WindowScale` to the game's single `SCALED` display window (ADR 0017). The
display is a process-global singleton already, so this module works on it directly rather than
through anything `App` or a scene owns. Under emscripten the browser owns the canvas size and
every call here is a no-op.
"""

from __future__ import annotations

import sys
import warnings
from collections.abc import Sequence

import pygame

from eye.persistence.settings import WindowScale

_MULTIPLIERS: dict[WindowScale, int] = {
    WindowScale.X1: 1,
    WindowScale.X2: 2,
    WindowScale.X3: 3,
    WindowScale.X4: 4,
}

# The size SDL chose for the SCALED window at boot, which AUTO restores. Captured on the first
# apply_window_scale() call, which run() makes before any resize.
_auto_size: tuple[int, int] | None = None


def window_scaling_supported() -> bool:
    return sys.platform != "emscripten"


def available_window_scales(logical_size: tuple[int, int], desktop_size: tuple[int, int]) -> tuple[WindowScale, ...]:
    """Every scale worth offering on a `desktop_size` display, in `WindowScale` order: `AUTO`,
    `FULLSCREEN`, and each multiple of `logical_size` that fits the desktop."""
    return tuple(
        scale
        for scale in WindowScale
        if scale not in _MULTIPLIERS
        or (
            logical_size[0] * _MULTIPLIERS[scale] <= desktop_size[0]
            and logical_size[1] * _MULTIPLIERS[scale] <= desktop_size[1]
        )
    )


def desktop_window_scales() -> tuple[WindowScale, ...]:
    """`available_window_scales` for the display surface on the primary desktop; nothing where
    scaling is unsupported or no display mode is set yet."""
    surface = pygame.display.get_surface() if window_scaling_supported() else None
    if surface is None:
        return ()
    return available_window_scales(surface.get_size(), pygame.display.get_desktop_sizes()[0])


def effective_window_scale(saved: WindowScale, available: Sequence[WindowScale]) -> WindowScale:
    """`saved`, unless this desktop can't offer it (e.g. a saved `X4` on a smaller monitor)."""
    return saved if saved in available else WindowScale.AUTO


def apply_window_scale(scale: WindowScale) -> None:
    """Resizes the display window to `scale`; `Xn` multiplies the display surface's logical size."""
    global _auto_size
    surface = pygame.display.get_surface() if window_scaling_supported() else None
    if surface is None:
        return
    window = _display_window()
    if _auto_size is None:
        _auto_size = window.size
    if scale is WindowScale.FULLSCREEN:
        window.set_fullscreen(desktop=True)
        return
    window.set_windowed()
    if scale is WindowScale.AUTO:
        window.size = _auto_size
    else:
        width, height = surface.get_size()
        window.size = (width * _MULTIPLIERS[scale], height * _MULTIPLIERS[scale])
    window.position = pygame.WINDOWPOS_CENTERED


def _display_window() -> pygame.Window:
    # Deprecated in pygame-ce 2.5.8, but the only way to resize a SCALED display-module window:
    # set_mode() can't pick the scale (ADR 0017 records the accepted risk).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return pygame.Window.from_display_module()
