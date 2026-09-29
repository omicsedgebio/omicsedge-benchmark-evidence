# Conceptual schema

The executable JSON Schemas in `schemas/` are the Phase 1A contract. Parquet
tables use the same six entities and DuckDB exposes them without collapsing
their identifiers.

| Entity | Grain | Identity and essential content |
|---|---|---|
| `EVENT` | One run-scoped comparator grouping or fallback source-record group | `event_id`; assembly/reference; 0-based interval; identity scope; benchmark run; source `BS` when present; derivation method; optional lookup key that is explicitly non-equivalence-bearing. |
| `EXPERIMENT` | One submitted pipeline applied to one sample and input technology condition | `experiment_id`; source corpus/submission; sample; technology/platform/coverage; pipeline, caller, aligner, basecaller and versions; metadata evidence artifacts; explicit unknown fields. |
| `BENCHMARK_RUN` | One immutable comparison invocation | `benchmark_run_id`; experiment; exact query/truth/BED/reference artifacts; core and padded intervals; comparator and engine versions; environment lock/digest; argv; run state; output artifacts and timestamps. |
| `OBSERVATION` | One truth- or query-side source record decision within one event and run | `observation_id`; event/run; side; raw and normalized decision; match kind/detail; raw VCF locus/alleles/genotype/filter; region state; source output artifact and record ordinal; origin. Multiple rows per event and side are allowed. |
| `SOURCE_ARTIFACT` | One byte-addressable input, metadata, software, or output object | `source_artifact_id`; URI; role; media type; byte size; version; hashes and verification state; retrieval time; license/reuse basis; local derivation state. |
| `PROVENANCE_LINK` | One directed lineage edge between typed registry entities | `provenance_link_id`; typed source/target refs; relation; transformation/software/parameters; timestamp; responsible agent. This represents lineage, not biological equivalence. |

## Cardinalities

- One `EXPERIMENT` has many `BENCHMARK_RUN` rows over time.
- One `BENCHMARK_RUN` uses exactly one query VCF, truth VCF, benchmark BED, and
  reference artifact in Phase 1A.
- One `BENCHMARK_RUN` has many run-scoped `EVENT` rows.
- One `EVENT` has one or more `OBSERVATION` rows; each side may have zero, one,
  or many source records.
- Every material entity may have many `PROVENANCE_LINK` rows.
- An artifact may be used by many runs, but a run never refers to an artifact by
  mutable filename alone.

## Storage keys

Identifiers are opaque stable strings. They are not derived solely from genomic
coordinates. A future content-addressed identifier scheme may be added only
after its serialization is specified and versioned.

Parquet partitions may use `corpus`, `sample`, and `benchmark_run_id` for
physical organization, but those paths are not semantic identity. DuckDB
foreign-key-like checks are performed during ingestion even where Parquet does
not enforce them.

## Required event-level query behavior

Given a run-scoped `event_id`, return its event bounds, all truth/query
observations, experiment condition, complete benchmark-run settings, and source
artifact lineage. A separate candidate-search query may use assembly, contig,
interval overlap, and normalized allele lookup, but its results must remain
separate events until an explicit future equivalence assertion exists.

The concrete DuckDB retrieval shape is locked in `sql/event_evidence.sql`.
