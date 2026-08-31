"""Enemy content catalog: `Strain` -> `StrainProfile`, bundling the `Stats`/`ActionDefinition`s a
`Generation` resolves into the enemy's `Combatant` on encounter, plus the Spore award for winning
that battle. Magic numbers are inline playtesting-driven placeholders (docs/adr/0004).
"""

from dataclasses import dataclass

from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.stats import Stats
from eye.exploration.encounters import Strain


@dataclass(frozen=True, slots=True)
class StrainProfile:
    stats: Stats
    actions: tuple[ActionDefinition, ...]
    spore_award: int


_BRAMBLE_STATS = Stats(
    max_hp=60,
    attack=8,
    defense=4,
    meter_capacity=100,
    meter_fill_rate=10,
    recoil=0.0,
)

BESTIARY: dict[Strain, StrainProfile] = {
    Strain.BRAMBLE: StrainProfile(
        stats=_BRAMBLE_STATS,
        actions=(ActionDefinition(kind=ActionKind.STRUGGLE),),
        spore_award=10,
    ),
}
