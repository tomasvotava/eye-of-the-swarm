import math

from eye.exploration.tuning import (
    SEED_GROWTH_BASE_RATE,
    SEED_GROWTH_RATE_CAP,
    seed_growth_rate,
)


def test_seed_growth_rate_saturates_at_the_cap_when_no_seed_exists() -> None:
    assert seed_growth_rate(math.inf) == SEED_GROWTH_RATE_CAP


def test_seed_growth_rate_is_base_rate_right_next_to_a_seed() -> None:
    assert seed_growth_rate(0.0) == SEED_GROWTH_BASE_RATE


def test_seed_growth_rate_increases_with_distance_up_to_the_cap() -> None:
    assert SEED_GROWTH_BASE_RATE < seed_growth_rate(10.0) <= SEED_GROWTH_RATE_CAP
