import math
import random
from collections.abc import Sequence

import pytest

from eye.bestiary import BESTIARY
from eye.character import Character
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.ai import ScriptedChooser
from eye.combat.battle import Battle, PlayerTurnNeedsAction
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName
from eye.combat.events import HitLanded
from eye.combat.stats import Combatant, Stats
from eye.combat.tuning import FIBROUS_ATTACK_MAGNITUDE, STRUGGLE_BASE_POWER
from eye.exploration.encounters import EncounterKind
from eye.exploration.events import EnemyEncountered, NothingHappened, SeedGrew, SeedPlanted
from eye.exploration.tuning import SEED_GROWTH_RATE_CAP, SEED_GROWTH_THRESHOLD
from eye.session.events import GenerationEnded
from eye.session.generation import Generation
from tests.combat.support import unfold
from tests.session.doubles import ScriptedEncounterRandom, advance_flat


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
        rng=ScriptedEncounterRandom(kind_queue),
        starting_screen=0,
        matured_turfs=(),
    )


def test_advance_forwards_exploration_events_untouched_when_nothing_happens() -> None:
    generation = _generation(kind_queue=[EncounterKind.NOTHING])

    events = advance_flat(generation)

    assert any(isinstance(event, SeedGrew) for event in events)
    assert NothingHappened() in events
    assert generation.died is False


def test_enemy_encounter_resolves_a_battle_against_the_bestiary_profile() -> None:
    generation = _generation(kind_queue=[EncounterKind.ENEMY])

    events = advance_flat(generation)

    enemy_event = next(event for event in events if isinstance(event, EnemyEncountered))
    profile = BESTIARY[enemy_event.strain]
    first_hit = next(event for event in events if isinstance(event, HitLanded))
    assert first_hit.damage == round(STRUGGLE_BASE_POWER + 10 - profile.stats.defense)


def test_player_win_awards_the_strains_spores_and_writes_hp_back() -> None:
    overwhelming = Stats(max_hp=100, attack=1000, defense=1000, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = _character(current_hp=100, max_hp=100)
    generation = _generation(character=character, stats=overwhelming, kind_queue=[EncounterKind.ENEMY])

    events = advance_flat(generation)

    enemy_event = next(event for event in events if isinstance(event, EnemyEncountered))
    assert generation.spores_gained == BESTIARY[enemy_event.strain].spore_award
    assert character.current_hp == 100
    assert generation.died is False


def test_player_loss_kills_the_character_and_ends_the_generation() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = _character(current_hp=5, max_hp=5)
    generation = _generation(character=character, stats=fragile, kind_queue=[EncounterKind.ENEMY])

    events = advance_flat(generation)

    assert generation.died is True
    assert character.current_hp <= 0
    assert events[-1] == GenerationEnded()


def test_advance_after_death_is_a_no_op() -> None:
    fragile = Stats(max_hp=5, attack=0, defense=0, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    character = _character(current_hp=5, max_hp=5)
    generation = _generation(character=character, stats=fragile, kind_queue=[EncounterKind.ENEMY])
    advance_flat(generation)

    assert advance_flat(generation) == []


def test_character_lifespan_effects_apply_to_the_player_combatant_in_battle() -> None:
    character = _character(current_hp=100, max_hp=100)
    character.effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, None))
    stats = Stats(max_hp=100, attack=10, defense=5, meter_capacity=100, meter_fill_rate=10, recoil=0.0)
    generation = _generation(character=character, stats=stats, kind_queue=[EncounterKind.ENEMY])

    events = advance_flat(generation)

    enemy_event = next(event for event in events if isinstance(event, EnemyEncountered))
    profile = BESTIARY[enemy_event.strain]
    first_hit = next(event for event in events if isinstance(event, HitLanded))
    expected = round(STRUGGLE_BASE_POWER + 10 + FIBROUS_ATTACK_MAGNITUDE - profile.stats.defense)
    assert first_hit.damage == expected


def test_active_lifespan_effects_lists_only_the_characters_lifespan_scoped_effects() -> None:
    character = _character()
    character.effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, None))
    character.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, 3))
    generation = _generation(character=character)

    assert generation.active_lifespan_effects == (EffectName.FIBROUS,)


def test_active_lifespan_effects_reports_a_name_held_in_both_categories_once() -> None:
    # Separate slots in the registry (PROJECT_BRIEF.md §5.6), but the row shows only whether held.
    character = _character()
    character.effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, None))
    character.effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.BATTLE, 3))
    generation = _generation(character=character)

    assert generation.active_lifespan_effects == (EffectName.FIBROUS,)


def test_active_lifespan_effects_is_empty_when_only_battle_effects_are_held() -> None:
    character = _character()
    character.effects.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, 3))
    generation = _generation(character=character)

    assert generation.active_lifespan_effects == ()


def test_active_lifespan_effects_is_a_snapshot_unaffected_by_later_changes() -> None:
    character = _character()
    character.effects.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, None))
    generation = _generation(character=character)

    snapshot = generation.active_lifespan_effects
    character.effects.apply(ActiveEffect(EffectName.NOURISHED, EffectCategory.LIFESPAN, None))

    assert snapshot == (EffectName.FIBROUS,)
    assert set(generation.active_lifespan_effects) == {EffectName.FIBROUS, EffectName.NOURISHED}


def test_pending_seeds_and_spores_gained_match_the_exploration_runs_accumulators() -> None:
    generation = _generation(kind_queue=[EncounterKind.NOTHING])

    advance_flat(generation)

    assert generation.pending_seeds == ()
    assert generation.spores_gained == 0


def test_plant_seed_passes_through_to_the_exploration_run() -> None:
    advances_to_ready = int(SEED_GROWTH_THRESHOLD // SEED_GROWTH_RATE_CAP)
    generation = _generation(kind_queue=[EncounterKind.NOTHING] * advances_to_ready)
    for _ in range(advances_to_ready):
        advance_flat(generation)
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
        advance_flat(generation)

    advance_flat(generation)

    assert generation.is_seed_ready is True
    assert generation.died is True
    assert generation.plant_seed() == []
    assert generation.pending_seeds == ()


def test_stopping_mid_battle_leaves_character_state_untouched() -> None:
    character = _character(current_hp=100, max_hp=100)
    generation = _generation(character=character, kind_queue=[EncounterKind.ENEMY])
    events = list(generation.advance())
    encounter = next(event for event in events if isinstance(event, EnemyEncountered))
    battle = generation.start_battle(encounter)
    battle.start()
    query = battle.query_player_turn()
    assert isinstance(query, PlayerTurnNeedsAction)
    battle.resolve_player_turn(query.available[0])  # one swing only -- driver stops here

    assert character.current_hp == 100
    assert generation.died is False


def test_advance_raises_while_a_battle_is_in_flight() -> None:
    generation = _generation(kind_queue=[EncounterKind.ENEMY])
    events = list(generation.advance())
    encounter = next(event for event in events if isinstance(event, EnemyEncountered))
    generation.start_battle(encounter)

    with pytest.raises(RuntimeError):
        generation.advance()


def test_start_battle_raises_while_a_previous_battle_is_still_in_flight() -> None:
    generation = _generation(kind_queue=[EncounterKind.ENEMY])
    events = list(generation.advance())
    encounter = next(event for event in events if isinstance(event, EnemyEncountered))
    generation.start_battle(encounter)

    with pytest.raises(RuntimeError):
        generation.start_battle(encounter)


def test_finish_battle_raises_before_the_battle_is_over() -> None:
    generation = _generation(kind_queue=[EncounterKind.ENEMY])
    events = list(generation.advance())
    encounter = next(event for event in events if isinstance(event, EnemyEncountered))
    battle = generation.start_battle(encounter)

    with pytest.raises(RuntimeError):
        generation.finish_battle(battle)


def test_finish_battle_raises_when_called_a_second_time() -> None:
    generation = _generation(kind_queue=[EncounterKind.ENEMY])
    events = list(generation.advance())
    encounter = next(event for event in events if isinstance(event, EnemyEncountered))
    battle = generation.start_battle(encounter)
    battle.start()
    unfold(battle, lambda available: available[0])
    generation.finish_battle(battle)

    with pytest.raises(RuntimeError):
        generation.finish_battle(battle)


def test_finish_battle_raises_for_a_battle_this_generation_did_not_start() -> None:
    generation = _generation(kind_queue=[EncounterKind.ENEMY])
    events = list(generation.advance())
    encounter = next(event for event in events if isinstance(event, EnemyEncountered))
    generation.start_battle(encounter)  # left unfinished

    foreign_stats = Stats(max_hp=1, attack=0, defense=0, meter_capacity=1, meter_fill_rate=1, recoil=0.0)
    foreign_player = Combatant(name="Foreign", base_stats=foreign_stats, current_hp=1)
    foreign_enemy = Combatant(name="ForeignEnemy", base_stats=foreign_stats, current_hp=0)
    foreign_battle = Battle(foreign_player, foreign_enemy, ScriptedChooser([]), random.Random(), 0.0)

    with pytest.raises(RuntimeError):
        generation.finish_battle(foreign_battle)


def test_distance_from_home_threads_through_from_the_exploration_run() -> None:
    generation = _generation(kind_queue=[EncounterKind.NOTHING] * 2)

    advance_flat(generation)
    advance_flat(generation)

    assert generation.distance_from_home == 2


def test_distance_to_nearest_matured_turf_threads_through_from_the_exploration_run() -> None:
    generation = Generation(
        character=_character(),
        stats=Stats(max_hp=100, attack=10, defense=5, meter_capacity=100, meter_fill_rate=10, recoil=0.0),
        actions=(ActionDefinition(kind=ActionKind.STRUGGLE),),
        rng=ScriptedEncounterRandom([EncounterKind.NOTHING] * 2),
        starting_screen=0,
        matured_turfs=(1,),
    )

    advance_flat(generation)
    advance_flat(generation)

    assert generation.distance_to_nearest_matured_turf == 1


def test_distance_to_nearest_matured_turf_is_infinite_with_no_matured_turf_yet() -> None:
    generation = _generation()

    assert generation.distance_to_nearest_matured_turf == math.inf
