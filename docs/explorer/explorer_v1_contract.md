# OmicsEdge Benchmark Evidence Explorer v1
## Frozen data contract

Status: FROZEN_BEFORE_IMPLEMENTATION
Project: OmicsEdgeBio Project 003
Scientific release: v1.0.0
Zenodo DOI: 10.5281/zenodo.23085673

## Purpose

The Evidence Explorer is a read-only product layer over the frozen
Project 003 benchmark evidence.

It does not recompute benchmark outcomes and does not alter any Phase 1
or Phase 2 scientific record.

The authoritative scientific source is the Project 003 v1.0.0 release.

Final release archive:

results/phase2e/omicsedge_phase2_final_results.tar.gz

SHA-256:

186cbed74fa718a728f7a24b43d58118a308165fae385eb95cc4cb4444788ca3

## Scientific model

The Explorer preserves the Project 003 entity model:

VARIANT <- EVENT_VARIANT_LINK <- EVENT -> OBSERVATION

Supporting entities include:

EXPERIMENT
BENCHMARK_RUN
SOURCE_ARTIFACT
PROVENANCE_LINK

Biological VARIANT identity and run-scoped EVENT identity remain separate.

## Authority mapping

### Phase 1

Phase 1A is authoritative for:

- HG002 experiments
- benchmark runs
- events
- observations
- source artifacts
- provenance

Phase 1B is authoritative for:

- exact biological VARIANT identities
- EVENT_VARIANT_LINK records
- identity method and identity provenance

Phase 1B evaluated cross-run candidate relationships only.

Therefore a Phase 1A EVENT without a Phase 1B EVENT_VARIANT_LINK must not be
reported as UNRESOLVED.

Its Explorer identity state is:

NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY

### Phase 2

Phase 2C is authoritative for:

- HG003 and HG004 experiments
- benchmark runs
- events
- observations
- source artifacts
- provenance

Phase 2D is authoritative for:

- biological VARIANT identities
- EVENT_VARIANT_LINK records
- exact identity status
- explicit unresolved identity accounting
- identity provenance

A Phase 2 event recorded by Phase 2D as unresolved must remain:

UNRESOLVED

No variant identity may be guessed for such an event.

## Explorer scope

The unified Explorer represents:

Samples:

- HG002
- HG003
- HG004

Technologies:

- Illumina
- Oxford Nanopore

Assembly:

- GRCh38

Benchmark comparator:

- hap.py 0.3.15

Comparison engine:

- vcfeval 3.12.1

## Frozen registry totals

Phase 1A:

- 3,602 EVENT records
- 7,204 OBSERVATION records

Phase 1B:

- 1,666 VARIANT records
- 3,332 EVENT_VARIANT_LINK records

Phase 2C:

- 7,951 EVENT records
- 15,902 OBSERVATION records

Phase 2D:

- 2,612 biological VARIANT identities
- 7,891 exact EVENT_VARIANT_LINK records
- 60 explicitly UNRESOLVED EVENT records

Unified event count:

- 11,553

Unified observation count:

- 23,106

The Explorer implementation must derive and validate all displayed totals
from the frozen authorities rather than trusting hard-coded presentation data.

## Identity states

The Explorer exposes exactly these high-level identity states:

### EXACT_NORMALIZED_ALLELE

A biological VARIANT identity was established by the frozen exact normalized
allele identity procedure.

### UNRESOLVED

Phase 2D explicitly evaluated the EVENT but could not establish an exact
biological VARIANT identity.

The unresolved reason must be preserved.

### NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY

The EVENT was preserved in Phase 1A but was not part of the Phase 1B
cross-run candidate identity operation.

This state is not equivalent to UNRESOLVED.

## Primary Explorer entities

### Variant record

A resolved biological variant entry must expose:

- variant_id
- assembly
- contig
- normalized_start_0based
- normalized_end_0based
- normalized_ref
- normalized_alt
- identity_schema_version
- phase_origin
- linked_event_count
- observation_count
- sample_ids
- technologies

### Event record

Every EVENT must expose:

- event_id
- phase_origin
- benchmark_run_id
- assembly
- contig
- start_0based
- end_0based
- identity_state
- variant_id when established
- unresolved_reason when explicitly unresolved
- observation_count

### Observation record

Every OBSERVATION must preserve, where present:

- observation_id
- event_id
- benchmark_run_id
- side
- observation_origin
- raw_decision
- normalized_decision
- raw_match_kind
- raw_variant_type
- raw_location_type
- region_status
- source_contig
- source_pos_1based
- source_ref
- source_alt
- source_genotype
- source_filter
- quality_score
- normalization_method
- normalization_version
- normalized_start_0based
- normalized_end_0based
- normalized_ref
- normalized_alt
- source_output_artifact_id

### Experiment and run context

Evidence retrieval must preserve:

- experiment_id
- sample_id
- technology
- platform
- coverage
- pipeline_name
- pipeline_version
- caller_names
- caller_versions
- benchmark_run_id
- comparator
- comparator_version
- engine
- engine_version
- truth_artifact_id
- query_artifact_id
- reference_artifact_id
- benchmark region artifact
- runtime image digest when available

## Provenance

The Explorer must retain enough provenance to trace displayed evidence back
to the frozen authority records.

The exporter must not rewrite provenance into unsupported claims.

Artifact IDs, archive checksums, identity methods, benchmark-run identifiers,
and applicable provenance-link identifiers must remain attributable.

## Search contract

Explorer v1 must support deterministic lookup by:

1. exact variant_id;
2. chromosome and position;
3. chromosome, position, REF, and ALT;
4. sample;
5. technology;
6. raw comparator decision;
7. raw variant type;
8. identity state.

Search is retrieval only.

Search criteria must not merge EVENTS or infer new biological equivalence.

## Coordinate contract

Registry coordinates are:

GRCh38
0-based
half-open

Source VCF positions remain available separately as original 1-based source
coordinates.

The user interface must label coordinate conventions explicitly.

## Genomic-context contract

Phase 2 selected windows have frozen context-selection metadata.

A selected window context must not automatically be assigned to every variant
inside that window.

Per-variant context labels may only be exposed after deterministic coordinate
intersection against the frozen stratification resources.

Any such context field must identify itself as a derived Explorer annotation
and retain the source stratification provenance.

Until that implementation exists, the Explorer must not claim a per-variant
HOMOPOLYMER, TANDEM_REPEAT, LOW_MAPPABILITY, SEGMENTAL_DUPLICATION, or
NON_DIFFICULT label merely from window membership.

## Output contract

The deterministic exporter will create:

results/explorer_v1/explorer_manifest.json
results/explorer_v1/variants.json
results/explorer_v1/events.json
results/explorer_v1/evidence.json
results/explorer_v1/unresolved_events.json
results/explorer_v1/checksums.sha256

### explorer_manifest.json

Must contain:

- schema version
- Project 003 release identifier
- authoritative archive SHA-256
- creation method/version
- entity counts
- sample values
- technology values
- identity-state counts
- output file SHA-256 values
- scientific-boundary flags

### variants.json

Search/index representation of resolved biological VARIANT identities.

### events.json

All 11,553 run-scoped EVENT records, including resolved, unresolved, and
Phase 1 identity-not-evaluated records.

### evidence.json

Observation-level evidence joined to experiment, run, event, and biological
identity context without collapsing observations.

### unresolved_events.json

Explicit Phase 2D UNRESOLVED events only.

It must not contain Phase 1 events that were outside the Phase 1B candidate
identity operation.

## Determinism

Two independent executions against the same frozen v1.0.0 archive must produce
byte-identical Explorer outputs.

JSON output must therefore use:

- UTF-8
- deterministic key ordering
- deterministic row ordering
- stable separators
- newline-terminated files

No timestamps generated at export time may participate in file content.

## Validation requirements

Explorer export validation must prove:

1. authoritative release archive SHA-256 matches the frozen value;
2. all nested authority checksum manifests pass;
3. Phase 1 counts reconcile;
4. Phase 2 counts reconcile;
5. unified EVENT count is 11,553;
6. unified OBSERVATION count is 23,106;
7. every observation references exactly one EVENT;
8. every EVENT references exactly one benchmark run;
9. every benchmark run references exactly one experiment;
10. each EVENT maps to at most one biological VARIANT;
11. every Phase 2 EVENT is accounted for by Phase 2D;
12. exactly 60 Phase 2 events remain UNRESOLVED;
13. unresolved events receive no guessed variant_id;
14. Phase 1 events outside Phase 1B identity candidates are not mislabeled
    UNRESOLVED;
15. raw benchmark decisions are preserved;
16. query and truth observations remain separate;
17. no reliability score is generated;
18. no trust score is generated;
19. no consensus decision is generated;
20. no technology ranking is generated;
21. output is deterministic across two executions;
22. all output checksums validate.

## Forbidden derived fields

The exporter and UI must not generate:

- reliability_score
- trust_score
- confidence_score
- consensus
- consensus_decision
- trusted
- technology_winner
- caller_winner
- preferred_technology
- pathogenicity
- clinical_significance

## Scientific boundaries

The Evidence Explorer is not:

- a variant caller;
- a consensus caller;
- a reliability scoring system;
- a technology ranking system;
- a caller ranking system;
- a clinical interpretation system;
- a pathogenicity database;
- a claim that GIAB represents perfect biological truth.

TP, FP, FN, N, UNK, and IGN remain outcomes of a particular benchmark
comparison, not intrinsic properties of an allele.

## Website integration rule

omicsedge.bio will consume the validated Explorer export.

The website must not independently reconstruct scientific identity,
provenance, benchmark outcome, or unresolved-state logic.

Scientific logic remains in the Project 003 repository.
