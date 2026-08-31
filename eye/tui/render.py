from collections.abc import Sequence
from enum import Enum

from rich.console import Console

from eye.combat.effects import EffectCategory, EffectName
from eye.combat.events import (
    ActionChosen,
    BattleEnded,
    Death,
    DotTicked,
    EffectApplied,
    EffectExpired,
    ExtraActionTriggered,
    HealApplied,
    HitLanded,
    HitReflected,
    MeterConsumed,
    MeterFilled,
    Revive,
    SelfDamageTaken,
    TurnSkipped,
)
from eye.combat.stats import Combatant
from eye.exploration.events import (
    EffectGranted,
    EnemyEncountered,
    NothingHappened,
    ResourceGranted,
    SeedGrew,
    SeedPlanted,
)
from eye.session.events import GenerationEnded, SeedsMatured, SessionEvent, SporesAwarded
from eye.session.generation import Generation


def _label(value: Enum) -> str:
    return value.name.replace("_", " ").title()


def events(console: Console, session_events: Sequence[SessionEvent]) -> None:
    for event in session_events:
        _render_event(console, event)


def _render_event(console: Console, event: SessionEvent) -> None:
    match event:
        case EnemyEncountered(strain=strain, biome=biome):
            console.print(f"A {_label(strain)} strain emerges from the {_label(biome)} biome.")
        case EffectGranted(effect=effect):
            console.print(f"You feel {_label(effect)} take hold.")
        case ResourceGranted(kind=kind, amount=amount):
            console.print(f"You gain {amount} ({_label(kind)}).")
        case NothingHappened():
            console.print("Nothing happens here.")
        case SeedGrew(amount=amount, meter_after=meter_after):
            console.print(f"Your seed grows by {amount:.1f} (now {meter_after:.1f}).")
        case SeedPlanted(position=position):
            console.print(f"You plant a seed at screen {position}.")
        case Death(combatant=combatant):
            console.print(f"{combatant.name} falls.")
        case Revive(combatant=combatant, revived_hp=revived_hp):
            console.print(f"{combatant.name} revives with {revived_hp} HP!")
        case TurnSkipped(combatant=combatant):
            console.print(f"{combatant.name}'s turn is skipped.")
        case ActionChosen(actor=actor, action=action, was_swapped_by_clouded_judgement=swapped):
            suffix = " (clouded judgement!)" if swapped else ""
            console.print(f"{actor.name} uses {_label(action)}{suffix}.")
        case HitLanded(
            source=source,
            target=target,
            action=action,
            hit_index=hit_index,
            hit_count=hit_count,
            damage=damage,
            target_hp_after=target_hp_after,
        ):
            hit_label = f" (hit {hit_index + 1}/{hit_count})" if hit_count > 1 else ""
            console.print(
                f"{source.name}'s {_label(action)} hits {target.name} for {damage}{hit_label} "
                f"-- {target.name} at {target_hp_after} HP."
            )
        case HitReflected(source=source, target=target, damage=damage, target_hp_after=target_hp_after):
            console.print(
                f"{source.name} reflects {damage} damage back at {target.name} "
                f"-- {target.name} at {target_hp_after} HP."
            )
        case SelfDamageTaken(combatant=combatant, damage=damage, combatant_hp_after=combatant_hp_after):
            console.print(f"{combatant.name} takes {damage} recoil damage -- now at {combatant_hp_after} HP.")
        case EffectApplied(target=target, effect=effect, category=category, remaining_turns=remaining_turns):
            console.print(f"{target.name} is affected by {_label(effect)}{_duration(category, remaining_turns)}.")
        case EffectExpired(target=target, effect=effect):
            console.print(f"{_label(effect)} wears off {target.name}.")
        case DotTicked(target=target, effect=effect, damage=damage, target_hp_after=target_hp_after):
            console.print(f"{target.name} takes {damage} {_label(effect)} damage -- now at {target_hp_after} HP.")
        case HealApplied(target=target, effect=effect, amount=amount, target_hp_after=target_hp_after):
            console.print(f"{target.name} heals {amount} HP from {_label(effect)} -- now at {target_hp_after} HP.")
        case ExtraActionTriggered(actor=actor):
            console.print(f"{actor.name} acts again!")
        case MeterFilled(combatant=combatant, amount=amount, meter_after=meter_after):
            console.print(f"{combatant.name}'s swarm meter fills by {amount} (now {meter_after}).")
        case MeterConsumed(combatant=combatant, meter_after=meter_after):
            console.print(f"{combatant.name}'s swarm meter empties (now {meter_after}).")
        case BattleEnded(winner=winner):
            console.print(f"{winner.name} wins the battle!" if winner is not None else "The battle ends in a draw.")
        case GenerationEnded():
            console.print("This generation has ended.")
        case SeedsMatured(positions=positions):
            console.print(f"Seeds mature at screens: {', '.join(str(position) for position in positions)}.")
        case SporesAwarded(amount=amount, spores_available=spores_available):
            console.print(f"You gain {amount} spores (total: {spores_available}).")


def _duration(category: EffectCategory, remaining_turns: int | None) -> str:
    if category is EffectCategory.LIFESPAN:
        return " for this generation"
    if remaining_turns is None:
        return " until the battle ends"
    return f" for {remaining_turns} turn{'s' if remaining_turns != 1 else ''}"


def combatant_state(console: Console, combatant: Combatant) -> None:
    console.print(
        f"{combatant.name}: {combatant.current_hp}/{combatant.base_stats.max_hp} HP, "
        f"meter {combatant.current_meter}/{combatant.base_stats.meter_capacity}"
    )
    active = [_label(name) for name in EffectName if combatant.effects.has(name)]
    if active:
        console.print(f"  effects: {', '.join(active)}")


def generation_ended(console: Console, generation: Generation) -> None:
    console.print("\n-- Generation ended --")
    if generation.pending_seeds:
        positions = ", ".join(str(position) for position in generation.pending_seeds)
        console.print(f"Seeds planted this life, awaiting maturation: {positions}")
    console.print(f"Spores earned this life: {generation.spores_gained}")
