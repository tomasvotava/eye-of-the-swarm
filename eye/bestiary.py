"""Enemy content catalog: `Strain` -> `StrainProfile`, bundling the `Stats`/`ActionDefinition`s a
`Generation` resolves into the enemy's `Combatant` on encounter, plus the Spore award for winning
that battle. Magic numbers are inline playtesting-driven placeholders (docs/adr/0004).
"""

from dataclasses import dataclass

from eye.combat.actions import ActionDefinition, ActionKind, EffectTarget, InflictedEffect
from eye.combat.effects import EffectName
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

# Real, encounterable Strains (eye.exploration.encounters.ENCOUNTERABLE_STRAINS), one sprite each
# under eye/gui/sprites/. Every Strain gets a Struggle-equivalent (always available) and a
# Swarm-Attack-equivalent (meter-gated) -- ordered weakest to strongest by design intent:
# Tumbleweed < Beatle < Flea < Phidizvik < Golem. Stats/actions are playtesting-driven
# placeholders (PROJECT_BRIEF.md §8), not final tuning.

_TUMBLEWEED_STATS = Stats(
    max_hp=40,
    attack=6,
    defense=2,
    meter_capacity=100,
    meter_fill_rate=15,
    recoil=0.0,
)
_TUMBLEWEED_ACTIONS = (
    ActionDefinition(kind=ActionKind.STRUGGLE, name="Roll"),
    ActionDefinition(kind=ActionKind.SWARM_ATTACK, name="Thorned Cyclone", requires_full_meter=True),
)

_BEATLE_STATS = Stats(
    max_hp=55,
    attack=7,
    defense=6,
    meter_capacity=100,
    meter_fill_rate=10,
    recoil=0.0,
)
_BEATLE_ACTIONS = (
    ActionDefinition(kind=ActionKind.STRUGGLE, name="Mandible Bite"),
    ActionDefinition(kind=ActionKind.SWARM_ATTACK, name="Shell Slam", requires_full_meter=True),
)

_FLEA_STATS = Stats(
    max_hp=45,
    attack=9,
    defense=3,
    meter_capacity=100,
    meter_fill_rate=20,
    recoil=0.0,
)
_FLEA_ACTIONS = (
    ActionDefinition(kind=ActionKind.STRUGGLE, name="Quick Bites", hit_count=2),
    ActionDefinition(kind=ActionKind.SWARM_ATTACK, name="Frenzied Leap", requires_full_meter=True),
)

_PHIDIZVIK_STATS = Stats(
    max_hp=70,
    attack=11,
    defense=6,
    meter_capacity=100,
    meter_fill_rate=12,
    recoil=0.0,
)
_PHIDIZVIK_ACTIONS = (
    ActionDefinition(
        kind=ActionKind.STRUGGLE,
        name="Venom Nip",
        inflicts=(InflictedEffect(effect=EffectName.TOXICITY, target=EffectTarget.OPPONENT),),
    ),
    ActionDefinition(
        kind=ActionKind.SWARM_ATTACK,
        name="Toxic Bloom",
        requires_full_meter=True,
        inflicts=(InflictedEffect(effect=EffectName.TOXICITY, target=EffectTarget.OPPONENT),),
    ),
)

_GOLEM_STATS = Stats(
    max_hp=100,
    attack=14,
    defense=10,
    meter_capacity=100,
    meter_fill_rate=8,
    recoil=0.0,
)
_GOLEM_ACTIONS = (
    ActionDefinition(kind=ActionKind.STRUGGLE, name="Rock Fist"),
    ActionDefinition(
        kind=ActionKind.SWARM_ATTACK,
        name="Seismic Slam",
        requires_full_meter=True,
        inflicts=(InflictedEffect(effect=EffectName.SPLINTERED, target=EffectTarget.OPPONENT),),
    ),
)

BESTIARY: dict[Strain, StrainProfile] = {
    Strain.BRAMBLE: StrainProfile(
        stats=_BRAMBLE_STATS,
        actions=(ActionDefinition(kind=ActionKind.STRUGGLE),),
        spore_award=10,
    ),
    Strain.TUMBLEWEED: StrainProfile(stats=_TUMBLEWEED_STATS, actions=_TUMBLEWEED_ACTIONS, spore_award=8),
    Strain.BEATLE: StrainProfile(stats=_BEATLE_STATS, actions=_BEATLE_ACTIONS, spore_award=10),
    Strain.FLEA: StrainProfile(stats=_FLEA_STATS, actions=_FLEA_ACTIONS, spore_award=12),
    Strain.PHIDIZVIK: StrainProfile(stats=_PHIDIZVIK_STATS, actions=_PHIDIZVIK_ACTIONS, spore_award=16),
    Strain.GOLEM: StrainProfile(stats=_GOLEM_STATS, actions=_GOLEM_ACTIONS, spore_award=22),
}
