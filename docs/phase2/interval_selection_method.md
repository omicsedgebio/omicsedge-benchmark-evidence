# Project 003 — Phase 2B Deterministic Interval-Selection Method

## Status

FROZEN BEFORE HG003/HG004 BENCHMARK-BED DOWNLOAD AND BEFORE QUERY-VCF DOWNLOAD

## Purpose

Define the deterministic procedure used to select the Phase 2 genomic interval panel.

The procedure must not use:

- query VCF contents,
- benchmark TP/FP/FN outcomes,
- precision,
- recall,
- concordance,
- variant density,
- technology agreement,
- caller performance.

Only frozen provenance, genomic coordinates, GIAB benchmark regions, and GIAB v3.6 stratification membership may be used.

---

## 1. Frozen Inputs

Phase 2 protocol SHA-256:

`6234485e8916fd30a335c761a62668b617cb148b5b5a1753d12fd7765fa1633f`

Admitted source manifest SHA-256:

`55ebf63901ac0c118cb5ec687b49cc81cf680bb9357246ba2f6138b27a29641f`

Downloaded context BED manifest SHA-256:

`977bf8110db8e26486eaea51d138cd02264da4b26b29fd9c29c595e3bf405cc5`

GIAB stratification version:

`v3.6`

Reference assembly:

`GRCh38`

---

## 2. Samples

The Phase 2 interval panel will be shared across:

- HG003
- HG004

The same genomic panel must be used for both samples and both sequencing technologies.

---

## 3. Benchmark-Region Universe

Before interval selection, obtain the frozen GIAB v4.2.1 GRCh38 benchmark BED for:

- HG003
- HG004

Define:

`SHARED_CALLABLE`

as the genomic intersection of the HG003 and HG004 benchmark BEDs.

Only bases contained in `SHARED_CALLABLE` are eligible for Phase 2 benchmarking.

This prevents sample-specific region selection from confounding cross-sample comparison.

---

## 4. Chromosome Scope

Only autosomes are eligible:

- chr1 through chr22

`chr20` is excluded from Phase 2 interval selection because Phase 1 used chr20.

This guarantees that the generalization test expands beyond the Phase 1 genomic chromosome.

Sex chromosomes and alternate/unplaced contigs are excluded from the Phase 2 v1 panel.

---

## 5. Frozen Contexts

Exactly five GIAB v3.6 contexts are used.

### NON_DIFFICULT

`Union/GRCh38_notinalldifficultregions.bed.gz`

### HOMOPOLYMER

`LowComplexity/GRCh38_AllHomopolymers_ge7bp_imperfectge11bp_slop5.bed.gz`

### TANDEM_REPEAT

`LowComplexity/GRCh38_AllTandemRepeats.bed.gz`

### LOW_MAPPABILITY

`Mappability/GRCh38_lowmappabilityall.bed.gz`

### SEGMENTAL_DUPLICATION

`SegmentalDuplications/GRCh38_segdups.bed.gz`

No additional context may be substituted after benchmark outcomes are observed.

---

## 6. Nominal Window Size

Each selected interval begins as a fixed:

`25,000 bp`

nominal genomic window.

For each eligible source stratification BED record:

1. compute the integer midpoint of the BED record,
2. center a 25,000 bp nominal window on that midpoint,
3. use 0-based half-open coordinates,
4. clip start to >= 0 where required.

Nominal window width must otherwise remain 25,000 bp.

---

## 7. Callable Intersection

For each nominal candidate window:

`ASSESSABLE_SEGMENTS = nominal_window ∩ SHARED_CALLABLE`

The nominal window remains the stable selection identity.

Benchmark execution uses only its `ASSESSABLE_SEGMENTS`.

A candidate is eligible only when the total assessable length is at least:

`5,000 bp`

This threshold is frozen before inspecting query variants or benchmark outcomes.

---

## 8. Context Anchor Requirement

The midpoint used to generate the candidate must originate from a record in the corresponding frozen context BED.

Therefore each candidate has an explicit context anchor.

A selected window may overlap other GIAB contexts.

Such overlap must be retained as metadata and must not cause retrospective reclassification or exclusion.

The primary context is the context whose BED generated the candidate.

---

## 9. Candidate Identity

Each eligible candidate receives a deterministic candidate ID.

The canonical payload is:

- phase = `2B`
- assembly = `GRCh38`
- context_id
- chromosome
- nominal_start_0based
- nominal_end_0based
- source_context_bed_sha256
- shared_callable_definition

Serialize the payload as canonical JSON:

- sorted keys
- compact separators
- UTF-8

Candidate ID:

`phase2-window:sha256:<SHA256(canonical_payload)>`

---

## 10. Candidate Ordering

Candidate selection must not use genomic variant content.

For each eligible candidate compute:

`selection_hash = SHA256("PROJECT003_PHASE2B|" + candidate_id)`

Candidates are ordered lexicographically by:

1. `selection_hash`
2. chromosome
3. nominal start
4. candidate ID

This produces a deterministic pseudo-randomized ordering independent of benchmark outcome.

---

## 11. Number of Selected Windows

Select exactly:

`10 windows per context`

for:

`50 total nominal windows`

provided the frozen callable/context inputs permit this.

If fewer than 10 valid candidates exist for a context, Phase 2B receives `MODIFY` and the shortage must be documented before any benchmark outcome is examined.

The selection requirement must not be weakened after benchmark results are observed.

---

## 12. Chromosome Diversity

Within each context:

- selected windows must span at least 5 distinct chromosomes,
- no chromosome may contribute more than 2 selected windows.

Selection proceeds down deterministic candidate order.

A candidate is accepted only if accepting it does not make the maximum-two-per-chromosome constraint impossible to respect.

After 10 selections, at least 5 distinct chromosomes must be represented.

If that cannot be achieved, Phase 2B receives `MODIFY`.

---

## 13. Cross-Context Window Overlap

Selected nominal windows from different contexts should not substantially duplicate the same genomic interval.

A new candidate is rejected when its nominal window overlaps any previously selected nominal window by:

`>= 50% of the smaller window`

Context processing order is frozen as:

1. NON_DIFFICULT
2. HOMOPOLYMER
3. TANDEM_REPEAT
4. LOW_MAPPABILITY
5. SEGMENTAL_DUPLICATION

When a candidate conflicts with an already selected window, the next candidate in deterministic order is evaluated.

This rule prevents the 50-window panel from being dominated by duplicate genomic neighborhoods.

---

## 14. Within-Context Overlap

Two selected windows within the same context may not overlap at all.

Any candidate with a non-zero nominal overlap with an already selected window from the same context is rejected.

---

## 15. Benchmark Panel

The final Phase 2 benchmark panel consists of the union of all assessable segments belonging to the 50 selected nominal windows.

The following must be preserved for every selected window:

- window ID
- context ID
- context BED provenance
- chromosome
- nominal start
- nominal end
- nominal length
- assessable segment coordinates
- total assessable bases
- selection hash
- chromosome-selection rank
- overlap metadata with other contexts

---

## 16. Variant-Type Independence

SNV/indel content is not permitted as an interval-selection input.

After benchmarking, the Phase 2 validation gate will test whether the frozen panel contains both SNV and indel evidence.

If one type is absent, this is a scientific outcome of the frozen panel and must not be repaired by outcome-driven interval replacement.

---

## 17. Sample and Technology Independence

The same frozen interval panel must be applied to:

- HG003 Illumina
- HG003 ONT
- HG004 Illumina
- HG004 ONT

No technology-specific or sample-specific replacement windows are permitted.

---

## 18. Deterministic Reproduction

Given identical:

- HG003 benchmark BED,
- HG004 benchmark BED,
- five context BEDs,
- this frozen selection method,

an independent rerun must reproduce:

- candidate IDs,
- selection hashes,
- selected window IDs,
- coordinates,
- context assignments,
- assessable segments,
- final panel checksum.

---

## 19. Required Phase 2B Outputs

Before query VCF download or benchmarking begins, Phase 2B must produce:

1. `shared_callable.bed`
2. `interval_candidates.tsv`
3. `selected_intervals.tsv`
4. `selected_assessable_segments.bed`
5. `interval_selection_summary.json`
6. checksum manifest
7. frozen interval-panel lock

---

## 20. Gate

Phase 2B interval selection is:

### PASS

if:

- all five contexts produce 10 selected windows,
- total selected windows = 50,
- each context spans at least 5 chromosomes,
- no chromosome contributes >2 windows within a context,
- chr20 is absent,
- all windows have >=5,000 assessable bases,
- all selected coordinates derive solely from frozen inputs,
- no benchmark outcome or query VCF is consulted.

### MODIFY

if the frozen truth/context inputs cannot satisfy the declared panel geometry.

### STOP

if deterministic selection cannot be reproduced or if outcome information is required to construct the panel.

---

## 21. Freeze Rule

This document must be hashed before:

- downloading Phase 2 query VCFs,
- inspecting query VCF contents,
- computing Phase 2 benchmark results.

Any scientific change requires a documented protocol amendment and new hash.
