import sys
from dataclasses import dataclass, field

import pygame
import pytest

from eye.gui import window
from eye.gui.window import available_window_scales, effective_window_scale
from eye.persistence.settings import WindowScale


def test_available_window_scales_offers_only_multiples_that_fit_the_desktop() -> None:
    assert available_window_scales((640, 480), (1920, 1080)) == (
        WindowScale.AUTO,
        WindowScale.X1,
        WindowScale.X2,
        WindowScale.FULLSCREEN,
    )


def test_available_window_scales_needs_both_dimensions_to_fit() -> None:
    assert WindowScale.X2 not in available_window_scales((640, 480), (1280, 959))
    assert WindowScale.X2 in available_window_scales((640, 480), (1280, 960))


def test_available_window_scales_always_offers_auto_and_fullscreen() -> None:
    assert available_window_scales((640, 480), (320, 240)) == (WindowScale.AUTO, WindowScale.FULLSCREEN)


@pytest.mark.parametrize(
    ("saved", "expected"),
    [
        (WindowScale.X2, WindowScale.X2),
        (WindowScale.X4, WindowScale.AUTO),
        (WindowScale.FULLSCREEN, WindowScale.FULLSCREEN),
    ],
)
def test_effective_window_scale_falls_back_to_auto_when_unavailable(saved: WindowScale, expected: WindowScale) -> None:
    available = (WindowScale.AUTO, WindowScale.X1, WindowScale.X2, WindowScale.FULLSCREEN)

    assert effective_window_scale(saved, available) is expected


@dataclass
class _FakeWindow:
    size: tuple[int, int] = (800, 600)
    position: object = None
    calls: list[str] = field(default_factory=list)

    def set_fullscreen(self, desktop: bool) -> None:
        self.calls.append(f"fullscreen(desktop={desktop})")

    def set_windowed(self) -> None:
        self.calls.append("windowed")


@pytest.fixture
def fake_window(monkeypatch: pytest.MonkeyPatch) -> _FakeWindow:
    fake = _FakeWindow()
    monkeypatch.setattr(window, "_display_window", lambda: fake)
    monkeypatch.setattr(window, "_auto_size", None)
    monkeypatch.setattr(pygame.display, "get_surface", lambda: pygame.Surface((640, 480)))
    return fake


def test_apply_window_scale_multiplies_the_logical_size_and_recentres(fake_window: _FakeWindow) -> None:
    window.apply_window_scale(WindowScale.X2)

    assert fake_window.size == (1280, 960)
    assert fake_window.position == pygame.WINDOWPOS_CENTERED
    assert fake_window.calls == ["windowed"]


def test_apply_window_scale_auto_restores_the_size_seen_on_the_first_call(fake_window: _FakeWindow) -> None:
    window.apply_window_scale(WindowScale.AUTO)
    window.apply_window_scale(WindowScale.X1)

    window.apply_window_scale(WindowScale.AUTO)

    assert fake_window.size == (800, 600)


def test_apply_window_scale_leaves_fullscreen_before_resizing(fake_window: _FakeWindow) -> None:
    window.apply_window_scale(WindowScale.FULLSCREEN)
    window.apply_window_scale(WindowScale.X1)

    assert fake_window.calls == ["fullscreen(desktop=True)", "windowed"]
    assert fake_window.size == (640, 480)


def test_apply_window_scale_is_a_no_op_under_emscripten(
    fake_window: _FakeWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "emscripten")

    window.apply_window_scale(WindowScale.X2)

    assert fake_window.size == (800, 600)
    assert fake_window.calls == []


def test_desktop_window_scales_is_empty_under_emscripten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "emscripten")

    assert window.desktop_window_scales() == ()
