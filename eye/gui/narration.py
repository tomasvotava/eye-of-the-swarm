"""NarrationQueue: a FIFO of message+subtitle entries a scene holds to speak to the player at
scripted first-playthrough moments (PROJECT_BRIEF.md §9.8). Presentation-only -- no domain
involvement, no rendering commitment beyond `draw_narration` below. Whoever holds the queue owns
feeding it `dismiss()` from its own `handle_pygame_event`; this module makes no assumption about
which input counts as "continue".

NarrationTrigger/NarrationTriggers add the bookkeeping on top: which of the 7 first-playthrough
moments have already been shown, so a scene can ask to fire one unconditionally and get a silent
no-op if it already has. They are remembered for a save file forever via
`load_seen_triggers`/`persist_seen_triggers` (GameDriver owns calling these, at the same
checkpoints it already persists the rest of the save). RecurringNarration covers the alerts that
are announced again every time their condition comes back, never persisted.
"""

from __future__ import annotations

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
    """The 7 first-playthrough moments a scene can narrate (PROJECT_BRIEF.md §9.8) -- one member
    per trigger point, independent of which scene ends up firing it, each shown once for a save
    file's whole lifetime."""

    INTRO_LORE = auto()
    FIRST_EXPLORATION = auto()
    FIRST_PICKUP = auto()
    FIRST_BATTLE = auto()
    FIRST_ATTACK = auto()
    FIRST_METER_FULL = auto()
    FIRST_DEATH = auto()


class RecurringNarration(Enum):
    """Alerts announced each time their condition comes true (PROJECT_BRIEF.md §9.8), via
    `NarrationTriggers.announce_recurring`. Never persisted to a save file."""

    TOO_FAR_FROM_HOME = auto()
    SEED_READY = auto()


@dataclass(slots=True)
class NarrationTriggers:
    """Owns a `NarrationQueue` plus which `NarrationTrigger`s have already fired and which
    `RecurringNarration`s are currently latched. One instance is shared by `GameDriver` across
    every scene reconstruction in a generation's lifetime (a fresh `Generation` gets a fresh
    instance, via `for_generation()`), so `fire()` is a no-op the second time a trigger is asked
    for, and a rebuilt scene doesn't re-announce a recurring alert whose condition still holds --
    callers need not track "have I already shown this" themselves."""

    queue: NarrationQueue = field(default_factory=NarrationQueue)
    _seen: set[NarrationTrigger] = field(default_factory=set)
    _latched: set[RecurringNarration] = field(default_factory=set)

    @classmethod
    def for_generation(cls, persisted_seen: Iterable[NarrationTrigger] = ()) -> NarrationTriggers:
        """A fresh generation's triggers, pre-seeded with whichever first-playthrough triggers
        this save file has already shown (`load_seen_triggers`), and every recurring alert
        unlatched."""
        return cls(_seen=set(persisted_seen))

    def fire(self, trigger: NarrationTrigger, message: str, subtitle: str) -> None:
        self.fire_sequence(trigger, [(message, subtitle)])

    def fire_sequence(self, trigger: NarrationTrigger, entries: Sequence[tuple[str, str]]) -> None:
        """Like `fire`, but queues several entries at once behind a single once-per-trigger gate --
        for a multi-line beat (e.g. INTRO_LORE) that should read as one sequence, not several
        independently-gated triggers."""
        if trigger in self._seen:
            return
        self._seen.add(trigger)
        for message, subtitle in entries:
            self.queue.enqueue(message, subtitle)

    def announce_recurring(
        self, beat: RecurringNarration, *, armed: bool, level: bool, message: str, subtitle: str
    ) -> None:
        """Enqueue `beat` once per rise of its condition; safe to call every frame. `level` is
        whether the condition holds: while it's false, `beat` unlatches so its next rise announces
        again. `armed` is whether announcing is allowed right now (it implies `level`); a disarmed
        frame with `level` still true neither announces nor unlatches."""
        if not level:
            self._latched.discard(beat)
            return
        if armed and beat not in self._latched:
            self._latched.add(beat)
            self.queue.enqueue(message, subtitle)

    @property
    def persisted_seen(self) -> frozenset[NarrationTrigger]:
        """This generation's `_seen` triggers, which a save file remembers forever. GameDriver folds
        this into its own running set and writes it out via `persist_seen_triggers` at the same
        checkpoints it already persists the rest of the save."""
        return frozenset(self._seen)


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
