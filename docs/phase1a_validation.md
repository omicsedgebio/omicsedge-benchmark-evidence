# Locked Phase 1A PASS/FAIL criteria

These criteria were locked before genomic inputs were downloaded or benchmark
results were inspected. Precision, recall, F1, TP count, FP count, FN count,
and agreement between technologies are not success thresholds.

Phase 1A is **PASS** only if every criterion below passes for both selected
submissions.

## Input and provenance

1. The query artifact URL, byte size, and published SHA-256 match the manifest.
2. Truth, TBI, BED, reference, FAI, and GZI names/URLs match the manifest; their
   downloaded byte sizes match the public listing and locally computed SHA-256
   values are recorded. Published reference MD5 values also match.
3. Every derived slice, index, SDF, annotated VCF, log, Parquet file, and DuckDB
   file is a separate artifact with a SHA-256 and a provenance edge.
4. Experiment claims resolve to the pinned metadata artifacts. Unknown caller
   versions remain the literal `UNKNOWN`.
5. All observations are marked `REGENERATED`; none is labeled as an original
   precisionFDA event decision.

## Locked run contract

6. Core/padded intervals, truth, BED, reference, comparator versions, engine,
   arguments, and thread count equal the checked-in lock. No interval is chosen
   or altered after viewing outcomes.
7. The core interval intersects at least one base of the v4.2.1 benchmark BED.
   Zero assessable bases is FAIL, not permission to substitute an interval.
8. Runtime-reported hap.py is 0.3.15 and RTG is 3.12.1; the container/derived
   image content digest and all auxiliary tool versions are recorded.
9. Each hap.py process exits zero and produces a readable indexed annotated VCF,
   metrics output, stdout, and stderr. Empty, truncated, or silently skipped
   comparison output is FAIL.

## Event semantics and normalization

10. The annotated VCF exposes separate `TRUTH` and `QUERY` samples and the
    expected GA4GH fields needed for decisions and grouping (`BD`, `BK`, and
    `BS`, allowing a documented source-record fallback only where `BS` is
    absent).
11. Every annotated source record in the padded output is either normalized or
    retained as an explicit rejected/boundary diagnostic; no record disappears
    silently.
12. Raw truth/query decision, match-kind, filter, genotype, source coordinates,
    and source record ordinal are retained. Normalized values do not overwrite
    raw values.
13. Each exported observation is wholly in the core interval, resolves to
    exactly one run-scoped event and benchmark run, and has complete lineage to
    an annotated output artifact and all four scientific inputs.
14. There is at least one exported event and at least one observation for each
    benchmark run. This is a pipeline-viability requirement, not a minimum
    accuracy requirement.
15. Decision counts derived from normalized observations reconcile exactly with
    the corresponding core-interval annotated records by side and raw decision.

## Storage and query

16. All six entity collections validate against their versioned JSON Schemas;
    identifiers are unique and every reference/provenance endpoint resolves.
17. Parquet round-trip preserves row counts, identifiers, integers, booleans,
    lists, explicit `UNKNOWN` strings, and null/inapplicable distinctions.
18. DuckDB views return the same counts as Parquet and the event-level query
    returns, for a selected run-scoped event, all observations plus experiment,
    run, artifact, and provenance context.
19. Candidate cross-run lookup does not merge run-scoped event IDs and labels
    coordinate/allele hits as candidates rather than established equivalence.
20. The complete run manifest, validation report, and output checksums are
    written before the Colab session ends.

Any failed item makes the overall result **FAIL**. A failed run may be retained
as an auditable benchmark-run record, but its observations cannot enter the
Phase 1A evidence export. Changing a locked input, interval, tool, or semantic
rule requires a new documented Phase 1A revision before rerunning.

