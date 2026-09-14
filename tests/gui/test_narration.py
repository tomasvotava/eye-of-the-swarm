import pygame
import pygame.typing
import pytest

from eye.gui.narration import (
    _GAP,
    NarrationEntry,
    NarrationQueue,
    NarrationTrigger,
    NarrationTriggers,
    _fitted_font,
    _wrapped_lines,
    draw_narration,
)

# A colour the overlay never paints, so colorkeying it leaves exactly the drawn pixels. Not black:
# the overlay's own backdrop panel is translucent black.
_UNDRAWN: pygame.typing.ColorLike = "navy"
_SURFACE_SIZE = (800, 600)
_MESSAGE = "You venture from your swarm's land into biomes unknown"
_SUBTITLE = "press -> to venture further"


def test_a_fresh_queue_is_inactive_with_no_current_entry() -> None:
    queue = NarrationQueue()

    assert queue.is_active is False
    assert queue.current is None


def test_enqueue_makes_the_queue_active_with_that_entry_current() -> None:
    queue = NarrationQueue()

    queue.enqueue(_MESSAGE, _SUBTITLE)

    assert queue.is_active is True
    assert queue.current == NarrationEntry(message=_MESSAGE, subtitle=_SUBTITLE)


def test_entries_are_served_in_the_order_they_were_enqueued() -> None:
    queue = NarrationQueue()

    queue.enqueue("first", "a")
    queue.enqueue("second", "b")

    assert queue.current == NarrationEntry(message="first", subtitle="a")
    queue.dismiss()
    assert queue.current == NarrationEntry(message="second", subtitle="b")


def test_dismissing_the_last_entry_clears_the_queue() -> None:
    queue = NarrationQueue()
    queue.enqueue(_MESSAGE, _SUBTITLE)

    queue.dismiss()

    assert queue.is_active is False
    assert queue.current is None


def test_dismissing_an_empty_queue_is_a_no_op() -> None:
    queue = NarrationQueue()

    queue.dismiss()  # must not raise

    assert queue.is_active is False


def _drawn_rect(*, center_x: int, column_width: int) -> pygame.Rect:
    surface = pygame.Surface(_SURFACE_SIZE)
    surface.fill(_UNDRAWN)
    draw_narration(
        surface,
        NarrationEntry(message=_MESSAGE, subtitle=_SUBTITLE),
        center_x=center_x,
        column_width=column_width,
    )
    surface.set_colorkey(_UNDRAWN)  # so get_bounding_rect() measures only what was drawn
    return surface.get_bounding_rect()


def test_the_drawn_block_is_centered_on_the_given_center_x_within_the_given_column_width() -> None:
    wide = _drawn_rect(center_x=400, column_width=700)
    narrow = _drawn_rect(center_x=610, column_width=90)

    assert wide.size != (0, 0)  # an empty rect would satisfy every check below
    assert wide.centerx == 400
    assert narrow.centerx == 610
    assert narrow.width <= 90 + _GAP * 2  # the panel's own inset is all that may exceed the budget


def test_a_longer_message_produces_a_taller_block_than_a_short_one() -> None:
    short = _drawn_rect(center_x=400, column_width=700)

    surface = pygame.Surface(_SURFACE_SIZE)
    surface.fill(_UNDRAWN)
    draw_narration(
        surface,
        NarrationEntry(message=_MESSAGE + " " + _MESSAGE, subtitle=_SUBTITLE),
        center_x=400,
        column_width=200,
    )
    surface.set_colorkey(_UNDRAWN)
    long = surface.get_bounding_rect()

    assert long.height > short.height


def test_fitted_font_shrinks_below_the_ceiling_to_stay_within_the_column() -> None:
    wide_column = _fitted_font((_MESSAGE,), 32, 2000)
    narrow_column = _fitted_font((_MESSAGE,), 32, 100)

    assert narrow_column.point_size < wide_column.point_size


def test_fitted_font_bottoms_out_at_the_floor_rather_than_shrinking_further() -> None:
    font = _fitted_font(("an uncomfortably long word that will never fit",), 32, 1)

    assert font.point_size == 10  # _MIN_FONT_SIZE, the fallback once nothing in range fits


def test_wrapped_lines_breaks_text_to_fit_the_width_without_dropping_words() -> None:
    font = pygame.font.Font(None, 20)

    lines = _wrapped_lines("one two three four five", font, font.size("one two")[0] + 1)

    assert " ".join(lines).split() == ["one", "two", "three", "four", "five"]
    assert len(lines) > 1


def test_an_entry_with_a_blank_message_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        NarrationEntry(message="   ", subtitle="a subtitle")


def test_firing_a_trigger_enqueues_it_on_the_owned_queue() -> None:
    triggers = NarrationTriggers()

    triggers.fire(NarrationTrigger.FIRST_EXPLORATION, _MESSAGE, _SUBTITLE)

    assert triggers.queue.current == NarrationEntry(message=_MESSAGE, subtitle=_SUBTITLE)


def test_firing_the_same_trigger_twice_enqueues_only_once() -> None:
    triggers = NarrationTriggers()

    triggers.fire(NarrationTrigger.FIRST_DEATH, "first", "a")
    triggers.fire(NarrationTrigger.FIRST_DEATH, "second", "b")

    assert triggers.queue.current == NarrationEntry(message="first", subtitle="a")
    triggers.queue.dismiss()
    assert triggers.queue.is_active is False


def test_firing_two_different_triggers_both_enqueue() -> None:
    triggers = NarrationTriggers()

    triggers.fire(NarrationTrigger.FIRST_EXPLORATION, "first", "a")
    triggers.fire(NarrationTrigger.FIRST_BATTLE, "second", "b")

    assert triggers.queue.current == NarrationEntry(message="first", subtitle="a")
    triggers.queue.dismiss()
    assert triggers.queue.current == NarrationEntry(message="second", subtitle="b")
