# Project 003 — Phase 1B Gate Report

Verdict: **PASS**

Frozen criteria: 15/15 PASS

## Scope

- Cross-run biological identity layer for the frozen Phase 1A candidate set.
- Candidates: 1,666
- Materialized VARIANT records: 1,666
- EVENT_VARIANT_LINK records: 3,332
- Representation-equivalence inference: not enabled in v1.
- Reliability/confidence/trust scoring: not generated.

## Locked validation

1. PASS — The authoritative Phase 1A archive SHA-256 equals 6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202.
2. PASS — All 35 detached Phase 1A checksums pass before Phase 1B processing begins.
3. PASS — The Phase 1A candidate input contains exactly 1,666 candidate relationships, unless a discrepancy is demonstrated to originate from the frozen Phase 1A bundle itself.
4. PASS — No Phase 1A EVENT, OBSERVATION, EXPERIMENT, BENCHMARK_RUN, SOURCE_ARTIFACT, or PROVENANCE_LINK scientific record is modified by Phase 1B.
5. PASS — Every Phase 1B candidate is accounted for exactly once in final identity accounting. No candidate disappears silently.
6. PASS — Every generated VARIANT identifier is deterministic and content-derived from the locked identity fields.
7. PASS — Exact normalized identity requires equality of assembly, contig, normalized start, normalized end, normalized REF, and normalized ALT.
8. PASS — Assembly is part of biological variant identity and cross-assembly records are never merged by coordinate/allele similarity alone.
9. PASS — REF assertions are consistent with the locked Phase 1A GRCh38 reference provenance.
10. PASS — Synthetic adversarial cases pass their predeclared expected outcomes, including indels, multiallelic records, overlaps, representation differences, and ambiguous cases.
11. PASS — Ambiguous or unsupported representation equivalence resolves to UNRESOLVED, never forced equivalence.
12. PASS — Every EVENT_VARIANT_LINK has complete provenance to the Phase 1A event, benchmark run, identity method/version, and candidate relationship where applicable.
13. PASS — Re-running Phase 1B on identical inputs produces identical VARIANT IDs, EVENT_VARIANT_LINK IDs, classifications, and row counts.
14. PASS — A variant-level DuckDB query returns linked evidence from both benchmark runs where available while retaining the original event IDs, experiment context, truth/query sides, raw decisions, and provenance.
15. PASS — Phase 1B introduces no reliability score, confidence score, trusted label, ranking, or forced consensus across technologies.

## Scientific interpretation

Phase 1B preserves Phase 1A run-scoped events and observations while adding a separate biological VARIANT identity layer.
Exact normalized allele identity is deterministic and provenance-backed.
No representation-equivalence claim is made where deterministic v1 rules do not support one.
Variant identity does not imply agreement between benchmark observations or sequencing technologies.
