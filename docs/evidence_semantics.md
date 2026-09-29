# Evidence semantics

## Observation, not label

`TP`, `FP`, `FN`, `N`, `UNK`, and `IGN` are outcomes of a particular
comparison. They are not intrinsic properties of a genomic allele. The same
source record can receive a different outcome under a different truth release,
benchmark BED, preprocessing rule, comparator, comparator version, or parameter
set.

Each normalized observation therefore names exactly one benchmark run, one
run-scoped event, one side (`TRUTH` or `QUERY`), and one or more source records.
Truth and query outcomes are stored separately. A genotype mismatch may produce
truth-side `FN` and query-side `FP` observations within the same superlocus.

## Event identity

For Phase 1A, an `EVENT` is a comparison-scoped grouping, normally the hap.py
`BS` superlocus emitted by one `BENCHMARK_RUN`. It is safe to use as a unit of
retrieval within that run. Its identifier is never reused across runs.

A normalized allele key may be stored as a lookup aid for a single source
record. It does not establish biological equivalence. Coordinate overlap,
identical normalized alleles, or lifted coordinates may identify candidates
for later review, but they must not silently merge events. Phase 1A defines no
cross-run canonical-event assertion.

If hap.py emits no `BS` value for a record, normalization creates a deterministic
run-scoped source-record event and records that derivation. It must not invent a
cross-record superlocus.

## Reference and coordinate rules

- Assembly is `GRCh38`, bound to the exact reference artifact in the run.
- Registry intervals are 0-based, half-open.
- Original VCF `CHROM` and 1-based `POS` are retained verbatim in observation
  source fields.
- Normalized start/end fields are derived and name their normalization method
  and version.
- Liftover is not identity and is not used in Phase 1A.
- Events intersecting the padded extraction boundary but not wholly contained
  in the locked core interval are retained as boundary diagnostics and excluded
  from the Phase 1A evidence export.

## Region and absence semantics

The following states are distinct:

- `INSIDE`: wholly inside the effective benchmark region;
- `OUTSIDE`: wholly outside it;
- `BORDER`: touches or crosses its boundary;
- `UNKNOWN`: membership was not computed or cannot be established;
- comparator decision `N`, `UNK`, or `IGN` as emitted by the tool;
- a filtered source call;
- no source record in a side of a superlocus; and
- an artifact or field absent from the public corpus.

Absence must never be rewritten as `FN`, `FP`, `N`, or `UNK` without comparator
evidence. The raw comparator value and the normalized decision are both kept.

## Unknowns

`UNKNOWN` means the value is not established by attributable evidence. It is a
positive semantic state, not a null shortcut. Null is reserved for a field that
is structurally inapplicable. Notably, the exact NeuSomatic version for `60Z59`
and the PEPPER/DeepVariant versions for `RU88N` remain `UNKNOWN`.

## Regeneration and provenance

All Phase 1A observations have `observation_origin = REGENERATED`. Provenance
must connect each observation to:

1. its annotated comparator output record;
2. the benchmark run and exact command;
3. the selected query, truth, BED, and reference artifacts;
4. the locked comparison environment;
5. normalization software/version and transformation time; and
6. the source metadata that supports experiment claims.

Copied, transformed, regenerated, and inferred assertions are distinguished.
No observation is publishable if its raw artifact lineage is broken.

## Comparability

The two Phase 1A runs are comparable only at the level explicitly shared by
their run contracts: sample, reference, truth, BED, interval, comparator,
parameters, and normalization code. Pipeline and sequencing technology differ.
Exact source-record matches across runs may be displayed together as candidate
correspondences, but the run-scoped event rows stay distinct.

