# Phase 2 benchmark-run schema extension

## Reason

The original Project 003 `BENCHMARK_RUN` schema models a benchmark run with
one `core_interval` and one `padded_interval`.

That representation is valid for the frozen Phase 1A HG002 chr20 experiment,
but it cannot faithfully represent the frozen Phase 2 panel, which contains
50 selected windows, 541 assessable BED segments, and spans 19 chromosomes.

The Phase 1 schema is therefore left unchanged.

Phase 2 uses a versioned `BENCHMARK_RUN` schema with explicit references to:

- the frozen benchmark region-set artifact,
- its SHA-256,
- a separately derived padded retrieval-region artifact,
- its SHA-256,
- retrieval padding,
- multi-region panel geometry.

This prevents a multi-chromosome benchmark from being misrepresented as one
synthetic contiguous genomic interval.

## Compatibility

Phase 1 records remain schema version `1.0.0`.

Phase 2 multi-region benchmark-run records use schema version `2.0.0`.

No Phase 1 entity or frozen Phase 1B artifact is modified.

## Phase 2 frozen panel

The Phase 2 benchmark region set is:

`data/phase2/selected_assessable_segments.bed`

SHA-256:

`4c77e17c3dec47051cb9b29fa14fee67f31a559785417d083f4f7bcacb05cd26`

Geometry:

- 50 selected windows
- 541 assessable segments
- 5 genomic contexts
- 19 chromosomes
- 1,162,571 assessable bases
- chr20 excluded

The padded retrieval region set is generated deterministically at runtime
using 1,000 bp padding. Its SHA-256 is recorded independently and does not
change the frozen benchmark domain.
