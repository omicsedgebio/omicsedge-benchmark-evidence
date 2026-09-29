# Project 003 — Phase 2 Protocol

## Title

Multi-Sample, Multi-Context Generalization of the OmicsEdge Benchmark Evidence Registry

## Status

FROZEN BEFORE PHASE 2 SOURCE SELECTION OR COMPUTATION

## Phase 1 Authorities

Phase 1A authoritative archive:

- path: `data/phase1a/omicsedge_phase1a_results.tar.gz`
- SHA-256: `6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202`

Phase 1B authoritative archive:

- path: `results/phase1b/omicsedge_phase1b_results.tar.gz`
- SHA-256: `50bf597cbc13a051d5dda7201e9d7653dbc7b1762fef1b8300199641df6474fb`

Phase 1B scientific gate:

- 15 / 15 validation criteria PASS
- 1,666 biological VARIANT records
- 3,332 EVENT_VARIANT_LINK records
- exact normalized-allele identity only
- representation-equivalence inference disabled
- no reliability or confidence score

---

# 1. Scientific Question

Can the OmicsEdge Benchmark Evidence Registry generalize beyond the Phase 1 HG002 chr20 proof-of-concept while preserving:

1. immutable run-scoped benchmark evidence,
2. deterministic biological variant identity,
3. complete provenance,
4. sample and technology context,
5. disagreements between benchmark observations,
6. reproducible product queries,
7. abstention where identity cannot be established safely?

Phase 2 is not a benchmark leaderboard.

Phase 2 is not intended to determine which sequencing technology or caller is superior.

Phase 2 tests whether the evidence-registry architecture remains scientifically valid when the amount and heterogeneity of public benchmark evidence increase.

---

# 2. Core Hypothesis

A biological variant can act as a stable assembly-specific lookup entity across multiple benchmark runs and samples while the original benchmark events and observations remain immutable and independently interpretable.

The registry must permit:

VARIANT
  -> EVENT_VARIANT_LINK
    -> EVENT
      -> OBSERVATION
        -> BENCHMARK_RUN
          -> EXPERIMENT

without converting heterogeneous evidence into a forced consensus.

---

# 3. Phase 2 Architecture

Phase 2 MUST retain the architecture established in Phases 1A and 1B.

Existing Phase 1A entities remain authoritative:

- EXPERIMENT
- BENCHMARK_RUN
- EVENT
- OBSERVATION
- SOURCE_ARTIFACT
- PROVENANCE_LINK

Existing Phase 1B entities remain authoritative:

- VARIANT
- EVENT_VARIANT_LINK

Phase 2 may add new records to the registry.

Phase 2 MUST NOT mutate existing Phase 1A or Phase 1B scientific records.

---

# 4. Biological Variant Identity

Phase 2 inherits the frozen Phase 1B v1 biological identity definition.

A VARIANT identity is determined by:

- assembly
- contig
- normalized start
- normalized end
- normalized REF
- normalized ALT

Sample identity is NOT part of the VARIANT identifier.

Technology is NOT part of the VARIANT identifier.

Caller is NOT part of the VARIANT identifier.

Benchmark comparator is NOT part of the VARIANT identifier.

These attributes belong to evidence context, not biological variant identity.

---

# 5. Identity States

Allowed identity states remain:

- EXACT_NORMALIZED_ALLELE
- REPRESENTATION_EQUIVALENCE_SUPPORTED
- NON_EQUIVALENT
- UNRESOLVED

Phase 2 MUST NOT emit:

REPRESENTATION_EQUIVALENCE_SUPPORTED

unless a separate representation-equivalence algorithm is:

1. explicitly specified,
2. validated on adversarial cases,
3. frozen before use on real Phase 2 evidence.

Until then, representation-different cases remain UNRESOLVED.

---

# 6. Phase 2 Expansion Target

Phase 2 should materially exceed the Phase 1 proof-of-concept.

The intended target is:

- at least 3 distinct benchmark samples in total,
- at least 2 sequencing technologies where compatible public evidence exists,
- at least 2 benchmark runs per included sample where paired technologies are available,
- multiple genomic contexts,
- multiple chromosomes,
- both SNVs and indels,
- deterministic, provenance-traceable region selection.

HG002 may remain included.

HG003 and HG004 are preferred additional samples because they are established GIAB benchmark genomes, but they are not automatically accepted.

Their inclusion depends on the Phase 2 source audit.

If HG003 or HG004 cannot satisfy the locked source requirements, another public benchmark sample may be substituted only through a documented Phase 2 source-selection decision.

No substitution may be based on benchmark performance.

---

# 7. Source Requirements

Every new Phase 2 benchmark experiment MUST have sufficient public metadata to identify, where applicable:

- sample
- sequencing technology
- platform
- source corpus
- source submission
- reference assembly
- variant caller or submitted callset provenance
- benchmark truth source
- benchmark regions
- comparator
- comparator version
- source artifact checksum

Minimum requirements:

1. public accessibility,
2. stable source identity,
3. GRCh38 compatibility,
4. usable variant call artifact,
5. usable truth artifact,
6. usable benchmark-region definition,
7. reproducible provenance.

A source failing these requirements MUST NOT silently enter the registry.

---

# 8. Source Selection Independence

Benchmark performance MUST NOT be consulted when deciding which candidate datasets enter Phase 2.

Source selection may use:

- data availability,
- sample identity,
- sequencing technology,
- reference assembly,
- metadata completeness,
- file integrity,
- technical compatibility,
- licensing,
- compute feasibility.

Source selection MUST NOT use:

- precision,
- recall,
- F1,
- concordance,
- false-positive count,
- false-negative count,
- apparent agreement with another technology,
- visually attractive benchmark behavior.

This rule exists to prevent outcome-driven dataset selection.

---

# 9. Genomic Context Expansion

Phase 2 must include multiple genomic contexts rather than simply increasing the size of the Phase 1 interval.

The final context panel must include, where valid public stratifications permit:

- comparatively uncomplicated benchmark sequence,
- homopolymer context,
- tandem-repeat context,
- low-mappability or difficult-mapping context,
- additional non-repetitive genomic context.

The same locked context-selection procedure must be applied across included samples wherever possible.

Context selection MUST occur before benchmark performance is examined.

---

# 10. Region Selection

The exact Phase 2 intervals will be frozen only after the source and stratification audit.

The interval-selection algorithm MUST be deterministic.

Permitted selection inputs include:

- chromosome,
- coordinate,
- public stratification membership,
- callable benchmark-region intersection,
- required interval size,
- deterministic ordering or hashing.

Benchmark outcomes MUST NOT be selection inputs.

The final interval panel must be written to a frozen Phase 2 interval manifest before benchmarking begins.

---

# 11. Benchmarking

Phase 2 should reuse the Phase 1 comparator methodology where technically compatible.

The comparator implementation and version MUST be recorded for every BENCHMARK_RUN.

Changing comparator software, normalization logic, truth interpretation, or benchmark-region semantics requires an explicit protocol amendment before the affected real-data run.

---

# 12. Sample Semantics

A biological VARIANT may legitimately have evidence from multiple samples.

Therefore:

same VARIANT
does NOT mean
same genotype

and:

same VARIANT
does NOT mean
same benchmark outcome

and:

same VARIANT
does NOT mean
same technology behavior.

Every product query must preserve sample identity explicitly.

---

# 13. Technology Semantics

Evidence from Illumina, Oxford Nanopore Technologies, or another admitted technology must remain separate at the observation/run level.

Phase 2 MUST NOT generate:

- technology winner,
- technology ranking,
- reliability score,
- trust score,
- confidence score,
- forced consensus.

The registry stores empirical evidence.

It does not decide which technology should be trusted.

---

# 14. Product Requirement

A user must be able to query one VARIANT and retrieve all linked benchmark evidence available in the registry, including:

- sample,
- technology,
- experiment,
- benchmark run,
- run-scoped event,
- truth/query side,
- raw benchmark decision,
- comparator/version,
- source artifact provenance,
- biological identity method.

The query must preserve disagreements rather than collapse them.

---

# 15. Phase 2 Subphases

## Phase 2A — Source Audit

Identify candidate public datasets and determine whether they satisfy the frozen source requirements.

No benchmark performance may be consulted during this stage.

Output:

- candidate source manifest
- eligibility decision
- exclusion reason
- immutable source identifiers
- checksums where available

## Phase 2B — Context Panel Freeze

Construct the deterministic multi-context genomic interval panel.

Output:

- interval manifest
- stratification provenance
- selection algorithm
- interval checksums
- frozen panel hash

## Phase 2C — Benchmark Expansion

Run the approved benchmark workflow only on datasets and regions frozen in 2A and 2B.

Output:

- new EXPERIMENT records
- new BENCHMARK_RUN records
- new EVENT records
- new OBSERVATION records
- source/provenance records

## Phase 2D — Identity Expansion

Apply the frozen biological identity layer to the expanded evidence.

Output:

- new VARIANT records where necessary
- new EVENT_VARIANT_LINK records
- unresolved identity records where necessary

## Phase 2E — Product and Generalization Validation

Build and test expanded product queries and evaluate the final frozen Phase 2 gate.

---

# 16. Compute Constraint

The project remains designed for low-cost execution.

Target paid-compute cost:

CAD 0 whenever practical.

Maximum additional paid compute without an explicit protocol amendment:

CAD 100.

Preferred resources:

- local macOS for metadata, validation, DuckDB, schemas, and small transformations,
- free Google Colab where additional compute is required,
- publicly hosted artifacts,
- deterministic resumable workflows.

---

# 17. Locked Phase 2 Validation Criteria

1. The authoritative Phase 1A archive remains byte-identical to its frozen SHA-256.

2. The authoritative Phase 1B archive remains byte-identical to SHA-256 `50bf597cbc13a051d5dda7201e9d7653dbc7b1762fef1b8300199641df6474fb`.

3. No Phase 1A or Phase 1B scientific record is modified by Phase 2.

4. Every admitted Phase 2 source satisfies the frozen source requirements and has documented provenance.

5. Dataset admission is independent of benchmark performance.

6. The final genomic context panel is frozen before Phase 2 benchmark outcomes are examined.

7. Region selection is deterministic and reproducible from recorded public inputs.

8. Phase 2 contains multiple genomic contexts and multiple chromosomes.

9. Phase 2 contains both SNV and indel benchmark evidence.

10. The expanded registry contains at least three distinct benchmark samples unless the source audit produces a documented MODIFY verdict before benchmarking.

11. Where paired public evidence permits, included samples preserve evidence from at least two sequencing technologies.

12. Biological VARIANT identifiers remain deterministic and assembly-specific.

13. No EVENT is silently merged across runs, samples, technologies, callers, or benchmark executions.

14. Representation-different or ambiguous identity remains UNRESOLVED unless a separately frozen and validated equivalence method exists.

15. Every new EVENT_VARIANT_LINK has complete provenance to its source EVENT, BENCHMARK_RUN, identity method/version, and originating Phase 2 selection record.

16. A variant-level product query can return evidence across multiple samples and technologies while preserving sample, experiment, run, event, observation, truth/query side, raw decision, and provenance.

17. The expanded registry introduces no reliability score, confidence score, trusted label, technology ranking, or forced consensus.

18. Re-running Phase 2 transformations on identical frozen inputs reproduces deterministic entity identifiers and scientific table contents.

19. All final Phase 2 release artifacts are checksum-manifested and independently verifiable after archive extraction.

20. The final Phase 2 report states limitations explicitly, including dataset-selection scope, benchmark truth limitations, unresolved representation equivalence, and the distinction between evidence aggregation and biological or clinical truth.

---

# 18. Outcome Gate

Phase 2 receives one final verdict:

PASS

All locked requirements are satisfied and the registry demonstrates valid generalization beyond the Phase 1 proof-of-concept.

MODIFY

The architecture remains scientifically viable, but one or more non-fatal requirements require a documented change before release.

STOP

A fundamental assumption fails, including but not limited to:

- provenance cannot be preserved,
- benchmark results are required to select datasets or regions,
- run-scoped evidence cannot remain immutable,
- variant identity produces unsafe cross-assembly or ambiguous merges,
- reproducibility cannot be achieved,
- product queries require scientifically unjustified evidence collapse.

Criteria may not be weakened after results are observed solely to obtain PASS.

---

# 19. Non-Goals

Phase 2 does not attempt to:

- build a new variant caller,
- rank sequencing technologies,
- identify a universally best caller,
- create a clinical interpretation database,
- infer pathogenicity,
- infer patient-level clinical truth,
- build a trust score,
- claim that benchmark truth is absolute biological truth,
- solve arbitrary representation equivalence without validation,
- replace IGV or other genome browsers.

---

# 20. Freeze Rule

This document must be hashed before Phase 2 source selection begins.

Any later scientific change requires:

1. a documented amendment,
2. justification,
3. a new protocol hash,
4. explicit identification of whether the change occurred before or after affected results were observed.
