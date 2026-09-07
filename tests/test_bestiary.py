from eye.bestiary import BESTIARY, StrainProfile
from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.stats import Stats
from eye.exploration.encounters import ENCOUNTERABLE_STRAINS, Strain

# Design intent (PROJECT_BRIEF.md §8 -- playtesting-driven, not final): weakest to strongest.
_STRENGTH_ORDER = (Strain.TUMBLEWEED, Strain.BEATLE, Strain.FLEA, Strain.PHIDIZVIK, Strain.GOLEM)


def test_bestiary_has_an_entry_for_every_strain() -> None:
    assert set(BESTIARY) == set(Strain)


def test_bramble_profile_has_stats_actions_and_a_spore_award() -> None:
    profile = BESTIARY[Strain.BRAMBLE]

    assert isinstance(profile, StrainProfile)
    assert isinstance(profile.stats, Stats)
    assert all(isinstance(action, ActionDefinition) for action in profile.actions)
    assert profile.actions
    assert profile.spore_award > 0


def test_bramble_is_immune_to_recoil() -> None:
    assert BESTIARY[Strain.BRAMBLE].stats.recoil == 0.0


def test_every_encounterable_strain_has_a_struggle_and_a_meter_gated_swarm_attack() -> None:
    for strain in ENCOUNTERABLE_STRAINS:
        profile = BESTIARY[strain]
        kinds = {action.kind for action in profile.actions}
        assert kinds == {ActionKind.STRUGGLE, ActionKind.SWARM_ATTACK}
        struggle = next(action for action in profile.actions if action.kind is ActionKind.STRUGGLE)
        swarm_attack = next(action for action in profile.actions if action.kind is ActionKind.SWARM_ATTACK)
        assert struggle.requires_full_meter is False
        assert swarm_attack.requires_full_meter is True


def test_encounterable_strain_power_follows_the_designed_strength_order() -> None:
    # "Power" combines raw stats with how often the meter-gated Swarm Attack fires -- a strain
    # with a faster meter_fill_rate reaches its (stronger) Swarm Attack more often, so a simple
    # HP+attack+defense sum alone would misrank Flea below Beatle despite Flea's aggression.
    def _power(strain: Strain) -> float:
        stats = BESTIARY[strain].stats
        return stats.max_hp + stats.attack * 3 + stats.defense * 3 + stats.meter_fill_rate * 2

    powers = [_power(strain) for strain in _STRENGTH_ORDER]
    assert powers == sorted(powers)


def test_encounterable_strains_award_more_spores_the_stronger_they_are() -> None:
    awards = [BESTIARY[strain].spore_award for strain in _STRENGTH_ORDER]
    assert awards == sorted(awards)
