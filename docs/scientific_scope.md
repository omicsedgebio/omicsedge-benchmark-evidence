# Scientific scope

## Scientific question

For a germline small-variant comparison event, what empirical benchmark
observations exist, under which sample, sequencing, calling, truth-set,
benchmark-region, reference, comparator, and software conditions, and what did
each side of the comparison report?

The primary scientific object is an **observation**, not a timeless claim that
a variant is true, false, easy, or difficult. Every decision remains attached
to the experiment and benchmark run that produced it.

## Phase 1A inclusion boundary

Phase 1A includes exactly two regenerated HG002 comparisons:

1. precisionFDA V2 submission `60Z59`, Illumina-only, HG002;
2. precisionFDA V2 submission `RU88N`, ONT-only, HG002;
3. GIAB HG002 GRCh38 v4.2.1 truth VCF;
4. the matching GIAB v4.2.1 benchmark BED;
5. one predeclared bounded GRCh38 interval; and
6. hap.py 0.3.15 using RTG vcfeval 3.12.1.

The resulting records are **new regenerated observations**. They are not the
original 2020 challenge comparisons, whose exact comparator build, invocation,
and truth-input checksums were not retained in the public NIST deposit.

## Selection policy

Submission selection was completed without consulting precision, recall, F1,
rank, FP/FN counts, or any per-submission benchmark result.

- `60Z59` was selected because Phase 0B had already verified its public HG002
  BGZF query artifact, checksum, GRCh38 header, single-technology classification,
  and participant-supplied methods.
- `RU88N` was selected as the corresponding public, single-technology ONT case
  with an unambiguous artifact-to-submission mapping and participant-supplied
  pipeline metadata.

This pair is representative of two input technologies for a pipeline proof. It
is not representative of the best, worst, median, or typical benchmark
performance and must not be described that way.

## In scope

- germline SNVs and small indels represented in the selected VCFs;
- separate truth-side and query-side comparator decisions;
- run-scoped hap.py superloci and source VCF records;
- exact input, transformation, environment, and output provenance;
- explicit assessed, unassessed, ignored, filtered, missing, and unknown states;
- typed Parquet observations and DuckDB event-level retrieval;
- metadata gaps represented as `UNKNOWN`, never inferred; and
- synthetic-only validation fixtures.

## Out of scope

- Project 002/CrossCall in every form;
- changes to or imports from the Phase 0B audit directory;
- raw-read download, alignment, basecalling, or variant calling;
- whole-genome comparison in Phase 1A;
- benchmarking structural variants, somatic variants, RNA variants, or non-HG002 samples;
- score-based submission selection or claims of technology superiority;
- treating the regenerated results as the original precisionFDA result;
- joining events across builds or runs solely by CHROM/POS/REF/ALT;
- publishing a production database, service, website, or remote repository; and
- downloading genomic inputs or executing hap.py/vcfeval during this bootstrap.

## Intended claims and prohibited claims

Phase 1A may demonstrate that public artifacts can be transformed into
queryable, provenance-complete event observations on a bounded interval. It
may not claim whole-genome coverage, clinical validity, caller quality,
technology ranking, universal variant identity, or reproducibility of the
original challenge comparator.

