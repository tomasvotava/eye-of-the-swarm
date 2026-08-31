import random
from collections.abc import Sequence
from typing import TypeVar

from eye.bestiary import BESTIARY
from eye.character import Character
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName
from eye.combat.events import HitLanded
from eye.combat.stats import Combatant, Stats
from eye.combat.tuning import FIBROUS_ATTACK_MAGNITUDE, STRUGGLE_BASE_POWER
from eye.exploration.encounters import EncounterKind, Strain
from eye.exploration.events import EnemyEncountered, NothingHappened, SeedGrew
from eye.session.events import GenerationEnded
from eye.session.generation import Generation

_T = TypeVar("_T")


class _ScriptedEncounterRandom(random.Random):
    """Deterministic random.Random stand-in for the encounter-kind draw only. Every scenario here
    gives each combat side exactly one available action, so the choices()/choice() calls GreedyAI
    makes during battle are already deterministic on a real Random -- only the encounter-kind pick
    (population of several weighted EncounterKind members) needs scripting."""

    def __init__(self, kind_queue: Sequence[EncounterKind]) -> None:
        super().__init__()
        self._kind_queue = list(kind_queue)

    def choices(  # type: ignore[override]
        self,
        population: Sequence[_T],
        weights: Sequence[float] | None = None,
        *,
        cum_weights: Sequence[float] | None = None,
        k: int = 1,
    ) -> list[_T]:
        if self._kind_queue:
            kind = self._kind_queue.pop(0)
            return [kind]  # type: ignore[list-item]
        return super().choices(population, weights, cum_weights=cum_weights, k=k)


class _FirstActionChooser:
    def choose(self, actor: Combatant, opponent: Combatant, available: Sequence[ActionDefinition]) -> ActionDefinition:
        return available[0]


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
        player_chooser=_FirstActionChooser(),
        rng=_ScriptedEncounterRandom(kind_queue),
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
