# Project 003 Phase 2D — Compute Release

## Status

PHASE 2D IDENTITY EXPANSION COMPLETE.

The successful Phase 2D execution applied the frozen Phase 1B biological
identity primitive to the frozen Phase 2C run-scoped evidence.

All locked Phase 2D validation criteria D01-D16 passed.

## Successful execution

Execution base commit:

`351c3364504d51c4a5aca8035cdc37835cc386e2`

Runtime-patched runner SHA-256:

`0315be7b6863e93172ed32025c3b503d79be380389a99d1b8159f04f225482bb`

Success marker:

`PHASE2D_IDENTITY_COMPUTE_PASS`

## Frozen result archive

Path:

`results/phase2d/omicsedge_phase2d_results.tar.gz`

SHA-256:

`3e5feb50e28b620a8ab9f1d4c9901b9faedb127fd84a2dad4dedf65dd5437532`

Size:

`4,530,007 bytes`

The archive was independently extracted after computation.

Every entry in the internal `checksums.sha256` manifest passed independent
verification.

## Identity accounting

Phase 2C EVENT records:

`7,951`

EXACT_NORMALIZED_ALLELE events:

`7,891`

UNRESOLVED events:

`60`

EVENT_VARIANT_LINK records:

`7,891`

Distinct biological VARIANT records touched by Phase 2D:

`2,612`

New Phase 2D VARIANT records:

`2,612`

Reused Phase 1B VARIANT records:

`0`

All 60 unresolved events had reason:

`MISSING_NORMALIZED_ALLELE_FIELD`

UNRESOLVED events received no EVENT_VARIANT_LINK and no guessed VARIANT ID.

## Phase 1B reuse result

No Phase 2D exact allele resolved to an existing Phase 1B VARIANT identifier.

This is recorded as an observed result, not a protocol modification.

The Phase 1B VARIANT records remain immutable.

## Product-query validation

The frozen Phase 2D example variant-level query returned:

- 8 observation rows;
- 2 distinct samples;
- 2 distinct sequencing technologies.

The query preserved the original experiment, benchmark run, EVENT,
OBSERVATION, truth/query side, raw comparator decision, raw match kind,
genotype, source filter, comparator context, identity method, and provenance.

## Scientific boundaries

Phase 2D did not:

- modify Phase 1B scientific records;
- modify Phase 2C scientific records;
- infer representation equivalence;
- assign biological identity to unresolved events;
- create reliability scores;
- create confidence scores;
- create trust labels;
- rank sequencing technologies;
- force consensus;
- make clinical interpretations.

Representation-equivalence inference remains disabled.

## Validation

All frozen Phase 2D gates passed:

- D01 Phase 1B archive identity
- D02 Phase 2C archive identity
- D03 frozen identity implementation
- D04 immutable inputs
- D05 complete EVENT accounting
- D06 exact single-allele requirement
- D07 deterministic VARIANT identifiers
- D08 Phase 1B VARIANT reuse semantics
- D09 UNRESOLVED abstention
- D10 representation equivalence disabled
- D11 at most one VARIANT link per EVENT
- D12 complete EVENT_VARIANT_LINK provenance
- D13 variant-level product query
- D14 deterministic reproducibility
- D15 no scoring or ranking
- D16 release checksum verification

## Next phase

Phase 2E will perform the final product/generalization validation against the
20 frozen Phase 2 validation criteria.

Phase 2D scientific outputs must remain frozen during Phase 2E.
