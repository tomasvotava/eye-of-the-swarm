from eye.combat.effects import (
    EFFECT_POLARITY,
    ActiveEffect,
    EffectCategory,
    EffectName,
    EffectPolarity,
    EffectRegistry,
)
from eye.combat.stats import Stat
from eye.combat.tuning import FIBROUS_ATTACK_MAGNITUDE


def test_modifier_returns_zero_with_no_active_effects() -> None:
    registry = EffectRegistry()

    assert registry.modifier(Stat.ATTACK) == 0.0


def test_modifier_is_zero_for_a_trigger_type_effect() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.RESONANCE, EffectCategory.LIFESPAN, remaining_turns=None))

    assert registry.modifier(Stat.ATTACK) == 0.0


def test_modifier_includes_a_single_active_stat_effect() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.BATTLE, remaining_turns=3))

    assert registry.modifier(Stat.ATTACK) == FIBROUS_ATTACK_MAGNITUDE


def test_lifespan_and_battle_instances_of_same_buff_combine_additively() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, remaining_turns=None))
    registry.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.BATTLE, remaining_turns=3))

    assert registry.modifier(Stat.ATTACK) == FIBROUS_ATTACK_MAGNITUDE * 2


def test_apply_refreshes_rather_than_stacks_within_the_same_category() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.BATTLE, remaining_turns=3))
    registry.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.BATTLE, remaining_turns=1))

    assert registry.modifier(Stat.ATTACK) == FIBROUS_ATTACK_MAGNITUDE


def test_has_finds_effect_in_any_category_when_none_given() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.WILTY, EffectCategory.LIFESPAN, remaining_turns=None))

    assert registry.has(EffectName.WILTY) is True


def test_has_is_false_when_effect_absent_from_the_requested_category() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.WILTY, EffectCategory.LIFESPAN, remaining_turns=None))

    assert registry.has(EffectName.WILTY, category=EffectCategory.BATTLE) is False


def test_tick_battle_effects_expires_effect_at_zero_remaining_turns() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=1))

    expired = registry.tick_battle_effects()

    assert expired == [EffectName.TOXICITY]
    assert registry.has(EffectName.TOXICITY, category=EffectCategory.BATTLE) is False


def test_tick_battle_effects_decrements_without_expiring_when_turns_remain() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.TOXICITY, EffectCategory.BATTLE, remaining_turns=2))

    expired = registry.tick_battle_effects()

    assert expired == []
    assert registry.has(EffectName.TOXICITY, category=EffectCategory.BATTLE) is True


def test_tick_battle_effects_never_expires_indefinite_duration() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.CLOUDED_JUDGEMENT, EffectCategory.BATTLE, remaining_turns=None))

    expired = registry.tick_battle_effects()

    assert expired == []
    assert registry.has(EffectName.CLOUDED_JUDGEMENT, category=EffectCategory.BATTLE) is True


def test_tick_battle_effects_does_not_touch_lifespan_effects() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, remaining_turns=None))

    expired = registry.tick_battle_effects()

    assert expired == []
    assert registry.has(EffectName.FIBROUS, category=EffectCategory.LIFESPAN) is True


def test_remove_drops_a_specific_active_effect() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))

    registry.remove(EffectName.ADRENALINE)

    assert registry.has(EffectName.ADRENALINE) is False


def test_remove_drops_all_categories_of_the_named_effect_when_none_given() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.LIFESPAN, remaining_turns=None))
    registry.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))

    registry.remove(EffectName.ADRENALINE)

    assert registry.has(EffectName.ADRENALINE) is False


def test_remove_only_the_given_category_when_specified() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.LIFESPAN, remaining_turns=None))
    registry.apply(ActiveEffect(EffectName.ADRENALINE, EffectCategory.BATTLE, remaining_turns=None))

    registry.remove(EffectName.ADRENALINE, category=EffectCategory.BATTLE)

    assert registry.has(EffectName.ADRENALINE, category=EffectCategory.BATTLE) is False
    assert registry.has(EffectName.ADRENALINE, category=EffectCategory.LIFESPAN) is True


def test_clear_battle_effects_removes_battle_but_keeps_lifespan() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, remaining_turns=None))
    registry.apply(ActiveEffect(EffectName.RUNT, EffectCategory.BATTLE, remaining_turns=3))

    registry.clear_battle_effects()

    assert registry.has(EffectName.RUNT, category=EffectCategory.BATTLE) is False
    assert registry.has(EffectName.FIBROUS, category=EffectCategory.LIFESPAN) is True


def test_clear_battle_effects_returns_the_cleared_effect_names() -> None:
    registry = EffectRegistry()
    registry.apply(ActiveEffect(EffectName.FIBROUS, EffectCategory.LIFESPAN, remaining_turns=None))
    registry.apply(ActiveEffect(EffectName.RUNT, EffectCategory.BATTLE, remaining_turns=3))

    cleared = registry.clear_battle_effects()

    assert cleared == [EffectName.RUNT]


def test_effect_polarity_has_an_entry_for_every_effect_name() -> None:
    assert set(EFFECT_POLARITY) == set(EffectName)


def test_effect_polarity_classifies_a_known_buff_and_debuff() -> None:
    assert EFFECT_POLARITY[EffectName.FIBROUS] is EffectPolarity.BUFF
    assert EFFECT_POLARITY[EffectName.TOXICITY] is EffectPolarity.DEBUFF
