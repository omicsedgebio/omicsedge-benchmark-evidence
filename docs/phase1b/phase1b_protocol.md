# Project 003 — Phase 1B Protocol

## Status

FROZEN BEFORE PHASE 1B IMPLEMENTATION

## Project

OmicsEdge Benchmark Evidence Registry

## Phase

Phase 1B — Cross-Run Biological Variant Identity Layer

## Purpose

Phase 1A demonstrated that public benchmark inputs can be regenerated into
provenance-rich, run-scoped benchmark events and observations across independent
Illumina and Oxford Nanopore Technologies (ONT) experiments.

Phase 1B tests whether run-scoped benchmark events can be linked conservatively
to stable biological variant identities without altering, merging, or
reinterpreting the original Phase 1A events or observations.

The purpose of this phase is identity resolution, not reliability scoring.

## Authoritative Phase 1A Input

Archive:

data/phase1a/omicsedge_phase1a_results.tar.gz

SHA-256:

6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202

Extracted results:

data/phase1a/omicsedge_phase1a_results/

The extracted Phase 1A result bundle must pass all checks in:

data/phase1a/omicsedge_phase1a_results/checksums.sha256

Phase 1A status:

PHASE1A_COMPUTE_PASS

Phase 1A registry contains:

- 2 experiments
- 2 benchmark runs
- 3,602 run-scoped events
- 7,204 observations
- 10,871 provenance links
- 1,666 cross-run candidate relationships
- 977,839 assessable core bases

The candidate relationships are currently explicitly unresolved:

CROSS_RUN_EQUIVALENCE_UNRESOLVED

## Scientific Question

Can two or more run-scoped benchmark events be linked to the same
assembly-specific biological variant using deterministic, provenance-preserving,
scientifically defensible rules?

## Critical Architectural Rule

Same biological variant does not mean same benchmark event.

Phase 1A EVENT records are comparator- and run-scoped objects.

Phase 1B must not merge, replace, rewrite, renumber, or otherwise modify those
EVENT records.

Instead, Phase 1B introduces a separate biological identity layer.

Conceptually:

VARIANT
    ^
    |
EVENT_VARIANT_LINK
    ^
    |
EVENT
    |
    v
OBSERVATION

Multiple run-scoped EVENT records may link to the same VARIANT when identity is
supported.

## Immutable Phase 1A Objects

The following Phase 1A entities are immutable inputs:

- EVENT
- OBSERVATION
- EXPERIMENT
- BENCHMARK_RUN
- SOURCE_ARTIFACT
- PROVENANCE_LINK

Phase 1B may reference them but must not mutate their scientific content.

## Phase 1B Entities

### VARIANT

Represents an assembly-specific biological allele identity.

Minimum fields:

- variant_id
- assembly
- contig
- normalized_start_0based
- normalized_end_0based
- normalized_ref
- normalized_alt
- normalization_method
- reference_artifact_id
- identity_schema_version

Variant identity must include assembly.

A coordinate alone is never sufficient identity.

### EVENT_VARIANT_LINK

Represents a provenance-backed assertion connecting one Phase 1A EVENT to one
Phase 1B VARIANT.

Minimum fields:

- event_variant_link_id
- event_id
- variant_id
- benchmark_run_id
- identity_status
- identity_method
- identity_method_version
- evidence
- provenance
- created_from_candidate
- phase1a_candidate_status

## Allowed Identity States

Phase 1B must use explicit categorical states.

Allowed states:

1. EXACT_NORMALIZED_ALLELE

   The compared events resolve to exactly the same normalized assembly,
   contig, start, REF, and ALT representation under the locked normalization
   procedure.

2. REPRESENTATION_EQUIVALENCE_SUPPORTED

   Different record representations are demonstrated to encode the same
   biological allele or haplotype under an explicitly documented deterministic
   equivalence procedure.

   This state must not be implemented or assigned unless Phase 1B contains a
   validated equivalence procedure.

3. NON_EQUIVALENT

   The events have sufficient comparable information and are demonstrably not
   the same biological allele under the locked identity rules.

4. UNRESOLVED

   Available evidence is insufficient to establish equivalence or
   non-equivalence safely.

No continuous confidence score is allowed.

No reliability score is allowed.

No trusted/untrusted label is allowed.

## Phase 1B Initial Scope

Phase 1B operates only on the Phase 1A cross-run candidate set.

Input:

data/phase1a/omicsedge_phase1a_results/cross_run_candidates.tsv

Expected candidate count:

1,666

Do not expand to:

- additional chromosomes
- additional genomic intervals
- additional samples
- additional truth versions
- additional submissions
- additional sequencing technologies

until the Phase 1B gate is completed.

## Assembly

GRCh38

Assembly identity is mandatory in every VARIANT identity.

Variants from different assemblies must never share a VARIANT identity merely
because coordinates or alleles appear similar.

## Reference

The same locked GRCh38 reference identity used in Phase 1A must be retained as
the reference provenance for Phase 1B.

REF assertions must be consistent with the locked reference.

## First Identity Method

The first supported identity method is deterministic exact normalized allele
identity.

Two candidate events may receive EXACT_NORMALIZED_ALLELE only when all of the
following are identical:

- assembly
- contig
- normalized_start_0based
- normalized_end_0based
- normalized_ref
- normalized_alt

The method must be deterministic.

The same inputs must always produce the same VARIANT identifier.

## Variant Identifier

The VARIANT identifier must be deterministic and content-derived.

Its input must include at minimum:

- identity schema version
- assembly
- contig
- normalized start
- normalized end
- normalized REF
- normalized ALT

The identifier must not depend on:

- processing order
- row number
- experiment
- sequencing technology
- benchmark run
- Python object identity
- wall-clock time
- random UUID generation

## Representation Equivalence

Phase 1B must not silently infer equivalence from nearby coordinates or similar
alleles.

Potential representation-equivalence logic must remain separate from exact
normalized identity.

Examples requiring explicit testing include:

- left-shiftable indels
- right-shiftable equivalent representations
- multiallelic decomposition
- overlapping alleles
- complex substitutions
- different representations of the same local haplotype

If equivalence cannot be demonstrated deterministically, the correct state is:

UNRESOLVED

## Event Preservation

Phase 1B must preserve:

- original EVENT IDs
- original benchmark run IDs
- original observation decisions
- original truth/query sides
- raw comparator decisions
- raw match kinds
- original provenance

Creating a shared VARIANT must never imply that the underlying benchmark
observations agree.

For example, two events may link to one VARIANT while retaining conflicting
benchmark outcomes.

That disagreement is scientifically meaningful and must remain visible.

## Provenance

Every EVENT_VARIANT_LINK must be traceable to:

- the originating Phase 1A EVENT
- the Phase 1A benchmark run
- the Phase 1A cross-run candidate where applicable
- the identity method
- the identity method version
- the exact Phase 1A archive identity

Every generated Phase 1B artifact must have:

- SHA-256
- derivation provenance
- version information

## Product Query Requirement

Phase 1B must produce a query capable of answering:

Given one GRCh38 biological variant, what public benchmark observations exist
for it across the Phase 1A Illumina and ONT experiments?

The query result must preserve at least:

- variant_id
- event_id
- event_variant_link_id
- experiment_id
- benchmark_run_id
- technology
- truth/query side
- raw decision
- raw match kind
- source genotype
- source filter
- comparator identity
- truth version
- identity status
- identity method
- provenance context

The query must not collapse contradictory observations.

## Synthetic Adversarial Test Set

Before interpreting aggregate Phase 1B outcomes, synthetic tests must cover at
minimum:

1. identical SNV representation
2. different SNVs at the same coordinate
3. identical insertion representation
4. identical deletion representation
5. left-shiftable indel representations
6. multiallelic decomposition
7. overlapping but non-equivalent alleles
8. equivalent local haplotype represented differently
9. same coordinate but different REF
10. same coordinate and REF but different ALT
11. same allele coordinates on different assemblies
12. deliberately ambiguous representation

Expected behavior must be specified before running these tests.

Ambiguous cases must resolve to UNRESOLVED.

## Locked Phase 1B Validation Criteria

Phase 1B PASS requires all applicable locked criteria below to pass.

1. The authoritative Phase 1A archive SHA-256 equals
   6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202.

2. All 35 detached Phase 1A checksums pass before Phase 1B processing begins.

3. The Phase 1A candidate input contains exactly 1,666 candidate relationships,
   unless a discrepancy is demonstrated to originate from the frozen Phase 1A
   bundle itself.

4. No Phase 1A EVENT, OBSERVATION, EXPERIMENT, BENCHMARK_RUN, SOURCE_ARTIFACT,
   or PROVENANCE_LINK scientific record is modified by Phase 1B.

5. Every Phase 1B candidate is accounted for exactly once in final identity
   accounting. No candidate disappears silently.

6. Every generated VARIANT identifier is deterministic and content-derived from
   the locked identity fields.

7. Exact normalized identity requires equality of assembly, contig, normalized
   start, normalized end, normalized REF, and normalized ALT.

8. Assembly is part of biological variant identity and cross-assembly records
   are never merged by coordinate/allele similarity alone.

9. REF assertions are consistent with the locked Phase 1A GRCh38 reference
   provenance.

10. Synthetic adversarial cases pass their predeclared expected outcomes,
    including indels, multiallelic records, overlaps, representation differences,
    and ambiguous cases.

11. Ambiguous or unsupported representation equivalence resolves to UNRESOLVED,
    never forced equivalence.

12. Every EVENT_VARIANT_LINK has complete provenance to the Phase 1A event,
    benchmark run, identity method/version, and candidate relationship where
    applicable.

13. Re-running Phase 1B on identical inputs produces identical VARIANT IDs,
    EVENT_VARIANT_LINK IDs, classifications, and row counts.

14. A variant-level DuckDB query returns linked evidence from both benchmark
    runs where available while retaining the original event IDs, experiment
    context, truth/query sides, raw decisions, and provenance.

15. Phase 1B introduces no reliability score, confidence score, trusted label,
    ranking, or forced consensus across technologies.

## Outcome Gate

At completion, assign exactly one Phase 1B verdict:

### PASS

Use when the identity layer is deterministic, provenance-complete,
scientifically defensible, adversarial tests pass, all candidate relationships
are accounted for, and variant-level queries preserve original benchmark
context.

### MODIFY

Use when the basic biological identity architecture remains scientifically
valid but one or more implementation or representation-equivalence limitations
must be corrected before expansion.

### STOP

Use when biological identity cannot be established without unsafe merging,
unverifiable assumptions, loss of comparator context, or scientifically
unsupported equivalence assertions.

## Explicit Non-Goals

Phase 1B does not:

- create a new variant caller
- predict variant truth
- produce a universal reliability score
- rank sequencing technologies
- declare one technology superior
- replace GIAB
- replace hap.py or RTG vcfeval
- alter Phase 1A benchmark decisions
- merge run-scoped comparator events
- expand to whole-genome benchmarking
- train a machine-learning model

## Compute Constraint

Phase 1B should initially run locally against the compact Phase 1A result bundle.

Do not download whole-genome BAM, CRAM, FASTQ, or other large sequencing data.

Do not rerun the Phase 1A genomic comparison unless a scientifically justified
requirement is identified.

Google Colab or other external compute should only be introduced if a later
locked Phase 1B step demonstrably requires reference-based haplotype evaluation
that cannot reasonably be performed from the compact local inputs.

## Freeze Rule

This protocol is frozen before Phase 1B implementation and before aggregate
identity outcomes from the 1,666 candidate relationships are inspected.

Any change to the scientific identity rules or validation criteria after
viewing Phase 1B outcomes must be:

- explicitly documented
- scientifically justified
- versioned
- distinguished from the original frozen protocol
