"""Player content catalog: base `Stats`/`ActionDefinition`s fed into `resolved_stats`/
`resolved_actions` (eye.skilltree.resolve) when a `Generation` constructs the player's
`Combatant`. Magic numbers are inline playtesting-driven placeholders (docs/adr/0004).
"""

from eye.combat.actions import ActionDefinition, ActionKind
from eye.combat.stats import Stats

BASE_PLAYER_STATS = Stats(
    max_hp=100,
    attack=10,
    defense=5,
    meter_capacity=100,
    meter_fill_rate=34,  # ~3 turns to full next to turf, ~7-8 at the falloff edge (tuning.meter_fill_scale)
    recoil=0.5,
)

STRUGGLE = ActionDefinition(kind=ActionKind.STRUGGLE, name="Struggle")

BASE_PLAYER_ACTIONS: tuple[ActionDefinition, ...] = (STRUGGLE,)
