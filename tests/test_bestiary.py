from eye.bestiary import BESTIARY, StrainProfile
from eye.combat.actions import ActionDefinition
from eye.combat.stats import Stats
from eye.exploration.encounters import Strain


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
