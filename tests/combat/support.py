from collections.abc import Callable, Sequence

from eye.combat.actions import ActionDefinition
from eye.combat.battle import Battle, PlayerTurnNeedsAction, TurnPhase
from eye.combat.events import BattleEvent


def unfold(battle: Battle, pick_action: Callable[[Sequence[ActionDefinition]], ActionDefinition]) -> list[BattleEvent]:
    """Drive `battle` to completion, calling `pick_action` once per player swing.

    Test/headless-only convenience over Battle's query/resolve seam (ADR 0008) -- not part of
    eye.combat's public surface.
    """
    events: list[BattleEvent] = []
    while not battle.is_over:
        while battle.turn_phase in (TurnPhase.AWAITING_QUERY, TurnPhase.AWAITING_PLAYER_ACTION):
            query = battle.query_player_turn()
            if isinstance(query, PlayerTurnNeedsAction):
                events.extend(query.pre_turn_events)
                events.extend(battle.resolve_player_turn(pick_action(query.available)))
            else:
                events.extend(query.events)
                break
        if battle.is_over:
            break
        events.extend(battle.resolve_enemy_turn())
    return events
