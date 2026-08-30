from eye.combat.stats import Combatant, Stat, Stats


class _FakeModifierSource:
    """Test double for the effect-registry port `Combatant.effects` depends on."""

    def __init__(self, battle: dict[Stat, float] | None = None, lifespan: dict[Stat, float] | None = None) -> None:
        self._battle = battle or {}
        self._lifespan = lifespan or {}

    def modifier(self, stat: Stat) -> float:
        return self._battle.get(stat, 0.0) + self._lifespan.get(stat, 0.0)

    def has(self, name: object) -> bool:
        return False

    def apply(self, effect: object) -> None:
        pass


def _stats() -> Stats:
    return Stats(max_hp=100, attack=10, defense=5, meter_capacity=100, meter_fill_rate=10)


def test_stats_recoil_defaults_to_zero() -> None:
    assert _stats().recoil == 0.0


def test_combatant_defaults_have_no_active_modifiers() -> None:
    combatant = Combatant(name="Sporeling", base_stats=_stats(), current_hp=100)

    assert combatant.current_meter == 0
    assert combatant.is_player is False
    assert combatant.effective(Stat.ATTACK) == 10


def test_effective_adds_a_single_battle_modifier() -> None:
    combatant = Combatant(
        name="Sporeling",
        base_stats=_stats(),
        current_hp=100,
        effects=_FakeModifierSource(battle={Stat.ATTACK: 3.0}),
    )

    assert combatant.effective(Stat.ATTACK) == 13.0


def test_effective_adds_a_single_lifespan_modifier() -> None:
    combatant = Combatant(
        name="Sporeling",
        base_stats=_stats(),
        current_hp=100,
        effects=_FakeModifierSource(lifespan={Stat.ATTACK: 2.0}),
    )

    assert combatant.effective(Stat.ATTACK) == 12.0


def test_effective_combines_battle_and_lifespan_modifiers_additively() -> None:
    combatant = Combatant(
        name="Sporeling",
        base_stats=_stats(),
        current_hp=100,
        effects=_FakeModifierSource(battle={Stat.ATTACK: 3.0}, lifespan={Stat.ATTACK: 2.0}),
    )

    assert combatant.effective(Stat.ATTACK) == 15.0
