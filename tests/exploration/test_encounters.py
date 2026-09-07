import random

from eye.combat.effects import EffectCategory, EffectName
from eye.exploration.encounters import (
    ENCOUNTERABLE_STRAINS,
    EffectPickupEncounter,
    EncounterGenerator,
    EncounterKind,
    EnemyEncounter,
    NothingEncounter,
    ResourceKind,
    ResourcePickupEncounter,
    Strain,
)


def test_same_seed_produces_the_same_sequence_of_encounters() -> None:
    first = EncounterGenerator(random.Random(1234))
    second = EncounterGenerator(random.Random(1234))

    first_rolls = [first.generate() for _ in range(50)]
    second_rolls = [second.generate() for _ in range(50)]

    assert first_rolls == second_rolls


def test_every_encounter_kind_is_reachable() -> None:
    generator = EncounterGenerator(random.Random(0))

    rolls = [generator.generate() for _ in range(500)]

    seen_kinds = {_kind_of(roll) for roll in rolls}
    assert seen_kinds == set(EncounterKind)


def test_every_resource_kind_is_reachable() -> None:
    generator = EncounterGenerator(random.Random(0))

    rolls = [generator.generate() for _ in range(500)]

    seen_resources = {roll.resource for roll in rolls if isinstance(roll, ResourcePickupEncounter)}
    assert seen_resources == set(ResourceKind)


def test_every_effect_name_is_reachable() -> None:
    generator = EncounterGenerator(random.Random(0))

    rolls = [generator.generate() for _ in range(500)]

    seen_effects = {roll.effect.name for roll in rolls if isinstance(roll, EffectPickupEncounter)}
    assert seen_effects == set(EffectName)


def test_effect_pickup_always_resolves_to_lifespan_with_no_duration() -> None:
    generator = EncounterGenerator(random.Random(0))

    rolls = [generator.generate() for _ in range(200)]

    effect_pickups = [roll for roll in rolls if isinstance(roll, EffectPickupEncounter)]
    assert effect_pickups
    for pickup in effect_pickups:
        assert pickup.effect.category is EffectCategory.LIFESPAN
        assert pickup.effect.remaining_turns is None


def test_enemy_encounter_uses_a_strain() -> None:
    generator = EncounterGenerator(random.Random(0))

    rolls = [generator.generate() for _ in range(200)]

    enemy_encounters = [roll for roll in rolls if isinstance(roll, EnemyEncounter)]
    assert enemy_encounters
    for encounter in enemy_encounters:
        assert encounter.strain in set(Strain)


def test_every_encounterable_strain_is_reachable() -> None:
    # Also establishes that BRAMBLE never spawns live: ENCOUNTERABLE_STRAINS excludes it, and this
    # asserts the *only* Strains ever actually drawn match that set exactly.
    generator = EncounterGenerator(random.Random(0))

    rolls = [generator.generate() for _ in range(500)]

    seen_strains = {roll.strain for roll in rolls if isinstance(roll, EnemyEncounter)}
    assert seen_strains == set(ENCOUNTERABLE_STRAINS)


def _kind_of(
    encounter: EnemyEncounter | EffectPickupEncounter | ResourcePickupEncounter | NothingEncounter,
) -> EncounterKind:
    if isinstance(encounter, EnemyEncounter):
        return EncounterKind.ENEMY
    if isinstance(encounter, EffectPickupEncounter):
        return EncounterKind.EFFECT_PICKUP
    if isinstance(encounter, ResourcePickupEncounter):
        return EncounterKind.RESOURCE_PICKUP
    return EncounterKind.NOTHING
