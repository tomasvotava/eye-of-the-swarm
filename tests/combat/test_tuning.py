import math

import pytest

from eye.combat.tuning import METER_FILL_EDGE_SCALE, PROXIMITY_FALLOFF_RANGE, meter_fill_scale


def test_meter_fill_scale_is_full_next_to_turf() -> None:
    assert meter_fill_scale(0.0, PROXIMITY_FALLOFF_RANGE) == 1.0


def test_meter_fill_scale_floors_near_the_edge_scale_just_inside_the_range() -> None:
    just_inside = math.nextafter(PROXIMITY_FALLOFF_RANGE, 0.0)

    assert meter_fill_scale(just_inside, PROXIMITY_FALLOFF_RANGE) == pytest.approx(METER_FILL_EDGE_SCALE)


@pytest.mark.parametrize("distance", [PROXIMITY_FALLOFF_RANGE, PROXIMITY_FALLOFF_RANGE * 2, math.inf])
def test_meter_fill_scale_is_zero_at_or_beyond_the_range(distance: float) -> None:
    assert meter_fill_scale(distance, PROXIMITY_FALLOFF_RANGE) == 0.0


def test_meter_fill_scale_never_increases_with_distance() -> None:
    distances = [step * 0.5 for step in range(int(PROXIMITY_FALLOFF_RANGE * 2) + 3)]
    scales = [meter_fill_scale(distance, PROXIMITY_FALLOFF_RANGE) for distance in distances]

    assert scales == sorted(scales, reverse=True)
