# 0006 — Persistence: validate purchased-node existence against the skill tree catalog

**Status:** Accepted
**Date:** 2026-08-31

## Context

ADR 0005 deliberately left `GameSnapshot.decode()` (`eye/persistence/codec.py`) validating only
JSON *shape* — required fields, correct types, known `Branch`/`SubBranch` enum values — and not
domain invariants. In particular, it does not check that a decoded `purchased_nodes` entry
corresponds to an actual node in the current skill tree `CATALOG` (`eye/skilltree/catalog.py`).

Review on the PR implementing ADR 0005 pointed out that `CATALOG` is already the canonical
`dict[SkillNodeId, SkillNode]` mapping, and asked why `decode()` re-derives partial validity
itself via `Branch.__members__`/`SubBranch.__members__` membership checks instead of using it. A
syntactically well-formed but nonexistent node (valid enum names, valid int tier, but no node at
that id in the current catalog — e.g. one renumbered or removed since the save was written) would
decode successfully and, per ADR 0005's direct-`SkillTree`-reconstitution decision, silently grant
the player credit for a node that no longer exists. That's worth catching at decode time rather
than left as a latent inconsistency for whatever composition root eventually consumes the
snapshot.

## Decision

- `decode()` gains a required `catalog: Iterable[SkillNode]` parameter, matching the existing
  resolver-function convention in `eye/skilltree/resolve.py` (`resolved_stats(base, tree,
  catalog)` and friends) — the caller passes `CATALOG.values()`, the same way `eye/session/game.py`
  already does for those resolvers. No default value: `eye/persistence/codec.py` already imports
  `SkillNodeId`/`Branch`/`SubBranch` (types) from `eye.skilltree.tree`, but defaulting `catalog` to
  the real `CATALOG` table would be exactly the "reach into another domain's module to get its
  data" pattern this codebase's domain modules avoid (`CLAUDE.md` conventions) — the codec accepts
  the catalog as injected context instead, same as any other external dependency it doesn't own.
- Structural JSON-shape validation stays in the codec, unchanged from ADR 0005 — only *existence*
  of the resulting `SkillNodeId` in the injected `catalog` is new. A well-formed-but-nonexistent
  node now raises `SaveDataError` instead of decoding successfully.
- Prerequisite-chain consistency (e.g. a purchased tier-2 node without tier-0/1 also purchased)
  remains explicitly out of scope, unchanged from ADR 0005 — this ADR narrows only the
  "exists in `CATALOG`" gap, not the rest of the domain-invariant surface ADR 0005 punted.

## Consequences

- `decode()`'s signature is no longer schema-only — callers must have a `SkillNode` catalog
  available at decode time, same as callers of the skilltree resolver functions already do.
- A save written against an older `CATALOG` (nodes renamed or removed since) now fails `decode()`
  with `SaveDataError` for those entries, rather than silently reconstructing a `SkillTree` with
  dangling purchased-node ids. This is the same class of gap ADR 0005 already flagged for
  `schema_version` drift ("no migration framework exists yet") — `CATALOG` drift is now covered by
  that same caveat, not a new one.
