# Project 003 — Phase 2E Final Validation Protocol

## Status

FROZEN BEFORE PHASE 2E FINAL-GATE EXECUTION.

## Purpose

Phase 2E performs the final product and generalization validation for
Project 003 Phase 2.

Phase 2E does not introduce new scientific validation criteria.

The authoritative criteria are the 20 requirements already frozen in:

`docs/phase2/phase2_protocol.md`

Phase 2E only freezes the deterministic evidence mapping, validation
procedure, product-query checks, reporting requirements, and final release
packaging procedure used to evaluate those requirements.

## Frozen authorities

Phase 1A archive:

`data/phase1a/omicsedge_phase1a_results.tar.gz`

SHA-256:

`6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202`

Phase 1B archive:

`results/phase1b/omicsedge_phase1b_results.tar.gz`

SHA-256:

`50bf597cbc13a051d5dda7201e9d7653dbc7b1762fef1b8300199641df6474fb`

Phase 2 protocol SHA-256:

`6234485e8916fd30a335c761a62668b617cb148b5b5a1753d12fd7765fa1633f`

Phase 2 admitted-source lock SHA-256:

`63d72d95d48c923514760c72f28a9a397071f6c44fa615bbc55a5fb5adf3a48c`

Phase 2 interval-panel lock SHA-256:

`ef00c21f0e667c1891b90d6785f1072895a8b9d620a5519130a8a1823a4bd9a1`

Phase 2C archive:

`results/phase2c/omicsedge_phase2c_results.tar.gz`

SHA-256:

`345b6c3483350f4f1930fc5957f7a97c2b2daf30e6ba1972f2cf3b8484ff0536`

Phase 2D archive:

`results/phase2d/omicsedge_phase2d_results.tar.gz`

SHA-256:

`3e5feb50e28b620a8ab9f1d4c9901b9faedb127fd84a2dad4dedf65dd5437532`

Frozen Phase 1B identity implementation SHA-256:

`ef05ab077a5bc4495616331dff663d3cea45297651c7a18cd243e98b21532a5c`

Phase 2D release lock SHA-256:

`e5880f5a516e4b71a91d7cc3aab8d273b817c090dec975d6e62fd5f2344a7592`

## Final gate

Phase 2E MUST evaluate exactly 20 criteria.

The criterion identifiers will be:

- P2-01
- P2-02
- P2-03
- P2-04
- P2-05
- P2-06
- P2-07
- P2-08
- P2-09
- P2-10
- P2-11
- P2-12
- P2-13
- P2-14
- P2-15
- P2-16
- P2-17
- P2-18
- P2-19
- P2-20

Their meanings are inherited unchanged from Section 17 of the frozen
Phase 2 protocol.

No criterion may be weakened, removed, or reinterpreted solely because of
observed Phase 2 results.

## Validation evidence mapping

### P2-01

Verify that the authoritative Phase 1A archive is byte-identical to its
frozen SHA-256.

### P2-02

Verify that the authoritative Phase 1B archive is byte-identical to its
frozen SHA-256.

### P2-03

Verify preservation of Phase 1 scientific authorities through their frozen
archive identities and separation of Phase 2 output namespaces.

### P2-04

Verify that every admitted Phase 2 source is represented in the frozen
source-admission records with required provenance.

### P2-05

Verify that source-admission records explicitly preserve independence from
benchmark performance.

### P2-06

Verify that the genomic context panel was frozen before Phase 2 benchmark
outcome execution.

### P2-07

Verify deterministic region-selection provenance from the frozen interval
selection artifacts and recorded inputs.

### P2-08

Verify that the frozen Phase 2 panel contains multiple genomic contexts and
multiple chromosomes.

### P2-09

Verify that the frozen Phase 2 benchmark evidence contains both SNV and
indel evidence.

### P2-10

Verify that the expanded registry contains at least three benchmark samples
across the frozen Phase 1 and Phase 2 evidence, unless the frozen source
audit had produced the protocol-permitted pre-benchmark MODIFY condition.

### P2-11

Verify paired sequencing-technology evidence where admitted public evidence
permits it.

### P2-12

Recompute biological VARIANT identifiers with the unchanged frozen Phase 1B
identity implementation and verify deterministic, assembly-specific identity.

### P2-13

Verify that run-scoped EVENT identity remains distinct across benchmark runs,
samples, technologies, callers, and executions and that Phase 2D biological
linking did not mutate or silently merge source EVENT records.

### P2-14

Verify that ambiguous or representation-unsupported identity remains
UNRESOLVED and that no representation-equivalence identity was emitted
without a separately frozen method.

### P2-15

Trace every new EVENT_VARIANT_LINK through its source EVENT and BENCHMARK_RUN
and verify identity method/version plus Phase 2 source-selection and
interval-selection provenance.

### P2-16

Execute deterministic variant-level product queries that preserve:

sample,
technology,
experiment,
benchmark run,
EVENT,
OBSERVATION,
truth/query side,
raw decision,
comparator/version,
source provenance,
and biological identity method.

The query MUST preserve disagreement rather than collapse observations to
consensus.

### P2-17

Verify that the expanded registry contains no reliability score, confidence
score, trusted label, technology ranking, or forced consensus.

### P2-18

Verify deterministic reproducibility evidence for Phase 2 transformations,
including deterministic entity identifiers and scientific table contents.

### P2-19

Create the final Phase 2 release as a deterministic, checksum-manifested
archive and independently extract and verify it before marking P2-19 PASS.

The final release will be self-contained enough to audit the frozen
authorities and Phase 2 final-gate evidence. It may include nested frozen
archives rather than duplicating their extracted scientific tables.

### P2-20

Verify that the final Phase 2 report explicitly states limitations covering:

dataset-selection scope,
benchmark-truth limitations,
unresolved representation equivalence,
and the distinction between evidence aggregation and biological or clinical
truth.

## Final product-query requirement

Phase 2E must create product-query evidence demonstrating that a biological
VARIANT can act as a lookup entity while retaining heterogeneous benchmark
context.

The product query must not compute:

reliability,
confidence,
trust,
technology ranking,
caller ranking,
majority vote,
or forced consensus.

## Final release outputs

Phase 2E will produce a compact deterministic final Phase 2 release containing
at minimum:

- final Phase 2 validation table;
- final Phase 2 validation summary;
- final Phase 2 report;
- final product-query evidence;
- deterministic reproducibility evidence;
- checksum manifest;
- frozen authority metadata;
- sufficient frozen Phase 2 artifacts or nested archives to independently
  verify the release.

## Outcome semantics

PASS:

All 20 frozen Phase 2 criteria pass.

MODIFY:

The architecture remains scientifically viable but one or more non-fatal
frozen requirements are not yet satisfied.

STOP:

A fundamental scientific or provenance assumption fails.

The validation implementation MUST derive the verdict from the frozen gate
results.

It MUST NOT hard-code PASS.

## Scientific boundaries

Phase 2E must not:

- modify Phase 1A, Phase 1B, Phase 2C, or Phase 2D scientific records;
- change biological identity semantics;
- infer representation equivalence;
- generate trust or reliability scores;
- rank sequencing technologies or callers;
- collapse disagreement to consensus;
- perform clinical interpretation.

## Compute boundary

Phase 2E is a compact local validation and packaging stage.

No BAM, CRAM, FASTQ, or new genomic benchmarking is permitted.

Expected paid compute cost:

CAD 0.
