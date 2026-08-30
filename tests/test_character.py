from eye.character import Character
from eye.combat.effects import EffectRegistry


def test_character_holds_given_hp_values() -> None:
    character = Character(current_hp=10, max_hp=20)

    assert character.current_hp == 10
    assert character.max_hp == 20


def test_character_default_effects_is_an_independent_registry_per_instance() -> None:
    first = Character(current_hp=10, max_hp=20)
    second = Character(current_hp=10, max_hp=20)

    assert isinstance(first.effects, EffectRegistry)
    assert first.effects is not second.effects
