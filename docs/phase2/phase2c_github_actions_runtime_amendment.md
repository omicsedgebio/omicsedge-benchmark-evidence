# Project 003 Phase 2C — GitHub Actions Runtime Amendment

## Status

FROZEN BEFORE GITHUB ACTIONS PHASE 2C COMPUTE.

This amendment changes only the Phase 2C execution substrate.

The frozen scientific design, source selection, interval panel, truth
definitions, comparator versions, command semantics, evidence model,
identity boundaries, and validation criteria remain unchanged.

## Reason for amendment

The original Phase 2C compute protocol specified a free Google Colab CPU
runtime with rootless udocker execution of the pinned hap.py BioContainer.

During the first execution attempt, Google Colab disconnected the runtime
because the containerization pattern was disallowed on the free tier.

The disconnection occurred before Phase 2 query/truth genomic downloads,
before hap.py/vcfeval benchmarking, and before benchmark outcome inspection.

A prior implementation-only UTF-8 subprocess decoding patch also completed
before any genomic benchmarking.

## Replacement execution substrate

Phase 2C will execute on a GitHub-hosted Linux Actions runner.

The workflow must:

- be manually triggered with `workflow_dispatch`;
- execute on a Linux x86_64 GitHub-hosted runner;
- use Docker available on the hosted runner;
- execute the exact frozen hap.py BioContainer by immutable digest;
- retain hap.py version 0.3.15;
- retain RTG Tools / vcfeval version 3.12.1;
- retain the frozen four Phase 2C benchmark runs;
- retain the frozen Phase 2 assessable-region panel;
- retain the exact frozen query and truth sources;
- retain the frozen 1000 bp retrieval padding;
- retain 2 comparator threads;
- retain fail-closed behavior;
- create only compact result artifacts for retention;
- not retain large genomic source files after the job;
- not perform Phase 2D biological identity expansion;
- not create reliability, trust, confidence, consensus, or technology-ranking
  scores.

## Comparator identity

hap.py version:

`0.3.15`

Frozen BioContainer manifest digest:

`sha256:d63b963a6cb01b4830393b22369e7b91d298e4156dde353739e74e4cfa4f96d0`

RTG Tools / vcfeval version:

`3.12.1`

RTG archive SHA-256:

`ba43cadbb3e79bff74e7d2f8540dd5e201574ec8e293ba555f3aeefd1375dfc5`

Comparison engine:

`vcfeval`

Threads:

`2`

## Frozen scientific inputs

The following remain authoritative and unchanged:

- `docs/phase2/phase2c_compute_protocol.md`
- `docs/phase2/phase2c_compute_protocol.lock`
- `data/phase2/admitted_sources.tsv`
- `data/phase2/selected_intervals.tsv`
- `data/phase2/selected_assessable_segments.bed`
- `data/phase2/interval_panel.lock`
- `environment/comparator-lock.yaml`
- `schemas/phase2/benchmark_run.schema.json`

Frozen assessable panel:

- 50 windows
- 541 assessable segments
- 1,162,571 assessable bases
- 19 chromosomes
- chr20 excluded

## Runtime provenance

The GitHub Actions execution must record at minimum:

- repository commit SHA;
- workflow run ID and attempt;
- runner OS and architecture;
- CPU count;
- available memory;
- free disk before large downloads;
- Docker version;
- hap.py container manifest digest;
- hap.py runtime identity;
- RTG version;
- Java version;
- bcftools version;
- samtools version;
- bedtools version;
- command argv;
- timestamps;
- exit status;
- wall time.

## Disk policy

The workflow must measure available temporary disk before downloading genomic
inputs.

The implementation must fail closed if its audited minimum free-disk
requirement is not satisfied.

No scientific interval, source, truth, comparator, or outcome definition may
be changed merely to fit the hosted runner.

## Cost policy

The workflow is intended to use only included GitHub Actions capacity.

The account Actions budget is configured to stop paid usage at the budget
limit.

No paid compute is required by this amendment.

## Outcome isolation

The GitHub Actions workflow and runner implementation must be committed and
audited before the first benchmark execution.

No benchmark result may be inspected before that implementation freeze.

Phase 2C remains limited to run-scoped benchmark evidence.

Cross-run biological identity remains Phase 2D work.

## Relationship to original protocol

This amendment supersedes only the runtime-specific statements requiring
Google Colab and udocker.

All scientific requirements of the frozen Phase 2C compute protocol remain
in force.
