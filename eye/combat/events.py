from dataclasses import dataclass

from eye.combat.actions import ActionKind
from eye.combat.effects import EffectCategory, EffectName
from eye.combat.stats import Combatant


@dataclass(frozen=True, slots=True)
class Death:
    combatant: Combatant


@dataclass(frozen=True, slots=True)
class Revive:
    combatant: Combatant
    revived_hp: int


@dataclass(frozen=True, slots=True)
class TurnSkipped:
    combatant: Combatant


@dataclass(frozen=True, slots=True)
class ActionChosen:
    actor: Combatant
    action: ActionKind
    was_swapped_by_clouded_judgement: bool


@dataclass(frozen=True, slots=True)
class HitLanded:
    source: Combatant
    target: Combatant
    action: ActionKind
    hit_index: int  # 0-based position within this action's hit_count
    hit_count: int  # lets a UI render "hit 2 of 3"
    damage: int
    target_hp_after: int


@dataclass(frozen=True, slots=True)
class HitReflected:
    source: Combatant  # the Spiky Skin holder doing the reflecting
    target: Combatant  # the original attacker, now taking reflected damage
    damage: int
    target_hp_after: int


@dataclass(frozen=True, slots=True)
class SelfDamageTaken:
    combatant: Combatant
    damage: int
    combatant_hp_after: int


@dataclass(frozen=True, slots=True)
class EffectApplied:
    target: Combatant
    effect: EffectName
    category: EffectCategory
    remaining_turns: int | None


@dataclass(frozen=True, slots=True)
class EffectExpired:
    target: Combatant
    effect: EffectName


@dataclass(frozen=True, slots=True)
class DotTicked:
    target: Combatant
    effect: EffectName
    damage: int
    target_hp_after: int


@dataclass(frozen=True, slots=True)
class HealApplied:
    target: Combatant
    effect: EffectName
    amount: int
    target_hp_after: int


@dataclass(frozen=True, slots=True)
class ExtraActionTriggered:
    actor: Combatant
    extra_action_index: int  # ties to the Uprooted decay hook (see #10)


@dataclass(frozen=True, slots=True)
class MeterFilled:
    combatant: Combatant
    amount: int
    meter_after: int


@dataclass(frozen=True, slots=True)
class MeterConsumed:
    combatant: Combatant
    meter_after: int


@dataclass(frozen=True, slots=True)
class BattleEnded:
    winner: Combatant | None


type BattleEvent = (
    Death
    | Revive
    | TurnSkipped
    | ActionChosen
    | HitLanded
    | HitReflected
    | SelfDamageTaken
    | EffectApplied
    | EffectExpired
    | DotTicked
    | HealApplied
    | ExtraActionTriggered
    | MeterFilled
    | MeterConsumed
    | BattleEnded
)
