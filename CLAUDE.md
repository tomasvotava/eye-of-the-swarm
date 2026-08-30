# The Eye of the Swarm — agent orientation

Read these before touching anything in this repo:

1. **`docs/PROJECT_BRIEF.md`** — the design source. Every mechanic (Seed/Turf, proximity
   scaling, combat, buffs/debuffs, skill tree, exploration format) is specified there. Treat it
   as authoritative; if code and brief disagree, that's a bug or an undocumented decision, not a
   reason to guess.
2. **`docs/ARCHITECTURE.md`** — the ADR index. Read it, then read every linked ADR under
   `docs/adr/` before working in a domain it covers. ADRs record *why* a module is shaped the way
   it is (module boundaries, event-sourcing choices, representation decisions) — the kind of
   context that isn't recoverable from the code alone.
3. This project follows the `house-rules` skill (`house-rules@tomasvotava`, enabled via
   `.claude/settings.json` — see below) for git/PR discipline, code-quality gates, and
   architecture conventions (DDD-as-guideline, ports-and-adapters, ADRs for architectural
   decisions). Follow it in every session; it overrides default behavior.

## Work tracking

All work is tracked as GitHub Issues, not in this repo's own docs:

- A body of related work is an **Epic** — an issue titled `Epic: <name>`, created first, with no
  parent of its own.
- Implementation-level work is a **sub-issue** of its Epic, linked with GitHub's native
  parent/sub-issue relationship (`gh issue create --parent <epic-number>`, or
  `gh issue edit <n> --parent <epic-number>` after the fact) — not just a "Part of #N" mention in
  the body. The Epic's own `sub-issues` field is the source of truth for what's in scope.
- Sequencing between sub-issues is expressed with real `--blocking`/`--blocked-by` relationships
  (`gh issue create --blocked-by <n>`), not prose like "depends on #N" alone. An issue with no
  blockers can land in parallel with its siblings; say so explicitly in its body.
- Each sub-issue is scoped to land as its own PR. Architectural decisions behind an Epic get an
  ADR (`docs/adr/NNNN-*.md`) before the Epic's sub-issues are filed — the ADR is the durable
  record; the issues carry implementation detail forward from it.
- Design/brainstorming specs are working artefacts, not committed history — `docs/superpowers/`
  is git-ignored on purpose (see `.gitignore`). Nothing under it is authoritative; if a decision
  from a working spec matters going forward, it belongs in an ADR instead.

## Conventions already in use

- Domain code (`eye/combat/`, `eye/exploration/`, `eye/skilltree/`) is pygame-free — no
  rendering, no cross-domain imports. A domain accepts context it doesn't own (e.g.
  `distance_from_turf`, skill-tree-resolved `Stats`) as plain constructor/method parameters; it
  never reaches into another domain's module to get it. Wiring domains together is a composition
  root's job.
- Mutable aggregates (`Battle`, `ExplorationRun`, `SkillTree`) mutate their owned state directly
  and return an ordered `list[...Event]` per call, rather than a single summarized result —
  needed for anything that plays back as a sequence (multi-hit attacks, chained effects,
  screen-by-screen exploration).
- Every magic number lives in a domain's `tuning.py`, explicitly marked as a playtesting-driven
  placeholder (PROJECT_BRIEF.md §8) — not asserted as final by being in code.
