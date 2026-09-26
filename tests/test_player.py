import math

from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.stats import Stats
from eye.combat.tuning import PROXIMITY_FALLOFF_RANGE, meter_fill_scale
from eye.player import BASE_PLAYER_ACTIONS, BASE_PLAYER_STATS


def test_base_player_stats_is_a_stats_instance() -> None:
    assert isinstance(BASE_PLAYER_STATS, Stats)


def test_base_player_stats_has_nonzero_recoil() -> None:
    assert BASE_PLAYER_STATS.recoil > 0.0


def _base_player_fill_per_turn(distance_from_turf: float) -> int:
    return round(BASE_PLAYER_STATS.meter_fill_rate * meter_fill_scale(distance_from_turf, PROXIMITY_FALLOFF_RANGE))


def test_base_player_meter_fills_in_exactly_three_turns_next_to_turf() -> None:
    turns_to_fill = math.ceil(BASE_PLAYER_STATS.meter_capacity / _base_player_fill_per_turn(0.0))

    assert turns_to_fill == 3


def test_base_player_meter_still_fills_at_the_last_distance_inside_the_range() -> None:
    assert _base_player_fill_per_turn(PROXIMITY_FALLOFF_RANGE - 1) > 0


def test_base_player_actions_includes_struggle() -> None:
    assert any(action.kind is ActionKind.STRUGGLE for action in BASE_PLAYER_ACTIONS)


def test_struggle_action_does_not_require_full_meter() -> None:
    struggle = next(action for action in BASE_PLAYER_ACTIONS if action.kind is ActionKind.STRUGGLE)

    assert struggle.requires_full_meter is False


def test_base_player_actions_are_action_definitions() -> None:
    assert all(isinstance(action, ActionDefinition) for action in BASE_PLAYER_ACTIONS)
