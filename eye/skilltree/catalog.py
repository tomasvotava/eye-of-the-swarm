from eye.combat.actions import ActionDefinition, ActionKind, EffectTarget, InflictedEffect
from eye.combat.effects import EffectName
from eye.skilltree.tree import (
    Branch,
    ExplorationModifierDelta,
    SkillNode,
    SkillNodeId,
    StatsDelta,
    SubBranch,
)
from eye.skilltree.tuning import (
    SELF_ATTACK_TIER0_ATTACK_DELTA,
    SELF_ATTACK_TIER1_RECOIL_DELTA,
    SELF_DEFENSE_TIER0_DEFENSE_DELTA,
    SELF_DEFENSE_TIER1_MAX_HP_DELTA,
    SELF_DEFENSE_TIER2_ATTACK_DELTA,
    SELF_DEFENSE_TIER2_DEFENSE_DELTA,
    SELF_UTILITY_TIER0_SEED_GROWTH_MULTIPLIER,
    SELF_UTILITY_TIER1_METER_FILL_RATE_DELTA,
    SELF_UTILITY_TIER2_SEED_GROWTH_MULTIPLIER,
    SWARM_ATTACK_TIER0_METER_FILL_RATE_DELTA,
    SWARM_DEFENSE_TIER1_DEFENSE_DELTA,
    SWARM_UTILITY_TIER0_PROXIMITY_DISCOUNT_BONUS,
    SWARM_UTILITY_TIER2_PROXIMITY_DISCOUNT_BONUS,
    SWARM_UTILITY_TIER2_SEED_GROWTH_MULTIPLIER,
    TIER_COSTS,
)

_NODES = (
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=0),
        cost=TIER_COSTS[0],
        name="Nasty Tendrils",
        description="Wraps around anything that gets too close, and squeezes.",
        stats_delta=StatsDelta(attack=SELF_ATTACK_TIER0_ATTACK_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=1),
        cost=TIER_COSTS[1],
        name="Hooks and Thorns",
        description="Hardened enough now that fewer of the thorns turn back on you.",
        stats_delta=StatsDelta(recoil=SELF_ATTACK_TIER1_RECOIL_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=2),
        cost=TIER_COSTS[2],
        name="Barbed Struggle",
        description="A struggle that leaves more than a bruise -- thorns that weaken whatever they scratch.",
        unlocked_actions=(
            ActionDefinition(
                kind=ActionKind.STRUGGLE,
                name="Barbed Struggle",
                inflicts=(InflictedEffect(effect=EffectName.RUNT, target=EffectTarget.OPPONENT),),
            ),
        ),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.DEFENSE, tier=0),
        cost=TIER_COSTS[0],
        name="Thick Bark",
        description="A hardened shell grown for one purpose: to still be standing after the next hit.",
        stats_delta=StatsDelta(defense=SELF_DEFENSE_TIER0_DEFENSE_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.DEFENSE, tier=1),
        cost=TIER_COSTS[1],
        name="Petrified Growth",
        description="Grows dense instead of tall, trading flexibility for sheer mass.",
        stats_delta=StatsDelta(max_hp=SELF_DEFENSE_TIER1_MAX_HP_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.DEFENSE, tier=2),
        cost=TIER_COSTS[2],
        name="Ossified Shell",
        description="Bark turned to bone -- heavier to carry, harder to break, slower to swing.",
        stats_delta=StatsDelta(defense=SELF_DEFENSE_TIER2_DEFENSE_DELTA, attack=SELF_DEFENSE_TIER2_ATTACK_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.UTILITY, tier=0),
        cost=TIER_COSTS[0],
        name="Fertile",
        description="Seeds swell faster underfoot, impatient to take root.",
        exploration_modifier=ExplorationModifierDelta(
            seed_growth_rate_multiplier=SELF_UTILITY_TIER0_SEED_GROWTH_MULTIPLIER
        ),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.UTILITY, tier=1),
        cost=TIER_COSTS[1],
        name="Weedlike",
        description="Spreads quick and greedy, filling every gap before anything else can.",
        stats_delta=StatsDelta(meter_fill_rate=SELF_UTILITY_TIER1_METER_FILL_RATE_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.UTILITY, tier=2),
        cost=TIER_COSTS[2],
        name="Overgrowth",
        description="Nothing stays bare for long once this takes hold.",
        exploration_modifier=ExplorationModifierDelta(
            seed_growth_rate_multiplier=SELF_UTILITY_TIER2_SEED_GROWTH_MULTIPLIER
        ),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.ATTACK, tier=0),
        cost=TIER_COSTS[0],
        name="Sense of Community",
        description="Even alone, some part of you is still listening for the others.",
        stats_delta=StatsDelta(meter_fill_rate=SWARM_ATTACK_TIER0_METER_FILL_RATE_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.ATTACK, tier=1),
        cost=TIER_COSTS[1],
        name="Fibrous Friends",
        description="Borrowed strength, offered freely and taken without asking.",
        lifespan_effects=(EffectName.FIBROUS,),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.ATTACK, tier=2),
        cost=TIER_COSTS[2],
        name="Coordinated Strike",
        description="One body swings; the whole hive follows through.",
        unlocked_actions=(
            ActionDefinition(
                kind=ActionKind.SWARM_ATTACK,
                name="Coordinated Strike",
                hit_count=2,
                requires_full_meter=True,
            ),
        ),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.DEFENSE, tier=0),
        cost=TIER_COSTS[0],
        name="Plants Together Strong",
        description="Bark thickens wherever two stems grow close enough to touch.",
        lifespan_effects=(EffectName.LIGNEOUS_PERIDERM,),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.DEFENSE, tier=1),
        cost=TIER_COSTS[1],
        name="We Are Root",
        description="What holds the ground holds everything standing on it.",
        stats_delta=StatsDelta(defense=SWARM_DEFENSE_TIER1_DEFENSE_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.DEFENSE, tier=2),
        cost=TIER_COSTS[2],
        name="Ouchy-Feely",
        description="It hurts to touch what hurts you back.",
        lifespan_effects=(EffectName.SPIKY_SKIN,),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=0),
        cost=TIER_COSTS[0],
        name="Swarm Sensation",
        description="The hive feels closer than the distance says it is.",
        exploration_modifier=ExplorationModifierDelta(
            proximity_discount_bonus=SWARM_UTILITY_TIER0_PROXIMITY_DISCOUNT_BONUS
        ),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=1),
        cost=TIER_COSTS[1],
        name="Sap-Fed",
        description="Fed by roots you never see, from a source you never asked to tap.",
        lifespan_effects=(EffectName.NOURISHED,),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=2),
        cost=TIER_COSTS[2],
        name="Close to Home",
        description="Wherever the swarm has been, the ground remembers you.",
        exploration_modifier=ExplorationModifierDelta(
            seed_growth_rate_multiplier=SWARM_UTILITY_TIER2_SEED_GROWTH_MULTIPLIER,
            proximity_discount_bonus=SWARM_UTILITY_TIER2_PROXIMITY_DISCOUNT_BONUS,
        ),
    ),
)

CATALOG: dict[SkillNodeId, SkillNode] = {node.id: node for node in _NODES}
