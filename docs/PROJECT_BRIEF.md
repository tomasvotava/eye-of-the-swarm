# The Eye of the Swarm — Design Brief

**Status:** v1 (core loop, GUI) complete; v2 (presentation & feel) in design
**Event:** pygame Summer Jam
**Jam topic:** "Swarm"
**Duration:** 17 days
**Title:** *The Eye of the Swarm*

> Note on terminology: many nouns in this document are functional placeholders (e.g. "skill point," "seed," "turf"). If world-building settles on a different theme, these may be renamed narratively (a "skill point" could become "a leaf" or "a droplet") without changing how the underlying mechanic works. Anywhere a placeholder term appears, treat it as mechanically locked but narratively flexible.

---

## 1. Logline

You are one body in an ever-growing hive. Every choice pulls you toward serving yourself or serving the swarm — and the game is built to slowly reveal that the two were never actually in conflict.

## 2. Core Theme

The title plays on "Eye" / "I" vs. "Swarm": the individual self versus the collective. The central question the game keeps putting in front of the player is simple — *invest in me, or invest in us?*

The intended emotional arc:
1. **Early game:** self-investment feels obviously correct — it's cheaper, faster, and the returns are immediate.
2. **Mid game:** hive-investment starts paying off in ways that feel accidental or situational ("sometimes I just... don't get hit").
3. **Late game:** the player realizes the hive-focused build has quietly become the stronger, more resilient path — and that helping the swarm *was* helping themselves all along.

This progression should be shown through mechanics, not dialogue or exposition — the jam's short timeline means the design itself has to carry the theme.

## 3. World & Tone (tentative)

- Leaning toward a **plant/hive organism** aesthetic: dark vines, alien flora spreading across territory.
- Tone (sinister invasive species vs. sympathetic natural growth) is **undecided** and will likely be settled by whatever art direction proves feasible in the time available, not the other way around.
- The mechanics below are intentionally written to be tone-agnostic so this decision can be made late.

## 4. Core Loop (roguelite structure)

1. Emerge as the current generation of the hive, spawning at the location of the last planted Seed.
2. Explore outward from the hive's Turf, fighting enemies and growing a Seed resource over time.
3. Decide when and where to plant the Seed once it's ready.
4. Eventually die. A new generation is "born," inheriting the hive's shared memory (i.e., meta-progression persists).
5. Between runs, spend earned **Spores** — gained after every battle — on the Skill Tree.

Death is not failure in the traditional sense — it's a generational handoff. Narratively, it's not "you died and respawned," it's "you were this individual, and now you're the next one, remembering everything the last one knew."

## 5. Core Tension Mechanics

### 5.1 Proximity-to-Hive Power Scaling
The player's abilities are strongest near the hive's *matured* Turf and weaken with distance from it (see §5.2 for how Turf differs from a freshly planted, not-yet-matured Seed). This is the constant, moment-to-moment expression of the game's theme: straying from the collective has an immediate, felt cost.

**v1 implementation:** linear falloff. Simple to build and tune first; a curved or stepped falloff can be explored later if time allows.

### 5.2 Seed / Turf Mechanic

**Growth:** The player continuously grows a **Seed** while exploring. Growth rate scales inversely with distance from the nearest seed — matured Turf or not — so growth is slow near any existing seed and speeds up the farther out the player roams. Distance itself is the incentive to keep pushing away from safety.

**Planting:** Once a Seed is fully grown, it can be planted at the player's current location.

**Maturation (the key twist):** A freshly planted Seed does **not** immediately become official hive Turf. It only matures — extending Turf and unlocking the proximity bonus (§5.1) at that spot — when the current generation dies. Planting banks the location for your *successor*, not for you: if you plant and keep exploring, you're still "far from the swarm" at that exact spot for the rest of this life, even standing right beside it, because the hive hasn't officially claimed it yet.

The moment you plant, a new Seed immediately starts growing (slowly, since you're standing next to one) — so the loop restarts right away, but the strength payoff from the previous plant is deferred until death.

**The core dilemma (updated):** since planting gives no immediate combat benefit in the current life, the pressure to plant isn't "get stronger now" — it's "lock in this location for whoever comes next" vs. "risk dying with nothing banked, for a shot at planting somewhere much farther out." This mirrors the skill tree's self-vs-hive tension (§5.3) on a per-run timescale: investing in the hive pays off for your successor, not for you.

**Decided:** all pending Seeds mature simultaneously on death — planting is always safe, there's no risk of losing progress by planting more than once in a single life. Since the exploration format (§6) is a linear path, the spawn-point question is resolved too: the furthest matured Seed is the new spawn point for the next generation.

**Decision timing:** the decision to plant is made *before* the next screen's encounter is revealed. A screen's contents (enemy, pickup, or nothing, §6) are only known once you've moved onto it and triggered it — at that point the plant decision for reaching it has already been resolved by however you chose to act on the previous screen. There is no way to preview a screen and then retroactively choose to plant instead of entering it.

### 5.3 Skill Tree — Self vs. Hive
Two main branches, each with roughly three sub-branches (Attack, Defense, Utility):

- **"I" branch (self):** direct, personal stat upgrades. Example: +20% max HP.
- **"Swarm" branch (hive):** collective/situational effects that start small and compound. Example progression: *"a hive member sometimes takes a hit for you"* → *"permanent swarm armor that reflects part of incoming damage back at the attacker."*

Design intent: the "I" branch should have a **steeper early curve** (cheap, obviously good, tempting) while the "Swarm" branch has a **flatter early curve but a much higher ceiling** — so the "correct" long-term strategy is initially counter-intuitive.

Utility sub-branches on both sides could govern things like Seed growth rate, maximum planting distance, or turf decay/expansion rules — practical knobs for tuning the core tension in #5.2.

### 5.4 Combat System
- Turn-based, with an ATB-style meter (à la *Final Fantasy*) that fills over a few turns to unlock a special attack.
- **Base attack ("Struggle"-style):** weak and self-damaging without upgrades — intentionally bad, so upgrading it feels like an obvious early win. This is the game's "hook" for the self-investment path.
- **Swarm attack:** the special, meter-gated attack. Its power *and* frequency (how fast the meter fills) both scale down with distance from the hive/turf — tying combat directly back into the core proximity mechanic.
- Basic stat set: HP, Attack, Defense, plus something like a "Swarm Meter" or "Resonance" stat governing the special attack.
- Enemy action selection each turn follows the process in §5.7; buffs/debuffs (§5.6) modify combat stats and can alter that process (e.g. Clouded Judgement).

### 5.5 Rebirth & Shared Memory
- On death, the player becomes a new individual — narratively the "next generation" — but retains all meta-progression (skill tree, currency, etc.).
- Framing: the hive shares memory across generations, so it's continuously "you," just a newer version. This turns the roguelite death loop into a narrative feature instead of a break in continuity.

### 5.6 Buffs & Debuffs

The intended effect: fights can't be fully calculated in advance from stats alone — some volatility, in bounded and named ways.

**Two categories, kept strictly separate** (no exploration-granted effect is battle-scoped, and vice versa):
- **Lifespan** — granted only while exploring (touching a power-up, §6). Lasts for the lifetime of the current generation; lost on death, not on battle end.
- **Battle/turn** — granted only during combat. Lasts a fixed number of turns, or until the current battle ends.

**Shared mechanic:** both the player and enemies can hold any buff/debuff type — nothing in the system is side-specific.

**Reapplication:** applying a buff/debuff already active on a target refreshes it (the new instance replaces the old) rather than stacking — but only *within* the same category. A Lifespan instance and a Battle/turn instance of the same buff type are tracked as separate slots and both apply at once, combining additively (e.g. a Lifespan Fibrous +20% picked up while exploring plus a Battle/turn Fibrous +30% granted mid-fight give +50% Attack for that battle, dropping back to +20% once the battle-scoped instance expires). At most one instance per category per buff type is ever active on a target.

**v1 has no cleanse/dispel mechanic** — effects run out only via duration or death.

**Specialty types** (beyond conventional HP/Attack/Defense modifiers):
- **Toxicity** (debuff) — after the holder attacks, they take poison damage each turn for N turns.
- **Nourished** (buff) — heals a few HP each turn. Plays nicely against Toxicity (net HP change depends on which is larger).
- **Clouded Judgement** (debuff) — player: the chosen action is swapped for a random one from their available set. Enemy: the normal action-selection process (§5.7) runs, but the top-ranked action is excluded from the candidate pool first.
- **Ligneous Periderm** (buff, name pending) — reduces damage taken (raises effective Defense) for its duration.
- **Splintered** (debuff) — lowers effective Defense for its duration.
- **Spiky Skin** (buff) — an attacker takes reflected damage when they hit the holder.
- **Adrenaline** (buff) — one-shot: the next time the holder would die, they instead revive with a small fixed HP, gain Fibrous, and take an extra turn immediately. Consumed on trigger, regardless of which category (Lifespan or Battle) held the triggering instance — a Lifespan-granted Adrenaline (e.g. a skill-tree trait) is a once-per-generation save, not a once-per-battle one. If both categories are active on the same holder, only the triggering instance is consumed (Battle preferred over Lifespan), leaving the other independently in play per the reapplication rule above.
- **Fibrous** (buff) — raises Attack for its duration.
- **Runt** (debuff) — lowers Attack for its duration.
- **Uprooted** (buff) — each turn, a fixed flat % chance of a second action that same turn.
- **Wilty** (debuff) — each turn, a fixed flat % chance of spontaneous death, checked independent of the chosen action. Pairs well with Adrenaline — some attacks may inflict both at once.
- **Vegetative** (debuff) — each turn, a fixed flat % chance the turn is skipped entirely.
- **Swarm Resonance** (buff) — one-shot: the next battle this generation enters starts with the
  Swarm Meter (§5.4) already partially filled. Consumed the moment that battle begins, regardless
  of how many battles pass before it's triggered. Exploration-only in practice (see §6) — nothing
  in the system stops a future battle-granted instance, but it would have nothing left to carry
  forward to, since Battle-scoped effects clear when the battle that granted them ends.

All "may" probabilities above are fixed flat percentages baked into the buff's definition — not upgradeable via the skill tree in v1; a knob to revisit post-jam if it proves fun.

### 5.7 Enemy AI — Action Selection

Enemies loop through their available actions each turn and score each one:

`score = damage_to_target − self_damage_taken + self_heal_gained + (K if this action wins the fight, else 0)`

...with `K` large enough that any lethal action always outranks any non-lethal one. Actions are ranked by score, best first.

**Difficulty** is a single greediness parameter **T ∈ (0, 1)** per tier (e.g. easy ≈ 0.6, medium ≈ 0.35, hard ≈ 0.15 — exact values to be tuned by playtesting, not fixed here). The probability of the rank-*k* action (0 = best) is proportional to `T^k`, normalized across however many actions are available that turn — a geometric falloff. Low T → sharply peaked on the best action (hard, near-deterministic); high T → flatter, more random picks (easy). This generalizes to any number of available actions without a per-count lookup table.

**Clouded Judgement** (enemy side, §5.6): drop the rank-0 action from the candidate list, then apply the same distribution to what remains — the enemy still "tries," it just never reaches for its actual best option.

**Interaction with Adrenaline:** if the target of a lethal hit holds Adrenaline (§5.6), that action doesn't count as "wins the fight" — the target survives — so the `K` bonus doesn't apply. The AI naturally deprioritizes attacks that can't actually close out the fight.

## 6. Exploration Format

**Decided:** a linear sequence of procedurally-generated **screens**, grouped into **Biomes** —
zones the path is divided into (see §8 for how many). The player walks left to right; there is no
free-roam map. Each screen spawns with a single random encounter that triggers on contact — the
player walks *into* it and something happens:

- Touch an enemy (of some **Strain** — an enemy archetype/kind, native to its Biome, §7) → cut to
  the turn-based combat screen (§5.4).
- Touch an effect pickup → apply a Lifespan buff or debuff (§5.6) — lasts until this generation
  dies.
- Touch a resource pickup → one of: restore HP; gain Spores (the skill-tree currency, §5.3); jump
  the current Seed's growth meter (§5.2); or shrink the *felt* distance to the nearest matured
  Turf — a "fellow carcass" find, a memory of a fallen hive-mate that makes the swarm feel closer.
  This last one only discounts proximity-to-hive combat scaling (§5.1) — it never affects Seed
  growth rate (§5.2), since growth is meant to reward pushing further out, not be blunted by a
  lucky find.
- Touch nothing → the screen is safely traversed — no gain, just further from Turf.
- (Other trigger types can be added to this list as they're designed — the pattern is generic: walk in, trigger fires.)

This keeps "distance from the nearest Seed" exactly as simple as intended: it's just a count of screens traversed, no spatial map math required (per §5.2 and §5.1). It also keeps the spawn-point rule from §5.2 unambiguous — furthest matured Seed = next generation's start screen.

**Core version (v1, no platforming):** movement within a screen is just "walk right until you touch the thing." No jumping, no obstacles, no physics. This is enough on its own to support the full core loop (proximity scaling, Seed growth, planting, combat) — the game is feature-complete without any platforming mechanics.

**Stretch goal — basic platformer movement:** if time allows, add jump input and simple obstacles (spikes, gaps, etc.) that damage the player if not cleared. This would layer on top of the existing screen-and-trigger structure rather than replace it — screens would just gain an optional physical-traversal layer before you reach the trigger. Because the core loop doesn't depend on this, it can be cut entirely without touching anything else in this document.

## 7. Scope Guardrails for a 17-Day Jam

Given the timeline, suggested priority order if cuts become necessary:

1. Core combat loop (Struggle attack + swarm meter + proximity scaling)
2. Seed / Turf loop (plant-now-vs-push-further tension)
3. Skill tree (even a minimal 2-branch, 3-tier version proves the theme)
4. Rebirth/meta-progression framing
5. Art direction, tone, and narrative flourish (lowest priority — can be simplified or reskinned last)

**Optional add-on, not on the critical path:** basic platformer movement (§6 stretch goal). Only attempt once 1–4 above are working and proven fun — it's pure upside, never required to ship a complete loop.

Recommend keeping the first pass to a single Strain (enemy archetype, §6), a single Biome (§6), a short path, and minimal UI, and only expanding once the core loop (1–3 above) is proven fun in isolation.

## 8. Open Questions / TBD

- Final tone: sinister invasive plant vs. sympathetic natural growth (art-driven decision).
- How many distinct Biomes the path is divided into (visually and by Strain difficulty), and
  whether Biome affects which Strains can spawn there. **Planned for v2 (§9.3): three**, art
  direction permitting — not locked until the art proves feasible.
- Whether "Struggle" stays purely mechanical or gets a narrative-flavored name once the world's tone is set.
- Whether basic platformer movement (§6 stretch goal) makes it into the jam build or gets pushed to post-jam.
- Exact numeric tuning for buff/debuff magnitudes, durations, "may" chance percentages, and AI difficulty T values (§5.6, §5.7) — playtesting-driven, not fixed by this brief.
- Whether door choice (§9.2) ever gains real mechanical influence over encounter selection — v2
  keeps it cosmetic only; giving it teeth would need a domain change and isn't currently planned.

## 9. v2 — Presentation Layer (Post-v1.0.0)

v1 closes out §7's priority list 1–4 (core combat, Seed/Turf loop, skill tree, rebirth framing)
plus a first playable GUI. Every idea below is a *presentation* change: how the existing engine's
state is walked through, revealed, and narrated to the player. None of it changes `Battle`,
`ExplorationRun`, `SkillTree`, or their events — the domain/GUI boundary this project already
follows (`CLAUDE.md`) holds for v2 too. Where an idea *would* require touching a domain, it's
flagged and left as an open question (§8) rather than folded in here.

### 9.1 Screen-by-screen walking

Today, entering a screen and resolving its encounter happen on the same input — §6's "walk right
until you touch the thing" is currently instantaneous, one keypress calls `advance()` and the
result is shown immediately. v2 makes that walk visible: the player character enters from the
screen's left edge, the encounter (enemy, pickup, or empty) is visible ahead at a fixed position,
and the player chooses when to walk toward it. `advance()` still fires exactly once per screen —
still as early as it does today, when the screen loads, since that's the only way to know what to
render there before the player moves a step — the domain's mutate-on-`.advance()` contract (§6) is
unchanged. What's new is that the result is withheld from the player until their sprite reaches
the encounter: the walk is a presentational delay between a decision already made and its reveal,
not a trigger for it. The player cannot choose not to reach the encounter — there's no way to
avoid it, only to choose when to arrive — so withholding the reveal doesn't change what happens,
only when the player learns it.

### 9.2 Door choice (cosmetic tension)

**Decided: cosmetic only.** Each screen may render its encounter behind one of several doors.
Picking a door doesn't touch `advance()`'s existing random roll — every door leads to the same,
already-decided outcome. The player experiences agency ("I dodged it by picking the left door")
the mechanics never actually granted; the tension is real, the control is not. Because encounter
selection is untouched, this needs no domain change. Whether a *real* door mechanic is worth
building later is an open question (§8), not part of this plan.

### 9.3 Biome progression

As screen count rises (distance from the hive's turf, §5.1/§6), background art gradually shifts
from the swarm's home biome toward the next — planned for a small, fixed number of biomes (three,
art direction permitting, §8), with a gradual transition rather than a hard cut: the closing
screens of one biome thin out its scenery as the opening screens of the next introduce theirs.
Purely a GUI-side function of screen count — the domain already tracks distance from turf, no new
domain state is needed.

### 9.4 Distance-from-home / distance-from-turf display

The player should always be able to see two distances: how far they've walked from home (screen
count) and how far they are from the nearest matured turf (§5.1's proximity scaling). Both values
already exist in domain state (`Generation`/`ExplorationRun`) — this is a GUI-only display
question. **Not yet decided:** the visual form (a number, a bar, a fading vine, etc.) — left open
deliberately, per the brief's own note (§0) that mechanically-locked ideas can stay narratively
undecided.

### 9.5 Battle event animation

Currently a full combat round resolves within a single `update()` call, with all of that round's
events dumped into the log at once (`CombatScene._record`). v2 reveals events one at a time — a
debuff roll, a struck hit, an applied effect, recoil damage — each with a short pause before the
next.

**Decided:** auto-timed reveal — each event shows for a fixed pause before the next appears,
rather than waiting on a keypress. Exact pacing is playtesting-tuned, per this project's existing
"every magic number lives in `tuning.py`" convention (`CLAUDE.md`). `Battle`'s event-per-call
contract (ADR 0008) already supports this; nothing about the domain changes, only how many frames
`CombatScene` takes to walk through one call's events.

### 9.6 Skill tree icon presentation

Each obtainable skill renders as a ~32×32px icon (replacing the current `SkillTreeLeaf`
placeholder) with its name and effect list beneath it, plus a description the skill carries.
Skills need a description field to carry this — a presentation-only addition alongside their
existing name/effects.

### 9.7 Buff/debuff descriptions + inspector overlay

Every buff/debuff (§5.6) needs a player-facing description, and the player should be able to
inspect any active icon at any time via an overlay listing all current buff/debuff icons with
their descriptions. Descriptions are presentation text, not domain state — likely a GUI-side
lookup keyed by `EffectName`, mirroring how `BuffIcon`/`TextBuffIcon` already work.

### 9.8 In-game narration ("tutorial" without a tutorial)

No dedicated tutorial mode. Instead, a lightweight message-and-continue mechanic ("You venture
from your swarm's land into biomes unknown — press → to venture further," "You've found a pile of
spores. Might be useful.") lets the game speak to the player at key first-playthrough moments,
folding instruction into story instead of breaking away for it. Presentation-only: an
overlay/queue the GUI shows at scripted trigger points, no domain involvement.

### 9.9 Art & audio asset pipeline

Sprites, backgrounds, animation frames, and music/sound are in production and will land
incrementally. The existing `SpriteAtlas` abstraction (ADR 0009) and its dev-only viewer are the
intended landing point — v2 work should keep placeholder art swappable through that seam rather
than hardcoding asset assumptions into scene code.
