from collections.abc import Iterator, Sequence

from rich.console import Console

from eye.combat.actions import ActionDefinition
from eye.combat.stats import Combatant
from eye.tui import render


class TUIActionChooser:
    def __init__(self, console: Console, input_source: Iterator[str]) -> None:
        self._console = console
        self._input_source = input_source

    def choose(self, actor: Combatant, opponent: Combatant, available: Sequence[ActionDefinition]) -> ActionDefinition:
        render.combatant_state(self._console, actor)
        render.combatant_state(self._console, opponent)
        for index, action in enumerate(available, start=1):
            self._console.print(f"{index}) {_action_label(action)}")

        while True:
            chosen_index = _parse_choice(self._next_input(), len(available))
            if chosen_index is not None:
                return available[chosen_index]
            self._console.print(f"Enter a number between 1 and {len(available)}.")

    def _next_input(self) -> str:
        try:
            return next(self._input_source)
        except StopIteration:
            raise RuntimeError("TUIActionChooser has no more input to consume") from None


def _action_label(action: ActionDefinition) -> str:
    return action.name or action.kind.name.replace("_", " ").title()


def _parse_choice(raw: str, option_count: int) -> int | None:
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    if not 1 <= value <= option_count:
        return None
    return value - 1
