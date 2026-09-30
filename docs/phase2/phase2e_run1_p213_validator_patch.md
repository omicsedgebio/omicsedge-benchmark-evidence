# Project 003 Phase 2E Run 1 — P2-13 Validator Correction

## Status

VALIDATOR-ONLY CORRECTION FROZEN BEFORE PHASE 2E RUN 2.

## Run 1

Execution base commit:

`c5ea3cc634f57e54ba39e6553276c04c422fd3a0`

Frozen Run-1 runner SHA-256:

`8eccc48fe34812c7d7e3f918a742318b6c90a36be62bc321c141e9c102682f4e`

Run-1 generated archive SHA-256:

`3e8d3d602cca96c461d3f8cfe847cf14f0b0fcf375a2b71be2a7b720edbd6cdf`

Observed Run-1 verdict:

`STOP`

Observed failed gate:

`P2-13`

All other frozen Phase 2 gates P2-01 through P2-12 and P2-14 through
P2-20 passed.

Run 1 is not accepted as the final Phase 2 scientific verdict because the
P2-13 implementation contained a validator false negative.

## Defect

The frozen Phase 2 criterion P2-13 states that no EVENT may be silently
merged across runs, samples, technologies, callers, or benchmark executions.

The Run-1 validator incorrectly implemented part of this criterion as:

`identity_scope == "RUN_SCOPED"`

However, the frozen Phase 2C EVENT construction does not define
`RUN_SCOPED` as an `identity_scope` value.

Phase 2C uses `identity_scope` to record the within-run EVENT derivation
mechanism:

- `COMPARATOR_SUPERLOCUS`
- `SOURCE_RECORD_FALLBACK`

Run scoping is instead encoded structurally through the EVENT identifier and
its `benchmark_run_id`.

## Post-Run-1 diagnostic

The diagnostic was performed without changing scientific records.

Observed frozen evidence:

- Phase 2C EVENT records: 7,951
- unique Phase 2C EVENT IDs: 7,951
- observed `identity_scope`: `SOURCE_RECORD_FALLBACK` for all 7,951 EVENTs
- every EVENT references one valid BENCHMARK_RUN
- every EVENT identifier is namespaced by its BENCHMARK_RUN
- every Phase 2D EVENT is accounted for exactly once
- no EVENT has more than one biological VARIANT link
- every EVENT_VARIANT_LINK preserves its source BENCHMARK_RUN

Run-specific EVENT counts:

- HG003 / Illumina: 1,850
- HG003 / ONT: 1,858
- HG004 / Illumina: 2,117
- HG004 / ONT: 2,126

Diagnostic marker:

`P2_13_VALIDATOR_FALSE_NEGATIVE_DIAGNOSIS_PASS`

## Correction

The P2-13 validator now tests the frozen criterion directly:

1. Phase 2C EVENT IDs are unique.
2. Phase 2D link EVENT IDs are unique.
3. Phase 2D accounting covers every Phase 2C EVENT exactly once.
4. Every EVENT references a valid BENCHMARK_RUN.
5. Every BENCHMARK_RUN references a valid EXPERIMENT.
6. Every EVENT ID is explicitly namespaced by its BENCHMARK_RUN.
7. Every EVENT_VARIANT_LINK preserves the source EVENT's BENCHMARK_RUN.
8. `identity_scope` remains restricted to the frozen Phase 2C derivation
   semantics.
9. Phase 2C did not assert cross-run equivalence.

The scientific meaning of P2-13 is unchanged.

## Scientific freeze

This correction does not change:

- Phase 1A records
- Phase 1B records
- Phase 2 source admission
- Phase 2 interval selection
- Phase 2C benchmark evidence
- Phase 2D biological identity
- any VARIANT identifier
- any EVENT identifier
- any EVENT_VARIANT_LINK
- representation-equivalence semantics
- scoring/ranking policy
- any other Phase 2 validation criterion
- PASS/MODIFY/STOP outcome semantics

Only the erroneous P2-13 validation implementation is corrected.

The Phase 2E Run-1 generated output is discarded as non-authoritative before
Run 2.
