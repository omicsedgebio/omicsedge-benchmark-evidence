# Project 003 Phase 2C — GitHub Actions Compute Run 3 Runtime Patch

## Status

RUNTIME/EXPORT-ONLY PATCH FROZEN AFTER RUN 3 AND BEFORE COMPUTE RERUN.

## Run 3

- GitHub Actions run ID: `36637029707`
- Repository commit:
  `58022f64ec6dd5b15a0637e0f3cf199409fc96fc`
- Result: `PHASE2C_COMPUTE_FAIL`
- Failure stage: `Phase 2C DuckDB evidence query`
- Exception: `ModuleNotFoundError: No module named 'numpy'`

Run 3 successfully completed:

- frozen genomic-source retrieval and verification;
- all four frozen hap.py comparisons;
- annotated-output validation;
- EVENT and OBSERVATION construction;
- EXPERIMENT and BENCHMARK_RUN construction;
- JSON-schema validation;
- TSV and Parquet materialization.

Materialized Run-3 entity counts:

- EVENT: 7,951
- OBSERVATION: 15,902
- EXPERIMENT: 4
- BENCHMARK_RUN: 4
- SOURCE_ARTIFACT: 73
- PROVENANCE_LINK: 23,961

Phase 2C final validation and final successful release packaging were not
completed. Phase 2D biological identity expansion was not performed.

## Failure

The example DuckDB query used `fetchdf()`, which requests a Pandas-style
DataFrame and therefore introduced an unnecessary NumPy/Pandas runtime
dependency.

The SQL query itself executed at the evidence-query stage; the failure was
in result materialization to a DataFrame.

## Patch

The SQL query, selected columns, joins, ordering, event identifier, and
evidence semantics are unchanged.

Only result materialization changes:

- DuckDB `fetchdf()` is replaced by native `fetchall()`;
- column names are obtained from the DuckDB cursor description;
- the same tab-separated example-query artifact is written with Python's
  standard-library `csv.writer`.

No NumPy or Pandas dependency is introduced.

No source selection, truth set, interval panel, comparator, benchmark
parameter, EVENT rule, OBSERVATION rule, schema, or biological-identity
rule is changed.

Original runner SHA-256:

`3044ecb28d18a0fe8876fea43ee59ed8f8d8b86b75ee694f8ffd3d1400ad7f09`

Patched runner SHA-256:

`523db63bee4a4b7337ea9a2f629af596cd3d3399f7c124817d9e0019fde54f78`
