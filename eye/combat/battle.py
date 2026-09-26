import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

from eye.combat.actions import ActionDefinition, resolve_hit
from eye.combat.ai import ActionChooser
from eye.combat.effects import ActiveEffect, EffectCategory, EffectName
from eye.combat.events import (
    ActionChosen,
    BattleEnded,
    BattleEvent,
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
from eye.combat.tuning import (
    ADRENALINE_REVIVE_HP,
    DEFAULT_BATTLE_EFFECT_DURATION_TURNS,
    HEAL_BEFORE_DAMAGE_TICKS,
    MAX_EXTRA_ACTIONS_PER_TURN,
    NOURISHED_HEAL_PER_TURN,
    PROXIMITY_FALLOFF_RANGE,
    RESONANCE_METER_PREFILL_RATIO,
    SPIKY_SKIN_REFLECT_RATIO,
    TOXICITY_DAMAGE_PER_TURN,
    VEGETATIVE_TRIGGER_CHANCE,
    WILTY_TRIGGER_CHANCE,
    meter_fill_scale,
    uprooted_chance,
)


@dataclass(frozen=True, slots=True)
class ActionAvailability:
    action: ActionDefinition
    is_available: bool


class TurnPhase(Enum):
    AWAITING_QUERY = auto()
    AWAITING_PLAYER_ACTION = auto()
    AWAITING_ENEMY_TURN = auto()
    FINISHED = auto()


@dataclass(frozen=True, slots=True)
class PlayerTurnNeedsAction:
    pre_turn_events: list[BattleEvent]
    available: Sequence[ActionDefinition]


@dataclass(frozen=True, slots=True)
class PlayerTurnConcluded:
    events: list[BattleEvent]


type PlayerTurnQuery = PlayerTurnNeedsAction | PlayerTurnConcluded


class Battle:
    """Round-resolution state machine for a single 1v1 encounter.

    The enemy's turn resolves in one automatic call (`resolve_enemy_turn()`) since its
    `GreedyAI` chooser never blocks on external input. The player's turn is driven by the
    caller through `query_player_turn()` / `resolve_player_turn()` instead, one swing at a
    time -- see `turn_phase` for which call to make next. Every resolving call mutates the
    player/enemy Combatants directly and returns the resulting BattleEvent log in
    chronological order -- the events are a record of what already happened, for
    playback/animation, not instructions for the caller to apply.
    """

    def __init__(
        self,
        player: Combatant,
        enemy: Combatant,
        enemy_chooser: ActionChooser,
        rng: random.Random,
        distance_from_turf: float,
    ) -> None:
        self._player = player
        self._enemy = enemy
        self._enemy_chooser = enemy_chooser
        self._rng = rng
        self._distance_from_turf = distance_from_turf
        self._pending_player_query: PlayerTurnQuery | None = None
        self._extra_action_index: int | None = None
        self._player_turn_done = False

    @property
    def is_over(self) -> bool:
        return self._player.current_hp <= 0 or self._enemy.current_hp <= 0

    @property
    def winner(self) -> Combatant | None:
        player_dead = self._player.current_hp <= 0
        enemy_dead = self._enemy.current_hp <= 0
        if player_dead == enemy_dead:
            return None
        return self._enemy if player_dead else self._player

    @property
    def player(self) -> Combatant:
        return self._player

    @property
    def enemy(self) -> Combatant:
        return self._enemy

    def start(self) -> list[BattleEvent]:
        events: list[BattleEvent] = []
        for combatant in (self._player, self._enemy):
            events.extend(self._prefill_resonance(combatant))
        return events

    def _prefill_resonance(self, combatant: Combatant) -> list[BattleEvent]:
        if not combatant.effects.has(EffectName.RESONANCE, category=EffectCategory.LIFESPAN):
            return []
        amount = round(combatant.base_stats.meter_capacity * RESONANCE_METER_PREFILL_RATIO)
        combatant.current_meter = min(combatant.base_stats.meter_capacity, combatant.current_meter + amount)
        combatant.effects.remove(EffectName.RESONANCE, category=EffectCategory.LIFESPAN)
        return [
            MeterFilled(combatant=combatant, amount=amount, meter_after=combatant.current_meter),
            EffectExpired(target=combatant, effect=EffectName.RESONANCE, category=EffectCategory.LIFESPAN),
        ]

    def _conclude_if_over(self, events: list[BattleEvent]) -> None:
        if self.is_over:
            events.extend(self._clear_battle_effects())
            events.append(BattleEnded(winner=self.winner))

    def _resolve_pre_turn(self, actor: Combatant) -> tuple[list[BattleEvent], bool]:
        events: list[BattleEvent] = []
        wilty_fired = False
        turn_skipped = False

        if actor.effects.has(EffectName.WILTY) and self._roll(WILTY_TRIGGER_CHANCE):
            wilty_fired = True
            actor.current_hp = 0
            death_events, _ = self._handle_potential_death(actor)
            events.extend(death_events)

        if (
            not wilty_fired
            and actor.current_hp > 0
            and actor.effects.has(EffectName.VEGETATIVE)
            and self._roll(VEGETATIVE_TRIGGER_CHANCE)
        ):
            events.append(TurnSkipped(combatant=actor))
            events.extend(self._end_of_turn_ticks(actor, actor_got_turn=False))
            turn_skipped = True

        needs_action = actor.current_hp > 0 and not turn_skipped
        return events, needs_action

    def query_player_turn(self) -> PlayerTurnQuery:
        if self.is_over:
            raise RuntimeError("query_player_turn() called after the battle is over")
        if self._pending_player_query is not None:
            return self._pending_player_query
        if self._player_turn_done:
            raise RuntimeError("query_player_turn() called again after this round's player turn already concluded")

        if self._extra_action_index is None:
            pre_turn_events, needs_action = self._resolve_pre_turn(self._player)
            if not needs_action:
                self._conclude_if_over(pre_turn_events)
                self._player_turn_done = True
                return PlayerTurnConcluded(events=pre_turn_events)
            query: PlayerTurnQuery = PlayerTurnNeedsAction(
                pre_turn_events=pre_turn_events, available=self._available_actions(self._player)
            )
        else:
            query = PlayerTurnNeedsAction(pre_turn_events=[], available=self._available_actions(self._player))

        self._pending_player_query = query
        return query

    def _resolve_player_swing(self, action: ActionDefinition) -> list[BattleEvent]:
        chosen = action
        was_swapped = self._player.effects.has(EffectName.CLOUDED_JUDGEMENT)
        if was_swapped:
            chosen = self._rng.choice(self._available_actions(self._player))
        return self._resolve_swing(self._player, self._enemy, chosen, was_swapped_by_clouded_judgement=was_swapped)

    def resolve_player_turn(self, action: ActionDefinition) -> list[BattleEvent]:
        query = self._pending_player_query
        if not isinstance(query, PlayerTurnNeedsAction):
            raise RuntimeError("resolve_player_turn() called without a pending PlayerTurnNeedsAction query")
        if action not in query.available:
            raise ValueError(f"{action!r} is not among this turn's available actions")
        self._pending_player_query = None

        events = self._resolve_player_swing(action)
        if self.is_over:
            self._conclude_if_over(events)
            self._player_turn_done = True
            self._extra_action_index = None
            return events

        extra_action_index = 0 if self._extra_action_index is None else self._extra_action_index
        if (
            extra_action_index < MAX_EXTRA_ACTIONS_PER_TURN
            and self._player.effects.has(EffectName.UPROOTED)
            and self._roll(uprooted_chance(extra_action_index))
        ):
            events.append(ExtraActionTriggered(actor=self._player, extra_action_index=extra_action_index))
            self._extra_action_index = extra_action_index + 1
            return events

        events.extend(self._end_of_turn_ticks(self._player, actor_got_turn=True))
        self._conclude_if_over(events)
        self._player_turn_done = True
        self._extra_action_index = None
        return events

    def _take_enemy_turn(self) -> list[BattleEvent]:
        events: list[BattleEvent] = []

        pre_turn_events, needs_action = self._resolve_pre_turn(self._enemy)
        events.extend(pre_turn_events)
        if not needs_action:
            return events

        events.extend(self._run_actions(self._enemy, self._player))
        if self.is_over:
            return events

        events.extend(self._end_of_turn_ticks(self._enemy, actor_got_turn=True))
        return events

    def resolve_enemy_turn(self) -> list[BattleEvent]:
        if self.is_over:
            raise RuntimeError("resolve_enemy_turn() called after the battle is over")
        if isinstance(self._pending_player_query, PlayerTurnNeedsAction):
            raise RuntimeError("resolve_enemy_turn() called with a pending player action still unresolved")
        if not self._player_turn_done:
            raise RuntimeError("resolve_enemy_turn() called before the player's turn concluded this round")

        events = self._take_enemy_turn()

        self._player_turn_done = False
        self._pending_player_query = None
        self._extra_action_index = None

        if not self.is_over:
            events.extend(self._expire_battle_effects())
        else:
            self._conclude_if_over(events)
        return events

    @property
    def turn_phase(self) -> TurnPhase:
        if self.is_over:
            return TurnPhase.FINISHED
        if isinstance(self._pending_player_query, PlayerTurnNeedsAction):
            return TurnPhase.AWAITING_PLAYER_ACTION
        if self._player_turn_done:
            return TurnPhase.AWAITING_ENEMY_TURN
        return TurnPhase.AWAITING_QUERY

    def _run_actions(self, actor: Combatant, opponent: Combatant) -> list[BattleEvent]:
        events: list[BattleEvent] = []
        extra_action_index = 0
        while True:
            events.extend(self._act(actor, opponent))
            if self.is_over:
                return events
            if extra_action_index >= MAX_EXTRA_ACTIONS_PER_TURN:
                return events
            if not actor.effects.has(EffectName.UPROOTED) or not self._roll(uprooted_chance(extra_action_index)):
                return events
            events.append(ExtraActionTriggered(actor=actor, extra_action_index=extra_action_index))
            extra_action_index += 1

    def _act(self, actor: Combatant, opponent: Combatant) -> list[BattleEvent]:
        available = self._available_actions(actor)
        chosen = self._enemy_chooser.choose(actor, opponent, available)
        return self._resolve_swing(actor, opponent, chosen, was_swapped_by_clouded_judgement=False)

    def _resolve_swing(
        self, actor: Combatant, opponent: Combatant, chosen: ActionDefinition, *, was_swapped_by_clouded_judgement: bool
    ) -> list[BattleEvent]:
        events: list[BattleEvent] = [
            ActionChosen(
                actor=actor, action=chosen.kind, was_swapped_by_clouded_judgement=was_swapped_by_clouded_judgement
            )
        ]

        for hit_index in range(chosen.hit_count):
            events.extend(self._resolve_one_hit(actor, opponent, chosen, hit_index))
            if self.is_over:
                break

        if chosen.requires_full_meter:
            actor.current_meter = 0
            events.append(MeterConsumed(combatant=actor, meter_after=0))

        return events

    def _resolve_one_hit(
        self, actor: Combatant, opponent: Combatant, action: ActionDefinition, hit_index: int
    ) -> list[BattleEvent]:
        events: list[BattleEvent] = []
        outcome = resolve_hit(actor, opponent, action, distance_from_turf=self._distance_from_turf)

        opponent.current_hp -= outcome.damage_to_defender
        events.append(
            HitLanded(
                source=actor,
                target=opponent,
                action=action.kind,
                hit_index=hit_index,
                hit_count=action.hit_count,
                damage=outcome.damage_to_defender,
                target_hp_after=opponent.current_hp,
            )
        )

        if outcome.damage_to_defender > 0 and opponent.effects.has(EffectName.SPIKY_SKIN):
            reflected = round(outcome.damage_to_defender * SPIKY_SKIN_REFLECT_RATIO)
            actor.current_hp -= reflected
            events.append(
                HitReflected(source=opponent, target=actor, damage=reflected, target_hp_after=actor.current_hp)
            )

        if outcome.recoil_to_attacker > 0:
            actor.current_hp -= outcome.recoil_to_attacker
            events.append(
                SelfDamageTaken(combatant=actor, damage=outcome.recoil_to_attacker, combatant_hp_after=actor.current_hp)
            )

        for effect_name, target in outcome.inflicted:
            duration = None if effect_name is EffectName.ADRENALINE else DEFAULT_BATTLE_EFFECT_DURATION_TURNS
            target.effects.apply(ActiveEffect(effect_name, EffectCategory.BATTLE, duration))
            events.append(
                EffectApplied(
                    target=target, effect=effect_name, category=EffectCategory.BATTLE, remaining_turns=duration
                )
            )

        events.extend(self._check_death(opponent))
        events.extend(self._check_death(actor))

        return events

    def _end_of_turn_ticks(self, actor: Combatant, actor_got_turn: bool) -> list[BattleEvent]:
        events: list[BattleEvent] = []

        tick_order = (
            (self._tick_nourished, self._tick_toxicity)
            if HEAL_BEFORE_DAMAGE_TICKS
            else (
                self._tick_toxicity,
                self._tick_nourished,
            )
        )
        for tick in tick_order:
            events.extend(tick(actor))

        if actor_got_turn and actor.current_hp > 0:
            amount = self._meter_fill_amount(actor)
            actor.current_meter = min(actor.base_stats.meter_capacity, actor.current_meter + amount)
            events.append(MeterFilled(combatant=actor, amount=amount, meter_after=actor.current_meter))

        return events

    def _tick_toxicity(self, actor: Combatant) -> list[BattleEvent]:
        events: list[BattleEvent] = []
        if actor.current_hp > 0 and actor.effects.has(EffectName.TOXICITY):
            actor.current_hp -= TOXICITY_DAMAGE_PER_TURN
            events.append(
                DotTicked(
                    target=actor,
                    effect=EffectName.TOXICITY,
                    damage=TOXICITY_DAMAGE_PER_TURN,
                    target_hp_after=actor.current_hp,
                )
            )
            events.extend(self._check_death(actor))
        return events

    def _tick_nourished(self, actor: Combatant) -> list[BattleEvent]:
        events: list[BattleEvent] = []
        if actor.current_hp > 0 and actor.effects.has(EffectName.NOURISHED):
            actor.current_hp = min(actor.base_stats.max_hp, actor.current_hp + NOURISHED_HEAL_PER_TURN)
            events.append(
                HealApplied(
                    target=actor,
                    effect=EffectName.NOURISHED,
                    amount=NOURISHED_HEAL_PER_TURN,
                    target_hp_after=actor.current_hp,
                )
            )
        return events

    def _expire_battle_effects(self) -> list[BattleEvent]:
        events: list[BattleEvent] = []
        for combatant in (self._player, self._enemy):
            for name in combatant.effects.tick_battle_effects():
                events.append(EffectExpired(target=combatant, effect=name, category=EffectCategory.BATTLE))
        return events

    def _clear_battle_effects(self) -> list[BattleEvent]:
        events: list[BattleEvent] = []
        for combatant in (self._player, self._enemy):
            for name in combatant.effects.clear_battle_effects():
                events.append(EffectExpired(target=combatant, effect=name, category=EffectCategory.BATTLE))
        return events

    def _check_death(self, combatant: Combatant) -> list[BattleEvent]:
        events, _ = self._handle_potential_death(combatant)
        return events

    def _handle_potential_death(self, combatant: Combatant) -> tuple[list[BattleEvent], bool]:
        if combatant.current_hp > 0:
            return [], False
        events: list[BattleEvent] = [Death(combatant=combatant)]
        adrenaline_category = self._active_adrenaline_category(combatant)
        if adrenaline_category is not None:
            events.extend(self._revive(combatant, adrenaline_category))
            return events, True
        return events, False

    def _active_adrenaline_category(self, combatant: Combatant) -> EffectCategory | None:
        if combatant.effects.has(EffectName.ADRENALINE, category=EffectCategory.BATTLE):
            return EffectCategory.BATTLE
        if combatant.effects.has(EffectName.ADRENALINE, category=EffectCategory.LIFESPAN):
            return EffectCategory.LIFESPAN
        return None

    def _revive(self, combatant: Combatant, adrenaline_category: EffectCategory) -> list[BattleEvent]:
        combatant.current_hp = ADRENALINE_REVIVE_HP
        combatant.effects.remove(EffectName.ADRENALINE, category=adrenaline_category)
        combatant.effects.apply(
            ActiveEffect(EffectName.FIBROUS, EffectCategory.BATTLE, DEFAULT_BATTLE_EFFECT_DURATION_TURNS)
        )
        return [
            Revive(combatant=combatant, revived_hp=ADRENALINE_REVIVE_HP),
            EffectApplied(
                target=combatant,
                effect=EffectName.FIBROUS,
                category=EffectCategory.BATTLE,
                remaining_turns=DEFAULT_BATTLE_EFFECT_DURATION_TURNS,
            ),
        ]

    def action_availability(self, combatant: Combatant) -> list[ActionAvailability]:
        return [
            ActionAvailability(action=action, is_available=self._is_action_available(combatant, action))
            for action in combatant.available_actions
        ]

    def _is_action_available(self, actor: Combatant, action: ActionDefinition) -> bool:
        return not action.requires_full_meter or actor.current_meter >= actor.base_stats.meter_capacity

    def _available_actions(self, actor: Combatant) -> Sequence[ActionDefinition]:
        return [action for action in actor.available_actions if self._is_action_available(actor, action)]

    def _meter_fill_amount(self, actor: Combatant) -> int:
        rate = actor.base_stats.meter_fill_rate
        if actor is self._player:
            return round(rate * meter_fill_scale(self._distance_from_turf, PROXIMITY_FALLOFF_RANGE))
        return rate

    def _roll(self, probability: float) -> bool:
        return self._rng.random() < probability
