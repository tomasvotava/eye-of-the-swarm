# The Eye of the Swarm — Design Brief

**Status:** Early concept / pre-production
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

### 5.5 Rebirth & Shared Memory
- On death, the player becomes a new individual — narratively the "next generation" — but retains all meta-progression (skill tree, currency, etc.).
- Framing: the hive shares memory across generations, so it's continuously "you," just a newer version. This turns the roguelite death loop into a narrative feature instead of a break in continuity.

## 6. Exploration Format

**Decided:** a linear sequence of procedurally-generated **screens**. The player walks left to right; there is no free-roam map. Each screen spawns with a single random encounter that triggers on contact — the player walks *into* it and something happens:

- Touch an enemy → cut to the turn-based combat screen (§5.4).
- Touch a power-up → apply a temporary buff or debuff.
- Touch a heal pickup → restore HP.
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

Recommend keeping the first pass to a single enemy archetype set, a short single-segment path, and minimal UI, and only expanding once the core loop (1–3 above) is proven fun in isolation.

## 8. Open Questions / TBD

- Final tone: sinister invasive plant vs. sympathetic natural growth (art-driven decision).
- How many distinct zones/segments the path is divided into (visually and by enemy difficulty).
- Whether "Struggle" stays purely mechanical or gets a narrative-flavored name once the world's tone is set.
- Whether basic platformer movement (§6 stretch goal) makes it into the jam build or gets pushed to post-jam.
