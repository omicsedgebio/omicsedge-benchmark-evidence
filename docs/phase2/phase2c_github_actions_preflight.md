# Project 003 Phase 2C — GitHub Actions Runtime Preflight

## Status

PASS BEFORE PHASE 2C BENCHMARK COMPUTE.

No Phase 2 genomic query/truth source was downloaded and no benchmark
outcome was inspected during this preflight.

## GitHub Actions execution

- Repository commit:
  `450e4b79ef2bbcf5670138f93267f506a41a844d`
- Workflow run ID:
  `36623331671`
- Workflow attempt:
  `1`
- Runner OS:
  `Linux`
- Runner architecture:
  `X64 / x86_64`
- Logical CPUs:
  `2`

## Memory

- Total RAM:
  `8,323,969,024 bytes`
- Available RAM during resource capture:
  `7,395,024,896 bytes`
- Swap:
  `3,221,221,376 bytes`

## Disk

Before cleanup:

`14,318,231,552 bytes free`

After removal of unrelated preinstalled runner software:

`39,831,887,872 bytes free`

Authoritative free-disk value at the frozen resource gate:

`39,831,830,528 bytes`

Frozen minimum:

`16,106,127,360 bytes (15 GiB)`

Result:

`PASS frozen >=15 GiB free-disk gate`

After frozen hap.py and RTG comparator materialization:

`38,794,772,480 bytes free`

## Comparator environment

Docker:

`28.0.4`

Frozen hap.py BioContainer:

`quay.io/biocontainers/hap.py@sha256:d63b963a6cb01b4830393b22369e7b91d298e4156dde353739e74e4cfa4f96d0`

Comparator result:

`PASS frozen hap.py OCI comparator executes`

Frozen RTG Tools:

`3.12.1`

RTG archive SHA-256:

`ba43cadbb3e79bff74e7d2f8540dd5e201574ec8e293ba555f3aeefd1375dfc5`

Comparator result:

`PASS frozen RTG 3.12.1 executes`

Final workflow marker:

`PHASE2C_GITHUB_ACTIONS_PREFLIGHT_PASS`

## Scientific boundary

This run tested only the execution environment.

It did not:

- retrieve the four Phase 2 query VCFs;
- retrieve HG003/HG004 benchmark truth VCFs;
- execute the four hap.py comparisons;
- inspect benchmark outcomes;
- create Phase 2C EVENT or OBSERVATION records;
- perform Phase 2D biological identity expansion;
- create reliability, trust, confidence, consensus, or technology-ranking
  scores.

The frozen Phase 2C scientific protocol and GitHub Actions runtime amendment
remain authoritative.
