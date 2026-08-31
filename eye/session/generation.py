import random
from collections.abc import Sequence

from eye.bestiary import BESTIARY
from eye.character import Character
from eye.combat.actions import ActionDefinition
from eye.combat.ai import ActionChooser, GreedyAI
from eye.combat.battle import Battle
from eye.combat.effects import EffectRegistry
from eye.combat.stats import Combatant, Stats
from eye.exploration.events import EnemyEncountered, ExplorationEvent
from eye.exploration.run import ExplorationRun
from eye.session.events import GenerationEnded, SessionEvent
from eye.session.tuning import ENEMY_AI_DIFFICULTY_T


class Generation:
    """One life: an `ExplorationRun` driving the screen-by-screen loop, dropping into a `Battle`
    whenever it surfaces an `EnemyEncountered`. Stops advancing once `character.current_hp <= 0`
    -- the only path to 0 HP, since exploration itself never deals damage (docs/adr/0004).
    """

    def __init__(
        self,
        character: Character,
        stats: Stats,
        actions: tuple[ActionDefinition, ...],
        player_chooser: ActionChooser,
        rng: random.Random,
        starting_screen: int,
        matured_turfs: Sequence[int],
        seed_growth_multiplier: float = 1.0,
        base_proximity_discount: float = 0.0,
    ) -> None:
        self._character = character
        self._stats = stats
        self._actions = actions
        self._player_chooser = player_chooser
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

    def plant_seed(self) -> list[SessionEvent]:
        if self.died:
            return []
        return list(self._exploration.plant_seed())

    def advance(self) -> list[SessionEvent]:
        if self.died:
            return []
        exploration_events = self._exploration.advance()
        events: list[SessionEvent] = list(exploration_events)
        enemy_encountered = self._enemy_encountered(exploration_events)
        if enemy_encountered is not None:
            events.extend(self._resolve_battle(enemy_encountered))
        if self.died:
            events.append(GenerationEnded())
        return events

    def _enemy_encountered(self, events: Sequence[ExplorationEvent]) -> EnemyEncountered | None:
        return next((event for event in events if isinstance(event, EnemyEncountered)), None)

    def _resolve_battle(self, encounter: EnemyEncountered) -> list[SessionEvent]:
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
        battle = Battle(player, enemy, self._player_chooser, enemy_chooser, self._rng, distance_from_turf)

        events: list[SessionEvent] = list(battle.start())
        while not battle.is_over:
            events.extend(battle.take_round())

        self._character.current_hp = player.current_hp
        if battle.winner is player:
            self._battle_spores_gained += profile.spore_award
        return events
