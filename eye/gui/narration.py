"""NarrationQueue: a FIFO of message+subtitle entries a scene holds to speak to the player at
scripted first-playthrough moments (PROJECT_BRIEF.md §9.8). Presentation-only -- no domain
involvement, no rendering commitment beyond `draw_narration` below. Whoever holds the queue owns
feeding it `dismiss()` from its own `handle_pygame_event`; this module makes no assumption about
which input counts as "continue".

NarrationTrigger/NarrationTriggers add the once-per-generation bookkeeping on top: which of the 8
scripted moments have already been shown, so a scene can ask to fire one unconditionally and get a
silent no-op if it already has.
"""

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, auto

import pygame
import pygame.typing

from eye.gui.fonts.fonts import GameFont, get_font

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
    """The 8 scripted first-playthrough moments a fresh generation re-sees (PROJECT_BRIEF.md
    §9.8) -- one member per trigger point, independent of which scene ends up firing it."""

    FIRST_EXPLORATION = auto()
    FIRST_SEED_READY = auto()
    FIRST_PICKUP = auto()
    FIRST_BATTLE = auto()
    FIRST_ATTACK = auto()
    FIRST_METER_FULL = auto()
    FIRST_DEATH = auto()
    FIRST_PROXIMITY_FALLOFF = auto()


@dataclass(slots=True)
class NarrationTriggers:
    """Owns a `NarrationQueue` plus which `NarrationTrigger`s have already fired this generation.
    One instance is shared by `GameDriver` across every scene reconstruction in a generation's
    lifetime (a fresh `Generation` gets a fresh instance), so `fire()` is a no-op the second time a
    trigger is asked for -- callers need not track "have I already shown this" themselves."""

    queue: NarrationQueue = field(default_factory=NarrationQueue)
    _seen: set[NarrationTrigger] = field(default_factory=set)

    def fire(self, trigger: NarrationTrigger, message: str, subtitle: str) -> None:
        if trigger in self._seen:
            return
        self._seen.add(trigger)
        self.queue.enqueue(message, subtitle)


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
