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
        stats_delta=StatsDelta(attack=SELF_ATTACK_TIER0_ATTACK_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=1),
        cost=TIER_COSTS[1],
        name="Hooks and Thorns",
        stats_delta=StatsDelta(recoil=SELF_ATTACK_TIER1_RECOIL_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.ATTACK, tier=2),
        cost=TIER_COSTS[2],
        name="Barbed Struggle",
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
        stats_delta=StatsDelta(defense=SELF_DEFENSE_TIER0_DEFENSE_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.DEFENSE, tier=1),
        cost=TIER_COSTS[1],
        name="Petrified Growth",
        stats_delta=StatsDelta(max_hp=SELF_DEFENSE_TIER1_MAX_HP_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.DEFENSE, tier=2),
        cost=TIER_COSTS[2],
        name="Ossified Shell",
        stats_delta=StatsDelta(defense=SELF_DEFENSE_TIER2_DEFENSE_DELTA, attack=SELF_DEFENSE_TIER2_ATTACK_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.UTILITY, tier=0),
        cost=TIER_COSTS[0],
        name="Fertile",
        exploration_modifier=ExplorationModifierDelta(
            seed_growth_rate_multiplier=SELF_UTILITY_TIER0_SEED_GROWTH_MULTIPLIER
        ),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.UTILITY, tier=1),
        cost=TIER_COSTS[1],
        name="Weedlike",
        stats_delta=StatsDelta(meter_fill_rate=SELF_UTILITY_TIER1_METER_FILL_RATE_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SELF, sub_branch=SubBranch.UTILITY, tier=2),
        cost=TIER_COSTS[2],
        name="Overgrowth",
        exploration_modifier=ExplorationModifierDelta(
            seed_growth_rate_multiplier=SELF_UTILITY_TIER2_SEED_GROWTH_MULTIPLIER
        ),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.ATTACK, tier=0),
        cost=TIER_COSTS[0],
        name="Sense of Community",
        stats_delta=StatsDelta(meter_fill_rate=SWARM_ATTACK_TIER0_METER_FILL_RATE_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.ATTACK, tier=1),
        cost=TIER_COSTS[1],
        name="Fibrous Friends",
        lifespan_effects=(EffectName.FIBROUS,),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.ATTACK, tier=2),
        cost=TIER_COSTS[2],
        name="Coordinated Strike",
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
        lifespan_effects=(EffectName.LIGNEOUS_PERIDERM,),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.DEFENSE, tier=1),
        cost=TIER_COSTS[1],
        name="We Are Root",
        stats_delta=StatsDelta(defense=SWARM_DEFENSE_TIER1_DEFENSE_DELTA),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.DEFENSE, tier=2),
        cost=TIER_COSTS[2],
        name="Ouchy-Feely",
        lifespan_effects=(EffectName.SPIKY_SKIN,),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=0),
        cost=TIER_COSTS[0],
        name="Swarm Sensation",
        exploration_modifier=ExplorationModifierDelta(
            proximity_discount_bonus=SWARM_UTILITY_TIER0_PROXIMITY_DISCOUNT_BONUS
        ),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=1),
        cost=TIER_COSTS[1],
        name="Sap-Fed",
        lifespan_effects=(EffectName.NOURISHED,),
    ),
    SkillNode(
        id=SkillNodeId(branch=Branch.SWARM, sub_branch=SubBranch.UTILITY, tier=2),
        cost=TIER_COSTS[2],
        name="Close to Home",
        exploration_modifier=ExplorationModifierDelta(
            seed_growth_rate_multiplier=SWARM_UTILITY_TIER2_SEED_GROWTH_MULTIPLIER,
            proximity_discount_bonus=SWARM_UTILITY_TIER2_PROXIMITY_DISCOUNT_BONUS,
        ),
    ),
)

CATALOG: dict[SkillNodeId, SkillNode] = {node.id: node for node in _NODES}
