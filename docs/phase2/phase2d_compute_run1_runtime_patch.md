# Project 003 Phase 2D — Compute Run 1 Runtime Patch

## Status

RUNTIME-ONLY PATCH FROZEN BEFORE PHASE 2D COMPUTE RUN 2.

## Failed execution

The first Phase 2D execution was attempted from frozen implementation commit:

`9e341e8330c8bcbbdb8ef8d3e54b7cef8955b251`

Frozen runner SHA-256:

`fc16e3163f9f61b3b6e794177cd2834739123cc0a2a2a91115e342bab5468082`

The execution passed the frozen-authority checks and then stopped while
extracting the authoritative Phase 2C release archive.

Observed failure:

`RuntimeError: archive contains non-file member: omicsedge_phase2c_results`

## Failure boundary

The failure occurred before the Phase 2C EVENT and OBSERVATION tables were
loaded into the Phase 2D identity transformation.

Therefore:

- no Phase 2D biological identity outcomes were inspected;
- no Phase 2D VARIANT records were materialized;
- no Phase 2D EVENT_VARIANT_LINK records were materialized;
- no Phase 2D identity accounting table was materialized;
- no Phase 2D release archive was created;
- `results/phase2d` did not exist after the failed execution.

## Cause

The frozen `safe_extract()` helper accepted only tar members for which
`member.isfile()` was true.

The authoritative Phase 2C archive legitimately contains a directory entry:

`omicsedge_phase2c_results/`

Directory entries are normal tar structure and do not alter the packaged
scientific content.

## Patch

The extraction helper now:

1. validates every member path against absolute paths and `..` traversal;
2. creates directory members explicitly;
3. continues to accept regular files;
4. rejects all other tar member types;
5. continues to return only extracted file-member names.

No scientific transformation logic is changed.

## Scientific freeze preservation

This patch does not change:

- Phase 1B or Phase 2C authoritative archive content;
- Phase 2D protocol;
- Phase 1B identity primitive;
- biological identity fields;
- deterministic VARIANT ID generation;
- exact normalized-allele eligibility;
- UNRESOLVED behavior;
- representation-equivalence policy;
- EVENT_VARIANT_LINK construction;
- product-query semantics;
- D01-D16 validation criteria;
- reliability/scoring/ranking/consensus restrictions.

The same frozen Phase 2D identity transformation must be rerun after this
runtime-only archive-extraction correction.

Patched runner SHA-256:

`0315be7b6863e93172ed32025c3b503d79be380389a99d1b8159f04f225482bb`
