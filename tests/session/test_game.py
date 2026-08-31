from collections.abc import Sequence

import pytest

from eye.bestiary import BESTIARY
from eye.combat.events import HitLanded
from eye.combat.tuning import STRUGGLE_BASE_POWER
from eye.exploration.encounters import EncounterKind, Strain
from eye.exploration.events import SeedPlanted
from eye.exploration.tuning import SEED_GROWTH_RATE_CAP, SEED_GROWTH_THRESHOLD
from eye.player import BASE_PLAYER_STATS
from eye.session.events import SeedsMatured, SporesAwarded
from eye.session.game import Game
from tests.session.doubles import FirstActionChooser, ScriptedEncounterRandom


def _game(kind_queue: Sequence[EncounterKind] = (), matured_turf_positions: Sequence[int] = ()) -> Game:
    return Game(
        rng=ScriptedEncounterRandom(kind_queue),
        player_chooser=FirstActionChooser(),
        matured_turf_positions=matured_turf_positions,
    )


def test_start_generation_uses_base_player_stats_from_an_empty_skill_tree() -> None:
    game = _game(kind_queue=[EncounterKind.ENEMY])
    generation = game.start_generation()

    events = generation.advance()

    first_hit = next(event for event in events if isinstance(event, HitLanded))
    bramble = BESTIARY[Strain.BRAMBLE]
    assert first_hit.damage == round(STRUGGLE_BASE_POWER + BASE_PLAYER_STATS.attack - bramble.stats.defense)


def test_start_generation_spawns_at_the_furthest_matured_turf() -> None:
    # Growth rate depends on distance from the nearest matured turf (SEED_GROWTH_RATE_CAP only
    # applies once far enough away), so drive to ready rather than hand-computing an advance count.
    game = _game(kind_queue=[EncounterKind.NOTHING] * 20, matured_turf_positions=(3, 7, 2))
    generation = game.start_generation()
    advances = 0
    while not generation.is_seed_ready:
        generation.advance()
        advances += 1

    events = generation.plant_seed()

    assert events == [SeedPlanted(position=7 + advances)]


def test_end_generation_raises_if_the_generation_has_not_died() -> None:
    game = _game()
    generation = game.start_generation()

    with pytest.raises(RuntimeError):
        game.end_generation(generation)


def test_end_generation_awards_spores_and_leaves_matured_turf_positions_unchanged_without_a_plant() -> None:
    game = _game(kind_queue=[EncounterKind.ENEMY, EncounterKind.ENEMY])
    generation = game.start_generation()
    while not generation.died:
        generation.advance()

    events = game.end_generation(generation)

    award = BESTIARY[Strain.BRAMBLE].spore_award
    assert game.skill_tree.spores_available == award
    assert game.matured_turf_positions == ()
    assert not any(isinstance(event, SeedsMatured) for event in events)
    assert SporesAwarded(amount=award, spores_available=award) in events


def test_end_generation_folds_a_planted_seed_into_matured_turf_positions() -> None:
    advances_to_ready = int(SEED_GROWTH_THRESHOLD // SEED_GROWTH_RATE_CAP)
    kind_queue = [EncounterKind.NOTHING] * advances_to_ready + [EncounterKind.ENEMY, EncounterKind.ENEMY]
    game = _game(kind_queue=kind_queue)
    generation = game.start_generation()

    for _ in range(advances_to_ready):
        generation.advance()
    generation.plant_seed()
    while not generation.died:
        generation.advance()

    events = game.end_generation(generation)

    assert game.matured_turf_positions == (advances_to_ready,)
    assert SeedsMatured(positions=(advances_to_ready,)) in events


def test_end_generation_raises_if_called_twice_on_the_same_generation() -> None:
    game = _game(kind_queue=[EncounterKind.ENEMY, EncounterKind.ENEMY])
    generation = game.start_generation()
    while not generation.died:
        generation.advance()
    game.end_generation(generation)

    with pytest.raises(RuntimeError):
        game.end_generation(generation)


def test_end_generation_raises_for_a_generation_started_by_a_different_game() -> None:
    owner = _game(kind_queue=[EncounterKind.ENEMY, EncounterKind.ENEMY])
    generation = owner.start_generation()
    while not generation.died:
        generation.advance()
    stranger = _game()

    with pytest.raises(RuntimeError):
        stranger.end_generation(generation)


def test_end_generation_reports_ownership_before_death_for_a_still_alive_foreign_generation() -> None:
    # A foreign, not-yet-died Generation must be diagnosed as "wrong owner", not misreported as
    # "not ended yet" -- ownership has to be checked before the died check, not after.
    owner = _game()
    generation = owner.start_generation()
    stranger = _game()

    with pytest.raises(RuntimeError, match="not started by this Game"):
        stranger.end_generation(generation)


def test_start_generation_raises_while_a_generation_is_already_in_progress() -> None:
    game = _game()
    game.start_generation()

    with pytest.raises(RuntimeError):
        game.start_generation()


def test_start_generation_is_allowed_again_after_end_generation() -> None:
    game = _game(kind_queue=[EncounterKind.ENEMY, EncounterKind.ENEMY])
    first = game.start_generation()
    while not first.died:
        first.advance()
    game.end_generation(first)

    second = game.start_generation()

    assert second is not first
