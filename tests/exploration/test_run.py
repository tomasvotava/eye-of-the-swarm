import math
import random
from collections.abc import Sequence
from typing import TypeVar

import pytest

from eye.character import Character
from eye.combat.effects import EffectCategory, EffectName
from eye.exploration.encounters import Biome, EncounterKind, ResourceKind, Strain
from eye.exploration.events import (
    EffectGranted,
    EnemyEncountered,
    NothingHappened,
    ResourceGranted,
    SeedGrew,
    SeedPlanted,
)
from eye.exploration.run import ExplorationRun
from eye.exploration.tuning import (
    RESOURCE_DISTANCE_DISCOUNT_MAGNITUDE,
    RESOURCE_HEAL_MAGNITUDE,
    RESOURCE_SEED_GROWTH_MAGNITUDE,
    RESOURCE_SPORES_MAGNITUDE,
    SEED_GROWTH_RATE_CAP,
)

_T = TypeVar("_T")


class _ScriptedRandom(random.Random):
    """Deterministic random.Random stand-in: choices() pops a queued EncounterKind, choice()
    picks by a queued index (default 0, i.e. the first enum member)."""

    def __init__(self, kind_queue: Sequence[EncounterKind], choice_indices: Sequence[int] = ()) -> None:
        super().__init__()
        self._kind_queue = list(kind_queue)
        self._choice_indices = list(choice_indices)

    # Narrower than random.Random.choices' generic signature -- this double is only ever handed
    # Sequence[EncounterKind] by EncounterGenerator, so the narrowing is intentional.
    def choices(  # type: ignore[override]
        self,
        population: Sequence[EncounterKind],
        weights: Sequence[float] | None = None,
        *,
        cum_weights: Sequence[float] | None = None,
        k: int = 1,
    ) -> list[EncounterKind]:
        return [self._kind_queue.pop(0)]

    def choice(self, seq: Sequence[_T]) -> _T:  # type: ignore[override]
        index = self._choice_indices.pop(0) if self._choice_indices else 0
        return seq[index]


def _character(current_hp: int = 50, max_hp: int = 100) -> Character:
    return Character(current_hp=current_hp, max_hp=max_hp)


def test_advance_grows_seed_by_the_formula_amount_when_nothing_exists_yet() -> None:
    run = ExplorationRun(_character(), _ScriptedRandom([EncounterKind.NOTHING]), starting_screen=0, matured_turfs=())

    events = run.advance()

    assert events == [SeedGrew(amount=SEED_GROWTH_RATE_CAP, meter_after=SEED_GROWTH_RATE_CAP), NothingHappened()]


def test_distance_to_nearest_seed_and_turf_are_inf_when_nothing_planted_or_matured() -> None:
    run = ExplorationRun(_character(), _ScriptedRandom([]), starting_screen=0, matured_turfs=())

    assert run.distance_to_nearest_seed == math.inf
    assert run.distance_to_nearest_matured_turf == math.inf


def test_plant_seed_raises_before_the_seed_is_ready() -> None:
    run = ExplorationRun(_character(), _ScriptedRandom([]), starting_screen=0, matured_turfs=())

    with pytest.raises(RuntimeError):
        run.plant_seed()


def test_plant_seed_resets_the_meter_and_records_the_current_screen() -> None:
    run = ExplorationRun(
        _character(),
        _ScriptedRandom([EncounterKind.NOTHING] * 10),
        starting_screen=5,
        matured_turfs=(),
    )
    while not run.is_seed_ready:
        run.advance()

    events = run.plant_seed()

    assert events == [SeedPlanted(position=run.pending_seeds[-1])]
    assert run.pending_seeds[-1] >= 5
    assert run.is_seed_ready is False
    with pytest.raises(RuntimeError):
        run.plant_seed()


def test_distance_discount_affects_turf_distance_but_not_seed_growth() -> None:
    run = ExplorationRun(
        _character(),
        _ScriptedRandom([EncounterKind.RESOURCE_PICKUP], choice_indices=[3]),  # DISTANCE_DISCOUNT
        starting_screen=5,
        matured_turfs=(0,),
    )
    undiscounted_turf_distance = run.distance_to_nearest_matured_turf + 1  # screen not yet advanced

    events = run.advance()

    assert ResourceGranted(kind=ResourceKind.DISTANCE_DISCOUNT, amount=RESOURCE_DISTANCE_DISCOUNT_MAGNITUDE) in events
    assert run.distance_to_nearest_matured_turf == undiscounted_turf_distance - RESOURCE_DISTANCE_DISCOUNT_MAGNITUDE
    assert run.distance_to_nearest_seed == 6.0  # matured turf still counts as a seed, undiscounted


def test_seed_growth_multiplier_scales_the_seed_grew_amount() -> None:
    run = ExplorationRun(
        _character(),
        _ScriptedRandom([EncounterKind.NOTHING]),
        starting_screen=0,
        matured_turfs=(),
        seed_growth_multiplier=1.5,
    )

    events = run.advance()

    scaled = SEED_GROWTH_RATE_CAP * 1.5
    assert events == [SeedGrew(amount=scaled, meter_after=scaled), NothingHappened()]


def test_base_proximity_discount_applies_before_any_pickup_is_touched() -> None:
    run = ExplorationRun(
        _character(),
        _ScriptedRandom([]),
        starting_screen=5,
        matured_turfs=(0,),
        base_proximity_discount=2.0,
    )

    assert run.distance_to_nearest_matured_turf == 3.0


def test_base_proximity_discount_combines_additively_with_a_distance_discount_pickup() -> None:
    run = ExplorationRun(
        _character(),
        _ScriptedRandom([EncounterKind.RESOURCE_PICKUP], choice_indices=[3]),  # DISTANCE_DISCOUNT
        starting_screen=5,
        matured_turfs=(0,),
        base_proximity_discount=2.0,
    )

    run.advance()

    total_discount = 2.0 + RESOURCE_DISTANCE_DISCOUNT_MAGNITUDE
    assert run.distance_to_nearest_matured_turf == (6 - 0) - total_discount


def test_heal_pickup_caps_at_max_hp() -> None:
    character = _character(current_hp=95, max_hp=100)
    run = ExplorationRun(
        character,
        _ScriptedRandom([EncounterKind.RESOURCE_PICKUP], choice_indices=[0]),  # HEAL
        starting_screen=0,
        matured_turfs=(),
    )

    events = run.advance()

    assert character.current_hp == 100
    assert ResourceGranted(kind=ResourceKind.HEAL, amount=RESOURCE_HEAL_MAGNITUDE) in events


def test_seed_growth_pickup_adds_a_second_seed_grew_event() -> None:
    run = ExplorationRun(
        _character(),
        _ScriptedRandom([EncounterKind.RESOURCE_PICKUP], choice_indices=[2]),  # SEED_GROWTH
        starting_screen=0,
        matured_turfs=(),
    )

    events = run.advance()

    seed_grew_events = [event for event in events if isinstance(event, SeedGrew)]
    assert len(seed_grew_events) == 2
    assert seed_grew_events[-1].amount == RESOURCE_SEED_GROWTH_MAGNITUDE
    assert seed_grew_events[-1].meter_after == SEED_GROWTH_RATE_CAP + RESOURCE_SEED_GROWTH_MAGNITUDE


def test_effect_pickup_applies_a_lifespan_effect_to_the_character() -> None:
    character = _character()
    run = ExplorationRun(
        character,
        _ScriptedRandom([EncounterKind.EFFECT_PICKUP], choice_indices=[0]),  # TOXICITY
        starting_screen=0,
        matured_turfs=(),
    )

    events = run.advance()

    assert character.effects.has(EffectName.TOXICITY, category=EffectCategory.LIFESPAN)
    assert EffectGranted(effect=EffectName.TOXICITY) in events


def test_enemy_encounter_emits_strain_and_the_v1_biome() -> None:
    run = ExplorationRun(
        _character(),
        _ScriptedRandom([EncounterKind.ENEMY], choice_indices=[0]),  # BEATLE, first of ENCOUNTERABLE_STRAINS
        starting_screen=0,
        matured_turfs=(),
    )

    events = run.advance()

    assert EnemyEncountered(strain=Strain.BEATLE, biome=Biome.BRAMBEROSITY) in events


def test_same_seed_produces_the_same_sequence_of_events() -> None:
    first = ExplorationRun(_character(), random.Random(42), starting_screen=0, matured_turfs=())
    second = ExplorationRun(_character(), random.Random(42), starting_screen=0, matured_turfs=())

    first_events = [first.advance() for _ in range(20)]
    second_events = [second.advance() for _ in range(20)]

    assert first_events == second_events


def test_spores_gained_accumulates_across_advances() -> None:
    run = ExplorationRun(
        _character(),
        _ScriptedRandom([EncounterKind.RESOURCE_PICKUP] * 2, choice_indices=[1, 1]),  # SPORES twice
        starting_screen=0,
        matured_turfs=(),
    )

    run.advance()
    run.advance()

    assert run.spores_gained == RESOURCE_SPORES_MAGNITUDE * 2
