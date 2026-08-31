from collections.abc import Sequence

from eye.bestiary import BESTIARY
from eye.character import Character
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName
from eye.combat.events import HitLanded
from eye.combat.stats import Stats
from eye.combat.tuning import FIBROUS_ATTACK_MAGNITUDE, STRUGGLE_BASE_POWER
from eye.exploration.encounters import EncounterKind, Strain
from eye.exploration.events import EnemyEncountered, NothingHappened, SeedGrew, SeedPlanted
from eye.exploration.tuning import SEED_GROWTH_RATE_CAP, SEED_GROWTH_THRESHOLD
from eye.session.events import GenerationEnded
from eye.session.generation import Generation
from tests.session.doubles import FirstActionChooser, ScriptedEncounterRandom


def _character(current_hp: int = 100, max_hp: int = 100) -> Character:
    return Character(current_hp=current_hp, max_hp=max_hp)


def _generation(
    character: Character | None = None,
    stats: Stats | None = None,
    kind_queue: Sequence[EncounterKind] = (),
) -> Generation:
    return Generation(
        character=character or _character(),
        stats=stats or Stats(max_hp=100, attack=10, defense=5, meter_capacity=100, meter_fill_rate=10, recoil=0.0),
        actions=(ActionDefinition(kind=ActionKind.STRUGGLE),),
        player_chooser=FirstActionChooser(),
        rng=ScriptedEncounterRandom(kind_queue),
        starting_screen=0,
        matured_turfs=(),
    )


def test_advance_forwards_exploration_events_untouched_when_nothing_happens() -> None:
    generation = _generation(kind_queue=[EncounterKind.NOTHING])

    events = generation.advance()

    assert any(isinstance(event, SeedGrew) for event in events)
    assert NothingHappened() in events
    assert generation.died is False


def test_enemy_encounter_resolves_a_battle_against_the_bestiary_profile() -> None:
    generation = _generation(kind_queue=[EncounterKind.ENEMY])

    events = generation.advance()

    enemy_event = next(event for event in events if isinstance(event, EnemyEncountered))
    assert enemy_event.strain == Strain.BRAMBLE
    first_hit = next(event for event in events if isinstance(event, HitLanded))
    bramble = BESTIARY[Strain.BRAMBLE]
    assert first_hit.damage == round(STRUGGLE_BASE_POWER + 10 - bramble.stats.defense)


def test_player_win_awards_the_strains_spores_and_writes_hp_back() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = _character(current_hp=100, max_hp=100)
    generation = _generation(character=character, stats=overwhelming, kind_queue=[EncounterKind.ENEMY])

    generation.advance()

    assert generation.spores_gained == BESTIARY[Strain.BRAMBLE].spore_award
    assert character.current_hp == 100
    assert generation.died is False


def test_player_loss_kills_the_character_and_ends_the_generation() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = _character(current_hp=5, max_hp=5)
    generation = _generation(character=character, stats=fragile, kind_queue=[EncounterKind.ENEMY])

    events = generation.advance()

    assert generation.died is True
    assert character.current_hp <= 0
    assert events[-1] == GenerationEnded()


def test_advance_after_death_is_a_no_op() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = _character(current_hp=5, max_hp=5)
    generation = _generation(character=character, stats=fragile, kind_queue=[EncounterKind.ENEMY])
    generation.advance()

    assert generation.advance() == []


def test_character_lifespan_effects_apply_to_the_player_combatant_in_battle() -> None:
    character = _character(current_hp=100, max_hp=100)
    character.effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, None))
    stats = Stats(max_hp=100, attack=10, defense=5, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(character=character, stats=stats, kind_queue=[EncounterKind.ENEMY])

    events = generation.advance()

    first_hit = next(event for event in events if isinstance(event, HitLanded))
    bramble = BESTIARY[Strain.BRAMBLE]
    expected = round(STRUGGLE_BASE_POWER + 10 + FIBROUS_ATTACK_MAGNITUDE - bramble.stats.defense)
    assert first_hit.damage == expected


def test_pending_seeds_and_spores_gained_match_the_exploration_runs_accumulators() -> None:
    generation = _generation(kind_queue=[EncounterKind.NOTHING])

    generation.advance()

    assert generation.pending_seeds == ()
    assert generation.spores_gained == 0


def test_plant_seed_passes_through_to_the_exploration_run() -> None:
    advances_to_ready = int(SEED_GROWTH_THRESHOLD // SEED_GROWTH_RATE_CAP)
    generation = _generation(kind_queue=[EncounterKind.NOTHING] * advances_to_ready)
    for _ in range(advances_to_ready):
        generation.advance()
    assert generation.is_seed_ready is True

    events = generation.plant_seed()

    assert events == [SeedPlanted(position=advances_to_ready)]
    assert generation.pending_seeds == (advances_to_ready,)
    assert generation.is_seed_ready is False


def test_plant_seed_is_a_no_op_if_the_generation_has_already_died() -> None:
    # Seed growth is applied before the encounter is resolved within advance(), so a single call
    # can both cross the growth threshold and kill the character via that same call's battle --
    # a driver checking is_seed_ready right after advance() (rather than before it) can reach
    # plant_seed() on an already-dead generation, so this mirrors advance()'s own no-op-after-death
    # contract rather than raising.
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = _character(current_hp=5, max_hp=5)
    kind_queue = [EncounterKind.NOTHING] * 3 + [EncounterKind.ENEMY]
    generation = _generation(character=character, stats=fragile, kind_queue=kind_queue)
    for _ in range(3):
        generation.advance()

    generation.advance()

    assert generation.is_seed_ready is True
    assert generation.died is True
    assert generation.plant_seed() == []
    assert generation.pending_seeds == ()
