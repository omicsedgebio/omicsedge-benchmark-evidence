# Project 003 — Phase 2C Compute Protocol

## Status

FROZEN BEFORE PHASE 2 QUERY VCF RETRIEVAL AND BENCHMARK OUTCOME INSPECTION

## Purpose

Phase 2C executes the frozen Phase 2 benchmark panel for four admitted
experiment conditions:

- HG003 Illumina
- HG003 Oxford Nanopore
- HG004 Illumina
- HG004 Oxford Nanopore

Heavy genomic inputs and comparator workspaces are temporary and run in
Google Colab.

The Mac and Git repository retain only compact provenance, manifests,
validated evidence, and release artifacts.

---

## 1. Frozen upstream authorities

Phase 2 protocol:

`docs/phase2/phase2_protocol.md`

SHA-256:

`6234485e8916fd30a335c761a62668b617cb148b5b5a1753d12fd7765fa1633f`

Admitted Phase 2 sources:

`data/phase2/admitted_sources.tsv`

SHA-256:

`55ebf63901ac0c118cb5ec687b49cc81cf680bb9357246ba2f6138b27a29641f`

Frozen Phase 2 interval panel:

`data/phase2/selected_assessable_segments.bed`

SHA-256:

`4c77e17c3dec47051cb9b29fa14fee67f31a559785417d083f4f7bcacb05cd26`

Selected interval metadata:

`data/phase2/selected_intervals.tsv`

SHA-256:

`2e5a6a97c9bacf5fdf3cf547ac7db32d06f611a1f2bcca66cbcfbd04e722c01c`

Interval panel lock:

`data/phase2/interval_panel.lock`

Panel geometry:

- 50 nominal windows
- 10 windows per context
- 541 assessable BED segments
- 1,162,571 assessable bases
- 19 represented chromosomes
- chr20 excluded

No query VCF contents or benchmark outcomes were consulted during panel
construction.

---

## 2. Admitted query VCFs

Exactly four query artifacts are admitted.

### HG003 Illumina

Submission:

`60Z59`

URL:

`https://data.nist.gov/od/ds/ark:/88434/mds2-2336/submission_vcfs/60Z59/60Z59_HG003.vcf.gz`

Expected SHA-256:

`c4384b734ae7f54ceedc3c5e5b52ef4b4805cba8dcc70079a5dcf412010ab44a`

### HG003 Oxford Nanopore

Submission:

`RU88N`

URL:

`https://data.nist.gov/od/ds/ark:/88434/mds2-2336/submission_vcfs/RU88N/RU88N_HG003.vcf.gz`

Expected SHA-256:

`84ac5c526a92548fa6f1ce46108674c29d32ea754f863c9e90fbca41a44edc20`

### HG004 Illumina

Submission:

`60Z59`

URL:

`https://data.nist.gov/od/ds/ark:/88434/mds2-2336/submission_vcfs/60Z59/60Z59_HG004.vcf.gz`

Expected SHA-256:

`b4184c164ef2cef60b50fa9db579c2548efa5d4301d105a49f8d7803114e1eff`

### HG004 Oxford Nanopore

Submission:

`RU88N`

URL:

`https://data.nist.gov/od/ds/ark:/88434/mds2-2336/submission_vcfs/RU88N/RU88N_HG004.vcf.gz`

Expected SHA-256:

`ec0e481dde0486d30c9f85c9323c1bf75008e2bad2ba50e2ac44e7e15277dabd`

Every whole query artifact must be downloaded and its SHA-256 verified
before it may be indexed, sliced, normalized, or benchmarked.

The original downloaded bytes are immutable.

---

## 3. GIAB truth

Truth release:

`GIAB v4.2.1`

Assembly:

`GRCh38`

### HG003 truth VCF

`https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG003_NA24149_father/NISTv4.2.1/GRCh38/HG003_GRCh38_1_22_v4.2.1_benchmark.vcf.gz`

Truth index:

same URL plus `.tbi`

Benchmark BED:

`https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG003_NA24149_father/NISTv4.2.1/GRCh38/HG003_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed`

### HG004 truth VCF

`https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG004_NA24143_mother/NISTv4.2.1/GRCh38/HG004_GRCh38_1_22_v4.2.1_benchmark.vcf.gz`

Truth index:

same URL plus `.tbi`

Benchmark BED:

`https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/AshkenazimTrio/HG004_NA24143_mother/NISTv4.2.1/GRCh38/HG004_GRCh38_1_22_v4.2.1_benchmark_noinconsistent.bed`

Every retrieved truth artifact receives a locally computed SHA-256.

Previously frozen benchmark-BED hashes must reproduce exactly:

HG003:

`652afd3046705af3200f9c87c255fef11bb212dd76c75a19999c9b2df8a3180c`

HG004:

`88d1c926fdc8abd9c39b3e9fe2af3fc43dd67d284690a3dc6127b369d96bccad`

A mismatch is a hard stop.

---

## 4. Reference

Reference:

`GCA_000001405.15_GRCh38_no_alt_analysis_set.fasta.gz`

URL:

`https://ftp-trace.ncbi.nlm.nih.gov/ReferenceSamples/giab/release/references/GRCh38/GCA_000001405.15_GRCh38_no_alt_analysis_set.fasta.gz`

Publisher MD5:

`3a3347eae0893f96ecf495d1c39e2284`

FAI MD5:

`5fddbc109c82980f9436aa5c21a57c61`

GZI MD5:

`cfa1ee11b1ecb29f936578b27014fbe0`

The reference is downloaded only inside the ephemeral Colab runtime.

Its MD5 and locally computed SHA-256 must be recorded before comparison.

---

## 5. Comparator identity

Software identity remains inherited from:

`environment/comparator-lock.yaml`

hap.py:

`0.3.15`

BioContainer manifest:

`sha256:d63b963a6cb01b4830393b22369e7b91d298e4156dde353739e74e4cfa4f96d0`

RTG Tools / vcfeval:

`3.12.1`

RTG archive SHA-256:

`ba43cadbb3e79bff74e7d2f8540dd5e201574ec8e293ba555f3aeefd1375dfc5`

Comparison engine:

`vcfeval`

Annotated comparator output:

enabled with `-V`

Threads:

`2`

---

## 6. Explicit Phase 1 → Phase 2 comparator adaptation

The following fields in `environment/comparator-lock.yaml` are
Phase-1-specific and MUST NOT be used for Phase 2C:

- `comparison.core_interval`
- `comparison.padded_interval`

Those fields describe the historical HG002 chr20 Phase 1A experiment.

Phase 2C replaces those coordinates with:

`data/phase2/selected_assessable_segments.bed`

No Phase 1 chr20 interval is permitted in Phase 2C execution.

---

## 7. Retrieval padding

Input retrieval uses:

`1,000 bp`

of genomic padding around each assessable segment.

Padding does not enlarge the benchmark panel or exported evidence.

The exact frozen panel remains the hap.py `-f` benchmark-region input.

Boundary-only records may be retained as diagnostics but must not become
core registry evidence.

---

## 8. Query preparation

For each query VCF:

1. download the whole artifact,
2. verify frozen SHA-256,
3. retain original bytes unchanged,
4. validate BGZF/VCF readability,
5. create derived index if possible,
6. derive a padded-panel query slice,
7. record checksums and transformation commands.

Original query files must never be overwritten.

---

## 9. Truth preparation

For HG003 and HG004:

1. retrieve truth VCF,
2. retrieve TBI,
3. retrieve benchmark BED,
4. verify frozen benchmark-BED SHA-256,
5. compute SHA-256 for truth VCF and TBI,
6. derive padded-panel truth slice,
7. retain transformation commands and hashes.

The same truth source is shared by Illumina and ONT for each sample.

---

## 10. Reference preparation

The exact GRCh38 no-alt reference is used.

Tool-specific structures including an RTG SDF are derived artifacts.

Hashes and derivation commands must be captured.

Reference sequence identity must not change.

---

## 11. Benchmark runs

Exactly four Phase 2C comparator runs are executed:

- HG003 / 60Z59 / Illumina
- HG003 / RU88N / ONT
- HG004 / 60Z59 / Illumina
- HG004 / RU88N / ONT

Each run uses the corresponding query, corresponding sample truth,
same GRCh38 reference, same frozen panel, hap.py 0.3.15,
RTG vcfeval 3.12.1, and two threads.

No quality threshold, caller-specific threshold, technology-specific filter,
or post-hoc region replacement may be introduced.

---

## 12. Comparator command semantics

Semantic command contract:

    hap.py TRUTH_SLICE QUERY_SLICE
      -f FROZEN_PHASE2_PANEL_BED
      -r GRCH38_REFERENCE
      -o RUN_OUTPUT_PREFIX
      -V
      --engine=vcfeval
      --engine-vcfeval-path=/opt/rtg-tools-3.12.1/rtg
      --engine-vcfeval-template GRCH38_RTG_SDF
      --threads=2

Path names are runtime-local.

Scientific arguments are frozen.

---

## 13. Runtime

Phase 2C runs in a fresh Google Colab CPU runtime.

Minimum preflight:

- Linux amd64 / x86_64
- >= 2 logical CPUs
- >= 7 GiB RAM
- >= 15 GiB free temporary disk

Large genomic files remain in ephemeral `/content`.

The pinned rootless runner from the prior proof remains:

`udocker==1.3.17`

---

## 14. Runtime identity capture

Capture:

- architecture
- CPU count
- RAM
- free disk
- Python
- hap.py identity evidence
- container digest
- RTG
- Java
- bcftools
- samtools
- udocker
- command argv
- timestamps
- stdout
- stderr
- exit status
- wall time
- output hashes

---

## 15. Outcome isolation

Before comparison, only structural/provenance information may be inspected.

Do not inspect or summarize:

- TP
- FP
- FN
- precision
- recall
- F1
- technology agreement
- outcome distributions

until all four sources and comparator configuration pass preflight.

No source or region may be replaced because of performance.

---

## 16. Evidence export

Phase 2C preserves:

- experiment
- benchmark run
- event
- truth observation
- query observation
- source artifacts
- provenance links

Events remain run-scoped.

Cross-run biological identity is deferred to Phase 2D.

---

## 17. Required compact Colab outputs

Return only compact reproducibility and evidence artifacts:

- runtime identity
- retrieval manifest
- source/derived checksums
- command log
- run manifest
- benchmark runs
- experiments
- required annotated comparator output
- events
- observations
- provenance links
- validation report
- stdout/stderr
- package checksum manifest

Do not return large query VCFs, truth VCFs, reference FASTA,
container layers, RTG SDF, or temporary workspaces.

---

## 18. Fail-closed conditions

Stop before scientific interpretation on:

- query SHA-256 mismatch
- benchmark BED SHA-256 mismatch
- reference MD5 mismatch
- comparator identity mismatch
- RTG archive SHA-256 mismatch
- frozen panel SHA-256 mismatch
- missing run
- comparator non-zero exit
- incomplete provenance
- outcome-driven source replacement
- accidental Phase 1 chr20 usage

---

## 19. Compute/storage policy

Large files exist only in Colab.

Target paid compute:

`CAD $0`

No large raw Phase 2 genomic input is required on the development Mac.

---

## 20. Freeze rule

This protocol must be hashed and committed before:

- Phase 2 query VCF retrieval
- Phase 2 benchmark execution
- Phase 2 outcome inspection

Any scientific change after outcome exposure requires a documented amendment
and a new hash.
