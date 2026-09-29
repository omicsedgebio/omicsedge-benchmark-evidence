# Project 003 Phase 2C — GitHub Actions Compute Run 2 Runtime Patch

## Status

RUNTIME-ONLY PATCH FROZEN AFTER RUN 2 AND BEFORE COMPUTE RERUN.

## Run 2

- GitHub Actions run ID: `36633924088`
- Repository commit:
  `141d1689ea441931f3dd5286579c7e5e783f31d1`
- Result: `PHASE2C_COMPUTE_FAIL`
- Failure location: post-comparator annotated-output validation
- Exception: `ModuleNotFoundError: No module named 'pysam'`

Run 2 successfully passed the frozen runtime/resource gates, retrieved the
frozen Phase 2 genomic inputs, and executed all four frozen hap.py benchmark
comparisons:

- phase2-hg003-60z59
- phase2-hg003-ru88n
- phase2-hg004-60z59
- phase2-hg004-ru88n

The failure occurred when the host Python process entered
`verify_annotated_outputs()` and attempted to import `pysam`.

No Phase 2C registry EVENT or OBSERVATION materialization was completed and
Phase 2D biological identity expansion was not performed.

## Scientific boundary

Run 2 crossed the genomic-compute boundary. Therefore no source-selection,
interval-panel, truth-set, comparator, comparison-parameter, EVENT,
OBSERVATION, or identity rule is changed by this patch.

The patch changes only Python dependency visibility in the GitHub Actions
runtime.

## Patch

Pinned Python dependencies remain unchanged:

- duckdb 1.5.6
- pyarrow 25.0.1
- pysam 0.23.3
- jsonschema 4.26.0
- PyYAML 6.0.3

They are now installed into an explicit ephemeral `python-site` directory.
That directory is inserted into the running interpreter's `sys.path`.

The runner also imports all five dependencies immediately after installation.
This creates a fail-closed dependency gate before genomic retrieval on the
next execution.

Original runner SHA-256:

`24011ab7187c57c020fb614e5570fddf0e80a734cf1332f8a0891abc500be071`

Patched runner SHA-256:

`3044ecb28d18a0fe8876fea43ee59ed8f8d8b86b75ee694f8ffd3d1400ad7f09`

The frozen scientific protocol, Phase 2 interval panel, source admission,
hap.py 0.3.15 OCI digest, RTG 3.12.1 comparator, and Phase 2C evidence
semantics are unchanged.
