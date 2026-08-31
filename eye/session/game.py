import random
from collections.abc import Sequence

from eye.character import Character
from eye.combat.ai import ActionChooser
from eye.combat.effects import ActiveEffect, EffectCategory
from eye.player import BASE_PLAYER_ACTIONS, BASE_PLAYER_STATS
from eye.session.events import SeedsMatured, SessionEvent, SporesAwarded
from eye.session.generation import Generation
from eye.skilltree.catalog import CATALOG
from eye.skilltree.resolve import (
    resolved_actions,
    resolved_exploration_modifiers,
    resolved_lifespan_effects,
    resolved_stats,
)
from eye.skilltree.state import SkillTree


class Game:
    """Owns everything that crosses generation boundaries: the `SkillTree` and
    `matured_turf_positions`. Does not own a generation's screen-by-screen loop -- planting has no
    callback/pull point in the domain, it's just a method the caller calls at its own discretion,
    so `start_generation()`/`end_generation()` bracket a loop the caller drives itself
    (docs/adr/0004-composition-root-architecture.md).
    """

    def __init__(
        self,
        rng: random.Random,
        player_chooser: ActionChooser,
        skill_tree: SkillTree | None = None,
        matured_turf_positions: Sequence[int] = (),
    ) -> None:
        self._rng = rng
        self._player_chooser = player_chooser
        self._skill_tree = skill_tree if skill_tree is not None else SkillTree()
        self._matured_turf_positions: tuple[int, ...] = tuple(matured_turf_positions)
        self._current_generation: Generation | None = None

    @property
    def skill_tree(self) -> SkillTree:
        return self._skill_tree

    @property
    def matured_turf_positions(self) -> tuple[int, ...]:
        return self._matured_turf_positions

    def start_generation(self) -> Generation:
        if self._current_generation is not None:
            raise RuntimeError("a generation is already in progress; call end_generation() first")

        catalog = CATALOG.values()
        stats = resolved_stats(BASE_PLAYER_STATS, self._skill_tree, catalog)
        actions = resolved_actions(self._skill_tree, catalog, BASE_PLAYER_ACTIONS)
        lifespan_effects = resolved_lifespan_effects(self._skill_tree, catalog)
        exploration_modifiers = resolved_exploration_modifiers(self._skill_tree, catalog)

        character = Character(current_hp=stats.max_hp, max_hp=stats.max_hp)
        for effect_name in lifespan_effects:
            character.effects.apply(ActiveEffect(effect_name, EffectCategory.LIFESPAN, None))

        spawn_screen = max(self._matured_turf_positions, default=0)
        generation = Generation(
            character,
            stats,
            actions,
            self._player_chooser,
            self._rng,
            spawn_screen,
            self._matured_turf_positions,
            exploration_modifiers.seed_growth_rate_multiplier,
            exploration_modifiers.proximity_discount_bonus,
        )
        self._current_generation = generation
        return generation

    def end_generation(self, generation: Generation) -> list[SessionEvent]:
        if generation is not self._current_generation:
            raise RuntimeError("generation was not started by this Game, or has already been ended")
        if not generation.died:
            raise RuntimeError("generation has not ended yet")
        self._current_generation = None

        events: list[SessionEvent] = []
        matured = generation.pending_seeds
        if matured:
            self._matured_turf_positions = (*self._matured_turf_positions, *matured)
            events.append(SeedsMatured(positions=matured))
        spores_gained = generation.spores_gained
        if spores_gained:
            self._skill_tree.add_spores(spores_gained)
            events.append(SporesAwarded(amount=spores_gained, spores_available=self._skill_tree.spores_available))
        return events
