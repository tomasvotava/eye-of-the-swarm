from collections.abc import Callable, Sequence

from eye.combat.actions import ActionDefinition
from eye.combat.battle import Battle, PlayerTurnNeedsAction, TurnPhase
from eye.combat.events import BattleEvent


def _assert_invariants(battle: Battle) -> None:
    """turn_phase/is_over/winner must always agree with each other and with which side, if any,
    is actually still alive -- checked after every query/resolve call so a state-machine
    regression fails at the exact step that caused it, not only once at the end of a battle."""
    if battle.is_over:
        assert battle.turn_phase is TurnPhase.FINISHED
        winner = battle.winner
        if winner is None:
            assert battle.player.current_hp <= 0
            assert battle.enemy.current_hp <= 0
        else:
            assert winner is battle.player or winner is battle.enemy
            assert winner.current_hp > 0
            loser = battle.enemy if winner is battle.player else battle.player
            assert loser.current_hp <= 0
    else:
        assert battle.turn_phase is not TurnPhase.FINISHED
        assert battle.winner is None


def unfold(battle: Battle, pick_action: Callable[[Sequence[ActionDefinition]], ActionDefinition]) -> list[BattleEvent]:
    """Drive `battle` to completion, calling `pick_action` once per player swing.

    Test/headless-only convenience over Battle's query/resolve seam (ADR 0008) -- not part of
    eye.combat's public surface. Asserts turn_phase/is_over/winner consistency after every
    query/resolve call.
    """
    events: list[BattleEvent] = []
    _assert_invariants(battle)
    while not battle.is_over:
        while battle.turn_phase in (TurnPhase.AWAITING_QUERY, TurnPhase.AWAITING_PLAYER_ACTION):
            query = battle.query_player_turn()
            _assert_invariants(battle)
            if isinstance(query, PlayerTurnNeedsAction):
                events.extend(query.pre_turn_events)
                events.extend(battle.resolve_player_turn(pick_action(query.available)))
                _assert_invariants(battle)
            else:
                events.extend(query.events)
                _assert_invariants(battle)
                break
        if battle.is_over:
            break
        events.extend(battle.resolve_enemy_turn())
        _assert_invariants(battle)
    return events
