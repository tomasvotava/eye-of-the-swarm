import random
from collections.abc import Sequence
from dataclasses import dataclass

from eye.bestiary import BESTIARY, StrainProfile
from eye.character import Character
from eye.combat.actions import ActionDefinition
from eye.combat.ai import GreedyAI
from eye.combat.battle import Battle
from eye.combat.effects import EffectCategory, EffectName, EffectRegistry
from eye.combat.stats import Combatant, Stats
from eye.exploration.events import EnemyEncountered
from eye.exploration.run import ExplorationRun
from eye.session.events import GenerationEnded, SessionEvent
from eye.session.tuning import ENEMY_AI_DIFFICULTY_T


@dataclass(slots=True)
class _InFlightBattle:
    battle: Battle
    player: Combatant
    profile: StrainProfile


class Generation:
    """One life: an `ExplorationRun` driving the screen-by-screen loop. Stops advancing once
    `character.current_hp <= 0` -- the only path to 0 HP, since exploration itself never deals
    damage (docs/adr/0004) and every hit happens inside a driver-owned `Battle` (docs/adr/0008).

    `advance()` surfaces an `EnemyEncountered` event like any other screen event; the driver is
    responsible for noticing it and calling `start_battle()` / driving the returned `Battle` /
    calling `finish_battle()` itself, the same way it already calls `plant_seed()` at its own
    discretion.
    """

    def __init__(
        self,
        character: Character,
        stats: Stats,
        actions: tuple[ActionDefinition, ...],
        rng: random.Random,
        starting_screen: int,
        matured_turfs: Sequence[int],
        seed_growth_multiplier: float = 1.0,
        base_proximity_discount: float = 0.0,
    ) -> None:
        self._character = character
        self._stats = stats
        self._actions = actions
        self._rng = rng
        self._exploration = ExplorationRun(
            character,
            rng,
            starting_screen,
            matured_turfs,
            seed_growth_multiplier,
            base_proximity_discount,
        )
        self._battle_spores_gained = 0
        self._in_flight: _InFlightBattle | None = None

    @property
    def died(self) -> bool:
        return self._character.current_hp <= 0

    @property
    def pending_seeds(self) -> tuple[int, ...]:
        return self._exploration.pending_seeds

    @property
    def spores_gained(self) -> int:
        return self._exploration.spores_gained + self._battle_spores_gained

    @property
    def is_seed_ready(self) -> bool:
        return self._exploration.is_seed_ready

    @property
    def active_lifespan_effects(self) -> tuple[EffectName, ...]:
        """Snapshot of the Lifespan-scoped effects the character holds, in `EffectName` order, each
        named once. A Battle-scoped effect of the same name is a separate slot (PROJECT_BRIEF.md §5.6)."""
        effects = self._character.effects
        return tuple(name for name in EffectName if effects.has(name, category=EffectCategory.LIFESPAN))

    def plant_seed(self) -> list[SessionEvent]:
        if self.died:
            return []
        return list(self._exploration.plant_seed())

    def advance(self) -> list[SessionEvent]:
        if self.died:
            return []
        if self._in_flight is not None:
            raise RuntimeError("advance() called while a battle is still in flight; call finish_battle() first")
        return list(self._exploration.advance())

    def start_battle(self, encounter: EnemyEncountered) -> Battle:
        if self._in_flight is not None:
            raise RuntimeError("start_battle() called while a previous battle is still in flight")

        profile = BESTIARY[encounter.strain]
        distance_from_turf = self._exploration.distance_to_nearest_matured_turf

        player = Combatant(
            name="Player",
            base_stats=self._stats,
            current_hp=self._character.current_hp,
            is_player=True,
            effects=self._character.effects,
            available_actions=self._actions,
        )
        enemy = Combatant(
            name=encounter.strain.name.capitalize(),
            base_stats=profile.stats,
            current_hp=profile.stats.max_hp,
            effects=EffectRegistry(),
            available_actions=profile.actions,
        )
        enemy_chooser = GreedyAI(ENEMY_AI_DIFFICULTY_T, self._rng, distance_from_turf)
        battle = Battle(player, enemy, enemy_chooser, self._rng, distance_from_turf)

        self._in_flight = _InFlightBattle(battle=battle, player=player, profile=profile)
        return battle

    def finish_battle(self, battle: Battle) -> list[SessionEvent]:
        if self._in_flight is None:
            raise RuntimeError("finish_battle() called with no battle in flight")
        if battle is not self._in_flight.battle:
            raise RuntimeError("finish_battle() called with a battle this Generation did not start")
        if not battle.is_over:
            raise RuntimeError("finish_battle() called before the battle is over")

        in_flight = self._in_flight
        self._in_flight = None
        self._character.current_hp = in_flight.player.current_hp
        if battle.winner is in_flight.player:
            self._battle_spores_gained += in_flight.profile.spore_award

        return [GenerationEnded()] if self.died else []
