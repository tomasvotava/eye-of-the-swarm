import math

from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.stats import Stats
from eye.player import BASE_PLAYER_ACTIONS, BASE_PLAYER_STATS


def test_base_player_stats_is_a_stats_instance() -> None:
    assert isinstance(BASE_PLAYER_STATS, Stats)


def test_base_player_stats_has_nonzero_recoil() -> None:
    assert BASE_PLAYER_STATS.recoil > 0.0


def test_base_player_meter_fill_rate_fills_an_unscaled_meter_within_five_turns() -> None:
    # Unscaled: eye.combat.battle.Battle._meter_fill_amount further scales this by proximity
    # falloff for the player, so this pins the rate itself, not turns-to-full in a real battle.
    turns_to_fill = math.ceil(BASE_PLAYER_STATS.meter_capacity / BASE_PLAYER_STATS.meter_fill_rate)

    assert turns_to_fill <= 5


def test_base_player_actions_includes_struggle() -> None:
    assert any(action.kind is ActionKind.STRUGGLE for action in BASE_PLAYER_ACTIONS)


def test_struggle_action_does_not_require_full_meter() -> None:
    struggle = next(action for action in BASE_PLAYER_ACTIONS if action.kind is ActionKind.STRUGGLE)

    assert struggle.requires_full_meter is False


def test_base_player_actions_are_action_definitions() -> None:
    assert all(isinstance(action, ActionDefinition) for action in BASE_PLAYER_ACTIONS)
