import pygame
import pygame.typing
import pytest

from eye.gui.narration import (
    _GAP,
    NarrationEntry,
    NarrationQueue,
    NarrationTrigger,
    NarrationTriggers,
    RecurringNarration,
    _fitted_font,
    _wrapped_lines,
    draw_narration,
    load_seen_triggers,
    persist_seen_triggers,
)
from tests.persistence.doubles import FakeSaveStore

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


def test_fire_sequence_enqueues_every_entry_in_order() -> None:
    triggers = NarrationTriggers()

    triggers.fire_sequence(NarrationTrigger.INTRO_LORE, [("first", "a"), ("second", "b")])

    assert triggers.queue.current == NarrationEntry(message="first", subtitle="a")
    triggers.queue.dismiss()
    assert triggers.queue.current == NarrationEntry(message="second", subtitle="b")


def test_fire_sequence_is_a_no_op_once_its_trigger_has_already_fired() -> None:
    triggers = NarrationTriggers()
    triggers.fire_sequence(NarrationTrigger.INTRO_LORE, [("first", "a")])
    triggers.queue.dismiss()

    triggers.fire_sequence(NarrationTrigger.INTRO_LORE, [("second", "b")])

    assert triggers.queue.is_active is False


def test_persisted_seen_reflects_a_fired_trigger() -> None:
    triggers = NarrationTriggers()

    triggers.fire(NarrationTrigger.FIRST_DEATH, _MESSAGE, _SUBTITLE)

    assert triggers.persisted_seen == frozenset({NarrationTrigger.FIRST_DEATH})


def test_persisted_seen_never_holds_a_recurring_announcement() -> None:
    triggers = NarrationTriggers()

    triggers.announce_recurring(
        RecurringNarration.SEED_READY, armed=True, level=True, message=_MESSAGE, subtitle=_SUBTITLE
    )

    assert triggers.persisted_seen == frozenset()


def test_for_generation_pre_seeds_persisted_triggers_as_already_seen() -> None:
    triggers = NarrationTriggers.for_generation({NarrationTrigger.FIRST_DEATH})

    triggers.fire(NarrationTrigger.FIRST_DEATH, _MESSAGE, _SUBTITLE)

    assert triggers.queue.is_active is False


def test_announce_recurring_enqueues_once_per_rise_of_its_level() -> None:
    triggers = NarrationTriggers()

    for _ in range(3):
        triggers.announce_recurring(
            RecurringNarration.TOO_FAR_FROM_HOME, armed=True, level=True, message=_MESSAGE, subtitle=_SUBTITLE
        )

    assert triggers.queue.current == NarrationEntry(message=_MESSAGE, subtitle=_SUBTITLE)
    triggers.queue.dismiss()
    assert triggers.queue.is_active is False


def test_announce_recurring_re_fires_after_its_level_falls() -> None:
    triggers = NarrationTriggers()
    beat = RecurringNarration.TOO_FAR_FROM_HOME
    triggers.announce_recurring(beat, armed=True, level=True, message="first", subtitle="a")
    triggers.queue.dismiss()

    triggers.announce_recurring(beat, armed=False, level=False, message="first", subtitle="a")
    triggers.announce_recurring(beat, armed=True, level=True, message="second", subtitle="b")

    assert triggers.queue.current == NarrationEntry(message="second", subtitle="b")


def test_announce_recurring_neither_fires_nor_unlatches_while_disarmed_at_level() -> None:
    triggers = NarrationTriggers()
    beat = RecurringNarration.SEED_READY

    triggers.announce_recurring(beat, armed=False, level=True, message=_MESSAGE, subtitle=_SUBTITLE)
    assert triggers.queue.is_active is False

    triggers.announce_recurring(beat, armed=True, level=True, message=_MESSAGE, subtitle=_SUBTITLE)
    triggers.queue.dismiss()
    triggers.announce_recurring(beat, armed=False, level=True, message=_MESSAGE, subtitle=_SUBTITLE)
    triggers.announce_recurring(beat, armed=True, level=True, message=_MESSAGE, subtitle=_SUBTITLE)

    assert triggers.queue.is_active is False


def test_recurring_announcements_latch_independently_of_each_other() -> None:
    triggers = NarrationTriggers()

    triggers.announce_recurring(RecurringNarration.SEED_READY, armed=True, level=True, message="seed", subtitle="a")
    triggers.announce_recurring(
        RecurringNarration.TOO_FAR_FROM_HOME, armed=True, level=True, message="far", subtitle="b"
    )

    assert triggers.queue.current == NarrationEntry(message="seed", subtitle="a")
    triggers.queue.dismiss()
    assert triggers.queue.current == NarrationEntry(message="far", subtitle="b")


def test_load_seen_triggers_from_an_empty_store_is_empty() -> None:
    assert load_seen_triggers(FakeSaveStore(data=None)) == frozenset()


def test_load_seen_triggers_from_corrupt_data_is_empty() -> None:
    assert load_seen_triggers(FakeSaveStore(data="not json")) == frozenset()


def test_load_seen_triggers_from_a_non_list_payload_is_empty() -> None:
    assert load_seen_triggers(FakeSaveStore(data='{"not": "a list"}')) == frozenset()


def test_load_seen_triggers_ignores_an_unknown_trigger_name() -> None:
    store = FakeSaveStore(data='["FIRST_DEATH", "SOME_FUTURE_TRIGGER"]')

    assert load_seen_triggers(store) == frozenset({NarrationTrigger.FIRST_DEATH})


def test_load_seen_triggers_ignores_retired_recurring_trigger_names() -> None:
    store = FakeSaveStore(data='["FIRST_DEATH", "FIRST_PROXIMITY_FALLOFF", "FIRST_SEED_READY"]')

    assert load_seen_triggers(store) == frozenset({NarrationTrigger.FIRST_DEATH})


def test_persist_then_load_round_trips_the_seen_set() -> None:
    store = FakeSaveStore()
    seen = frozenset({NarrationTrigger.FIRST_DEATH, NarrationTrigger.FIRST_BATTLE})

    persist_seen_triggers(store, seen)

    assert load_seen_triggers(store) == seen
