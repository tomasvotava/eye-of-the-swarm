from collections.abc import Iterator, Sequence

from rich.console import Console

from eye.combat.actions import ActionDefinition
from eye.combat.stats import Combatant
from eye.tui import render
from eye.tui._input import next_line, parse_bounded_index


class TUIActionChooser:
    def __init__(self, console: Console, input_source: Iterator[str]) -> None:
        self._console = console
        self._input_source = input_source

    def choose(self, actor: Combatant, opponent: Combatant, available: Sequence[ActionDefinition]) -> ActionDefinition:
        render.combatant_state(self._console, actor)
        render.combatant_state(self._console, opponent)
        for index, action in enumerate(available, start=1):
            self._console.print(f"{index}) {_action_label(action)}", markup=False)

        while True:
            chosen_index = parse_bounded_index(next_line(self._input_source, "TUIActionChooser"), len(available))
            if chosen_index is not None:
                return available[chosen_index]
            self._console.print(f"Enter a number between 1 and {len(available)}.")


def _action_label(action: ActionDefinition) -> str:
    return action.name or action.kind.name.replace("_", " ").title()
