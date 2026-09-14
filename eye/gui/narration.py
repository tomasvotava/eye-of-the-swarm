"""NarrationQueue: a FIFO of message+subtitle entries a scene holds to speak to the player at
scripted first-playthrough moments (PROJECT_BRIEF.md §9.8). Presentation-only -- no domain
involvement, no rendering commitment beyond `draw_narration` below. Whoever holds the queue owns
feeding it `dismiss()` from its own `handle_pygame_event`; this module makes no assumption about
which input counts as "continue".

NarrationTrigger/NarrationTriggers add the bookkeeping on top: which of the 8 scripted moments
have already been shown, so a scene can ask to fire one unconditionally and get a silent no-op if
it already has. 7 of the 8 are first-playthrough beats, remembered for a save file forever via
`load_seen_triggers`/`persist_seen_triggers` (GameDriver owns calling these, at the same
checkpoints it already persists the rest of the save); FIRST_SEED_READY is a standing reminder
instead, deliberately excluded so it re-shows every generation.
"""

import json
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum, auto

import pygame
import pygame.typing

from eye.gui.fonts.fonts import GameFont, get_font
from eye.persistence.port import SaveStore

# Ceilings, not fixed sizes: _fitted_font drops below them when a line won't fit the column.
_MESSAGE_FONT_SIZE = 32
_SUBTITLE_FONT_SIZE = 16
# Floor for the shrink-to-fit search: below this the text fits its column but can't be read.
_MIN_FONT_SIZE = 10
_GAP = 8
_TEXT_COLOR: pygame.typing.ColorLike = "white"
# Dims whatever the overlay lands on. Black, so it leaves no edge against the black background.
_BACKDROP_COLOR: pygame.typing.ColorLike = (0, 0, 0, 200)


@dataclass(frozen=True, slots=True)
class NarrationEntry:
    """One queued line: a main message plus a smaller qualifying subtitle."""

    message: str
    subtitle: str

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("a narration entry's message must not be blank")


class NarrationQueue:
    """FIFO of `NarrationEntry`. `is_active`/`current` tell a scene what to draw (if anything);
    `dismiss` moves to the next queued entry, or clears when the queue empties."""

    def __init__(self) -> None:
        self._entries: deque[NarrationEntry] = deque()

    def enqueue(self, message: str, subtitle: str) -> None:
        self._entries.append(NarrationEntry(message, subtitle))

    @property
    def is_active(self) -> bool:
        return bool(self._entries)

    @property
    def current(self) -> NarrationEntry | None:
        return self._entries[0] if self._entries else None

    def dismiss(self) -> None:
        if self._entries:
            self._entries.popleft()


class NarrationTrigger(Enum):
    """The 8 scripted moments a scene can narrate (PROJECT_BRIEF.md §9.8) -- one member per
    trigger point, independent of which scene ends up firing it. FIRST_SEED_READY is a per-life
    reminder; the other 7 are first-playthrough beats, shown once for a save file's whole
    lifetime (see `_PERSISTED_TRIGGERS`)."""

    FIRST_EXPLORATION = auto()
    FIRST_SEED_READY = auto()
    FIRST_PICKUP = auto()
    FIRST_BATTLE = auto()
    FIRST_ATTACK = auto()
    FIRST_METER_FULL = auto()
    FIRST_DEATH = auto()
    FIRST_PROXIMITY_FALLOFF = auto()


# Every trigger except FIRST_SEED_READY: that one is a standing "here's how you plant" reminder,
# not a once-ever story beat, so it must re-fire every generation regardless of save-file history.
_PERSISTED_TRIGGERS = frozenset(NarrationTrigger) - {NarrationTrigger.FIRST_SEED_READY}


@dataclass(slots=True)
class NarrationTriggers:
    """Owns a `NarrationQueue` plus which `NarrationTrigger`s have already fired this generation.
    One instance is shared by `GameDriver` across every scene reconstruction in a generation's
    lifetime (a fresh `Generation` gets a fresh instance, via `for_generation()`), so `fire()` is a
    no-op the second time a trigger is asked for -- callers need not track "have I already shown
    this" themselves."""

    queue: NarrationQueue = field(default_factory=NarrationQueue)
    _seen: set[NarrationTrigger] = field(default_factory=set)

    @classmethod
    def for_generation(cls, persisted_seen: Iterable[NarrationTrigger] = ()) -> NarrationTriggers:
        """A fresh generation's triggers, pre-seeded with whichever first-playthrough triggers
        this save file has already shown (`load_seen_triggers`). Filters to `_PERSISTED_TRIGGERS`
        even if `persisted_seen` carries FIRST_SEED_READY -- that one always starts unseen."""
        return cls(_seen=set(persisted_seen) & _PERSISTED_TRIGGERS)

    def fire(self, trigger: NarrationTrigger, message: str, subtitle: str) -> None:
        if trigger in self._seen:
            return
        self._seen.add(trigger)
        self.queue.enqueue(message, subtitle)

    @property
    def persisted_seen(self) -> frozenset[NarrationTrigger]:
        """The subset of this generation's `_seen` triggers a save file should remember forever.
        GameDriver folds this into its own running set and writes it out via
        `persist_seen_triggers` at the same checkpoints it already persists the rest of the save.
        """
        return frozenset(self._seen) & _PERSISTED_TRIGGERS


def load_seen_triggers(store: SaveStore) -> frozenset[NarrationTrigger]:
    """The `NarrationTrigger`s a save file has already shown permanently, read from `store`
    (`save.narration_store_for_slot()`). Missing or unreadable data reads as "nothing shown yet"
    rather than raising -- a narration replaying once is a far smaller cost than blocking boot on
    a corrupt sidecar file for a presentation-only concern.
    """
    raw = store.load()
    if raw is None:
        return frozenset()
    try:
        names = json.loads(raw)
    except json.JSONDecodeError:
        return frozenset()
    if not isinstance(names, list):
        return frozenset()
    return frozenset(
        NarrationTrigger[name] for name in names if isinstance(name, str) and name in NarrationTrigger.__members__
    )


def persist_seen_triggers(store: SaveStore, seen: frozenset[NarrationTrigger]) -> None:
    store.save(json.dumps(sorted(trigger.name for trigger in seen)))


def _fitted_font(texts: Sequence[str], max_font_size: int, max_width: int) -> pygame.font.Font:
    """The largest Ithaca font up to `max_font_size` rendering every one of `texts` within
    `max_width`, bottoming out at `_MIN_FONT_SIZE` even if that no longer fits."""
    for size in range(max_font_size, _MIN_FONT_SIZE, -1):
        font = get_font(GameFont.ITHACA, size)
        if all(font.size(text)[0] <= max_width for text in texts):
            return font
    return get_font(GameFont.ITHACA, min(max_font_size, _MIN_FONT_SIZE))


def _wrapped_lines(text: str, font: pygame.font.Font, max_width: int) -> list[str]:
    """`text` greedily broken into lines that each render within `max_width`. A word wider than the
    budget overruns its own line; callers size the font against the words first."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and font.size(candidate)[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def draw_narration(surface: pygame.Surface, entry: NarrationEntry, *, center_x: int, column_width: int) -> None:
    """Draw `entry` as message over subtitle, over a backdrop panel, centered on `center_x` and on
    the surface's own vertical middle. `column_width` is the width budget both lines are typeset
    into; anchoring is the caller's decision, mirroring `card.draw_card`."""
    message_font = _fitted_font(entry.message.split(), _MESSAGE_FONT_SIZE, column_width)
    message_lines = [
        message_font.render(line, True, _TEXT_COLOR)
        for line in _wrapped_lines(entry.message, message_font, column_width)
    ]
    subtitle_font = _fitted_font(entry.subtitle.split(), _SUBTITLE_FONT_SIZE, column_width)
    subtitle_lines = [
        subtitle_font.render(line, True, _TEXT_COLOR)
        for line in _wrapped_lines(entry.subtitle, subtitle_font, column_width)
    ]

    message_height = sum(line.height for line in message_lines)
    subtitle_height = sum(line.height for line in subtitle_lines)
    block_height = message_height + subtitle_height + _GAP
    block_width = max(line.width for line in (*message_lines, *subtitle_lines))
    top = surface.get_height() // 2 - block_height // 2

    backdrop = pygame.Rect(0, 0, block_width + _GAP * 2, block_height + _GAP * 2)
    backdrop.center = (center_x, top + block_height // 2)
    # Blitted from an SRCALPHA surface: pygame.draw would write the alpha instead of blending.
    panel = pygame.Surface(backdrop.size, pygame.SRCALPHA)
    panel.fill(_BACKDROP_COLOR)
    surface.blit(panel, backdrop.topleft)

    message_top = top
    for line in message_lines:
        surface.blit(line, (center_x - line.width // 2, message_top))
        message_top += line.height
    subtitle_top = message_top + _GAP
    for line in subtitle_lines:
        surface.blit(line, (center_x - line.width // 2, subtitle_top))
        subtitle_top += line.height
