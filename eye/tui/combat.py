from collections.abc import Iterator, Sequence

from rich.console import Console

from eye.combat.actions import ActionDefinition
from eye.combat.battle import PlayerTurnNeedsAction, TurnPhase
from eye.combat.stats import Combatant
from eye.exploration.events import EnemyEncountered
from eye.session.generation import Generation
from eye.tui import render
from eye.tui._input import next_line, parse_bounded_index


def play_battle(
    console: Console, generation: Generation, encounter: EnemyEncountered, input_source: Iterator[str]
) -> None:
    battle = generation.start_battle(encounter)
    render.events(console, battle.start())

    while not battle.is_over:
        while battle.turn_phase in (TurnPhase.AWAITING_QUERY, TurnPhase.AWAITING_PLAYER_ACTION):
            query = battle.query_player_turn()
            if isinstance(query, PlayerTurnNeedsAction):
                render.events(console, query.pre_turn_events)
                action = _prompt_action(console, input_source, battle.player, battle.enemy, query.available)
                render.events(console, battle.resolve_player_turn(action))
            else:
                render.events(console, query.events)
                break
        if battle.is_over:
            break
        render.events(console, battle.resolve_enemy_turn())

    render.events(console, generation.finish_battle(battle))


def _prompt_action(
    console: Console,
    input_source: Iterator[str],
    player: Combatant,
    enemy: Combatant,
    available: Sequence[ActionDefinition],
) -> ActionDefinition:
    render.combatant_state(console, player)
    render.combatant_state(console, enemy)
    for index, action in enumerate(available, start=1):
        console.print(f"{index}) {_action_label(action)}", markup=False)

    while True:
        chosen_index = parse_bounded_index(next_line(input_source, "combat"), len(available))
        if chosen_index is not None:
            return available[chosen_index]
        console.print(f"Enter a number between 1 and {len(available)}.")


def _action_label(action: ActionDefinition) -> str:
    return action.name or action.kind.name.replace("_", " ").title()
