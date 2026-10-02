<div align="center">

<img src="assets/omicsedge-logo.svg" width="620" alt="OmicsEdgeBio Benchmark Evidence Registry">

<br>

# OmicsEdge Benchmark Evidence Registry

### Traceable benchmark evidence across sequencing technologies, callers, samples, genomic contexts, and comparator versions.

**Project 003 · OmicsEdgeBio**

**[OmicsEdge Evidence Atlas](https://omicsedge.bio/evidence-atlas) · [Live Evidence Explorer](https://omicsedge.bio/explorer) · [DOI / Citation](https://doi.org/10.5281/zenodo.23085673)**

<br>

[![Evidence Atlas v1.0.0](https://img.shields.io/badge/Evidence_Atlas_v1.0.0-RELEASED-brightgreen)](#release-status)
[![Expansion M0](https://img.shields.io/badge/Expansion_M0-FROZEN-blue)](#evidence-atlas-expansion-in-development)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23085673.svg)](https://doi.org/10.5281/zenodo.23085673)
[![Phase 1A](https://img.shields.io/badge/Phase_1A-PASS-brightgreen)](#phase-1a--empirical-proof-of-concept)
[![Phase 1B](https://img.shields.io/badge/Phase_1B-15%2F15_PASS-brightgreen)](#phase-1b--biological-variant-identity)
[![Phase 2](https://img.shields.io/badge/Phase_2-20%2F20_PASS-brightgreen)](#phase-2--generalization)
[![Assembly](https://img.shields.io/badge/assembly-GRCh38-lightgrey)](#)
[![Truth](https://img.shields.io/badge/GIAB-v4.2.1-lightgrey)](#)

</div>

The **[OmicsEdge Evidence Atlas](https://omicsedge.bio/evidence-atlas)** is the public-facing research resource and tool. The **OmicsEdge Benchmark Evidence Registry** is the formal released and citable scientific resource underlying Evidence Atlas v1.0.0.

---

## Release status

| Status | Scope |
|---|---|
| ✅ **RELEASED** | **Evidence Atlas v1.0.0** (Project 003): human (GRCh38), HG002 · HG003 · HG004, Illumina · Oxford Nanopore, germline small-variant benchmark evidence. Frozen and checksummed. DOI [`10.5281/zenodo.23085673`](https://doi.org/10.5281/zenodo.23085673). |
| 🔒 **FROZEN DEVELOPMENT MILESTONE** | **M0 — Evidence Atlas Expansion Protocol** (approved 2026-10-01). Defines the architecture and scientific rules for cross-species / cross-platform expansion. **Rules only: no data, no model, no new evidence.** Locked by [`docs/atlas/m0_expansion_protocol.lock`](docs/atlas/m0_expansion_protocol.lock). |
| 🧪 **IN REVIEW** | **M1A — bounded Automated Public Data Catalog implementation.** Canonical pilot pending manual GitHub Actions run; metadata only, not evidence or a release. |

No expansion record has been admitted as evidence or released. The repository
contains the M1A implementation and offline fixtures only; canonical pilot
outputs must be produced off-Mac by the manual GitHub Actions workflow. See
[Evidence Atlas expansion](#evidence-atlas-expansion-in-development).

---

## What is this?

Most variant benchmarks answer a narrow question:

> **How well did this callset perform?**

The OmicsEdge Benchmark Evidence Registry asks a different question:

> **What empirical evidence exists for this biological variant across experiments, technologies, benchmark runs, genomic contexts, truth versions, and comparator versions - and exactly where did that evidence come from?**

The registry preserves the benchmark evidence itself rather than collapsing it immediately into a single score.

It is designed to make statements such as:

- this biological variant appeared in multiple independent benchmark runs,
- this Illumina observation was classified differently from an Oxford Nanopore observation,
- both observations originated from specific public submissions,
- the comparison used a particular GIAB truth release,
- the comparator implementation and version are known,
- the genomic context is traceable,
- and no unsupported consensus has been invented.

---

# Project dashboard

| Metric | Current state |
|---|---:|
| Project | **OmicsEdgeBio Project 003** |
| Phase 1A | ✅ PASS |
| Phase 1B | ✅ **15 / 15 gates PASS** |
| Phase 2 | ✅ **20 / 20 gates PASS** |
| Phase 2 release | ✅ Frozen and independently verified |
| Samples represented after Phase 2 | **HG002 · HG003 · HG004** |
| Sequencing technologies | **Illumina · Oxford Nanopore** |
| Phase 1 benchmark runs | **2** |
| Phase 1 events | **3,602** |
| Phase 1 observations | **7,204** |
| Phase 1 provenance links | **10,871** |
| Phase 1 biological variants | **1,666** |
| Phase 1 EVENT -> VARIANT links | **3,332** |
| Phase 2C benchmark events | **7,951** |
| Phase 2C observations | **15,902** |
| Phase 2D exact EVENT -> VARIANT links | **7,891** |
| Phase 2D unresolved events | **60** |
| Phase 2D biological variants touched | **2,612** |
| Phase 2 genomic contexts | **5** |
| Frozen Phase 2 windows | **50** |
| Phase 2 chromosomes represented | **19** |
| Phase 2 assessable bases | **1,162,571 bp** |
| Phase 2 query outcomes used during panel selection | **0** |
| Reliability / trust score | **Not generated** |
| Forced technology consensus | **Not generated** |

---

# Evidence Explorer

The Evidence Explorer is the live browser interface for inspecting the released Evidence Atlas v1.0.0.

It exposes run-scoped observations, genomic context, and provenance without collapsing the evidence into a single trust score.

**[Open the live Evidence Explorer →](https://omicsedge.bio/explorer)**

<p align="center">
  <img src="assets/evidence-explorer-preview.svg"
       width="100%"
       alt="OmicsEdge Evidence Explorer interface">
</p>

<p align="center">
  <sub>
    The live Evidence Explorer presents run-scoped observations, genomic context,
    and provenance while preserving the released evidence model.
  </sub>
</p>

---
---

# The core idea

```mermaid
flowchart LR

    A["Public sequencing experiment"] --> B["Benchmark run"]

    T["Truth VCF + benchmark regions"] --> B
    C["Comparator + version"] --> B

    B --> E["Run-scoped EVENT"]

    E --> O1["Truth-side OBSERVATION"]
    E --> O2["Query-side OBSERVATION"]

    E --> L["EVENT_VARIANT_LINK"]

    L --> V["Biological VARIANT"]

    SA["SOURCE_ARTIFACT"] --> P["PROVENANCE_LINK"]
    P --> B
    P --> E
    P --> O1
    P --> O2
    P --> V
```

The important separation is:

```text
VARIANT <- EVENT_VARIANT_LINK <- EVENT -> OBSERVATION
```

A biological variant can therefore accumulate evidence from multiple benchmark runs **without pretending that those benchmark events are identical**.

---

# Why this separation matters

A conventional benchmark may produce:

```text
Variant → PASS / FAIL
```

The evidence registry instead preserves:

```mermaid
flowchart TD

    V["Biological variant"]

    V --> R1["HG002 · Illumina · Run A"]
    V --> R2["HG002 · ONT · Run B"]
    V --> R3["HG003 · Illumina · Run C"]
    V --> R4["HG003 · ONT · Run D"]

    R1 --> E1["benchmark event"]
    R2 --> E2["benchmark event"]
    R3 --> E3["benchmark event"]
    R4 --> E4["benchmark event"]

    E1 --> O1["observations + provenance"]
    E2 --> O2["observations + provenance"]
    E3 --> O3["observations + provenance"]
    E4 --> O4["observations + provenance"]
```

These observations can coexist even when technologies or benchmark runs disagree.

The registry does **not** automatically turn them into:

```text
70% trustworthy
```

or:

```text
Illumina wins
```

or:

```text
Consensus = PASS
```

Those conclusions require separate scientific methods.

---

# Evidence Explorer interface

The live public interface behaves as an **evidence explorer**.

A user searches for a variant:

```text
chr7:140453136 A>T
```

and receives something conceptually like:

```text
┌──────────────────────────────────────────────────────────────┐
│ VARIANT                                                      │
│ GRCh38 · chr7:140453136 · A>T                               │
├──────────────────────────────────────────────────────────────┤
│ Evidence                                                     │
│                                                              │
│ HG002                                                        │
│   Illumina       ● TP     GIAB v4.2.1   hap.py 0.3.15       │
│   ONT            ● TP     GIAB v4.2.1   hap.py 0.3.15       │
│                                                              │
│ HG003                                                        │
│   Illumina       ● ...                                       │
│   ONT            ● ...                                       │
│                                                              │
│ HG004                                                        │
│   Illumina       ● ...                                       │
│   ONT            ● ...                                       │
├──────────────────────────────────────────────────────────────┤
│ Context                                                      │
│ tandem repeat · low mappability · callable                  │
├──────────────────────────────────────────────────────────────┤
│ Provenance                                                   │
│ submission → artifact → benchmark run → event → observation │
└──────────────────────────────────────────────────────────────┘
```

The Evidence Explorer makes each layer inspectable rather than hiding provenance behind a single summary number.

---

# Evidence journey

```mermaid
sequenceDiagram

    participant S as Public source
    participant R as Registry pipeline
    participant B as Benchmark comparator
    participant E as Evidence registry
    participant U as Explorer user

    S->>R: Query VCF + truth + metadata
    R->>R: Verify hashes and provenance
    R->>B: Execute frozen benchmark
    B->>R: Annotated benchmark output
    R->>E: EVENT + OBSERVATION records
    R->>E: SOURCE_ARTIFACT + PROVENANCE_LINK
    R->>E: Biological VARIANT links
    U->>E: Query biological variant
    E-->>U: Run-scoped evidence + provenance
```

---

# Phase 1A - empirical proof of concept

**Status: PASS**

Phase 1A established that public benchmark output could be transformed into a provenance-preserving evidence registry.

The experiment used two public precisionFDA Truth Challenge V2 HG002 submissions:

| Dimension | Illumina | Oxford Nanopore |
|---|---|---|
| Sample | HG002 | HG002 |
| Submission | `60Z59` | `RU88N` |
| Platform | NovaSeq 6000 | PromethION R9.4 |
| Pipeline | RN-Illumina | PEPPER-DeepVariant |
| Assembly | GRCh38 | GRCh38 |
| Truth | GIAB v4.2.1 | GIAB v4.2.1 |
| Comparator | hap.py 0.3.15 | hap.py 0.3.15 |
| Matching engine | RTG vcfeval 3.12.1 | RTG vcfeval 3.12.1 |

Phase 1A produced:

```text
2 experiments
2 benchmark runs
3,602 run-scoped events
7,204 observations
10,871 provenance links
1,666 cross-run identity candidates
```

The original evidence remains run-scoped and immutable.

---

# Phase 1B - biological variant identity

**Status: PASS - 15 / 15 validation gates**

Phase 1B introduced a distinct biological `VARIANT` entity.

```mermaid
erDiagram

    VARIANT ||--o{ EVENT_VARIANT_LINK : identifies
    EVENT ||--o{ EVENT_VARIANT_LINK : maps_to
    EVENT ||--o{ OBSERVATION : contains
    BENCHMARK_RUN ||--o{ EVENT : produces
    EXPERIMENT ||--o{ BENCHMARK_RUN : participates_in
    SOURCE_ARTIFACT ||--o{ PROVENANCE_LINK : supports
```

The frozen Phase 1 evidence produced:

```text
1,666 biological VARIANT entities
3,332 EVENT_VARIANT_LINK entities
1,666 cross-run relationships
```

All 1,666 Phase 1 candidates satisfied exact normalized allele identity under the frozen v1 method.

The identity decision uses:

```text
assembly
contig
normalized start
normalized end
REF
ALT
```

Deterministic IDs are content-derived using SHA-256.

### Representation equivalence

Representation equivalence is deliberately **not inferred**.

For example:

```text
left-aligned representation
vs.
alternate representation of the same local haplotype
```

is not automatically treated as biological identity.

Until a separately specified and validated representation-equivalence method exists, such relationships remain:

```text
UNRESOLVED
```

---

# Phase 2 - generalization

**Status: PASS - 20 / 20 final validation gates**

Phase 2 tested whether the evidence model generalizes beyond a single HG002 chr20 proof of concept.

The final Phase 2 release passed all **20 / 20 frozen validation criteria**.

Final Phase 2 evidence includes:

```text
3 benchmark samples: HG002, HG003, HG004
2 sequencing technologies: Illumina and Oxford Nanopore
5 genomic contexts
19 chromosomes
7,951 Phase 2C run-scoped EVENT records
15,902 Phase 2C OBSERVATION records
7,891 exact EVENT_VARIANT_LINK records
60 UNRESOLVED EVENT records
2,612 Phase 2D biological VARIANT identities touched
```

The final release was checksum-manifested, independently extracted, and independently verified.

Frozen Phase 2 sources:

```text
HG003 · Illumina
HG003 · Oxford Nanopore

HG004 · Illumina
HG004 · Oxford Nanopore
```

All source selection occurred **before benchmark performance inspection**.

---

## Genomic context panel

The Phase 2 panel uses official GIAB genome-stratifications v3.6.

```mermaid
mindmap
  root((Phase 2 genomic contexts))
    Non-difficult
      GIAB difficult-region complement
    Homopolymer
      long perfect / imperfect runs
    Tandem repeat
      repeat-associated complexity
    Low mappability
      mapping ambiguity
    Segmental duplication
      duplicated genomic sequence
```

Exactly five context definitions were frozen:

| Context | GIAB v3.6 stratification |
|---|---|
| Non-difficult | `GRCh38_notinalldifficultregions.bed.gz` |
| Homopolymer | `GRCh38_AllHomopolymers_ge7bp_imperfectge11bp_slop5.bed.gz` |
| Tandem repeat | `GRCh38_AllTandemRepeats.bed.gz` |
| Low mappability | `GRCh38_lowmappabilityall.bed.gz` |
| Segmental duplication | `GRCh38_segdups.bed.gz` |

---

## Frozen Phase 2 interval panel

The panel was selected using genomic coordinates and frozen GIAB regions only.

No query VCF content or benchmark outcome was consulted.

```text
50 windows
10 windows / context
19 chromosomes represented
chr20 excluded
1,162,571 assessable bp
```

The chromosome used for the original Phase 1 proof of concept - `chr20` - was deliberately excluded.

```mermaid
flowchart LR

    A["HG003 GIAB callable"] --> I["Intersection"]
    B["HG004 GIAB callable"] --> I

    I --> C["Shared callable universe"]

    C --> D["GIAB context anchors"]

    D --> E["Deterministic SHA-256 ordering"]

    E --> F["10 windows / context"]

    F --> G["50-window frozen panel"]

    G --> H["Phase 2C benchmark"]
```

Selection constraints included:

```text
25 kb nominal windows
>= 5 kb assessable sequence
>= 5 chromosomes / context
<= 2 windows / chromosome / context
no within-context overlap
< 50% overlap across contexts
chr20 excluded
```

---

# Provenance model

Every piece of evidence should be traceable back through the chain that generated it.

```mermaid
flowchart RL

    O["Observation"]

    O --> E["Event"]
    E --> R["Benchmark run"]
    R --> X["Experiment"]

    O --> P["Provenance links"]
    E --> P
    R --> P

    P --> Q["Query VCF"]
    P --> T["Truth VCF"]
    P --> B["Benchmark BED"]
    P --> G["Reference genome"]
    P --> C["Comparator runtime"]
```

This allows a user to distinguish:

```text
same biological variant
```

from:

```text
same benchmark event
```

from:

```text
same comparator decision
```

from:

```text
same technology behavior
```

They are not assumed to be equivalent.

---

# What the registry intentionally does not do

The current scientific model does **not** generate:

| Not generated | Reason |
|---|---|
| Global trust score | Requires a separately validated model |
| Reliability score | Evidence preservation precedes scoring |
| Technology ranking | Benchmark context is conditional |
| Forced consensus | Discordant evidence remains observable |
| Caller ranking | Not a caller leaderboard |
| Representation equivalence | Requires separate validation |
| Clinical interpretation | Outside current scientific scope |

The registry is an **evidence layer**, not a decision engine.

---

# Evidence Atlas expansion (in development)

> **Status: IN DEVELOPMENT. Nothing in this section is released.**
> Evidence Atlas v1.0.0 above is the only released resource. It is frozen.
> M0, the expansion protocol, is frozen and approved. It defines
> **architecture and scientific rules only**.

### What M0 is and is not

M0 fixes, in advance, how future data will be discovered, described, judged
and released. M0 itself does **not** mean any of the following:

- multispecies evidence has been released. It has not; v1.0.0 is human-only.
- PacBio or other additional technologies are part of Atlas v1. They are not;
  v1.0.0 covers Illumina and Oxford Nanopore only.
- public sequencing runs had been ingested by M0. None were; M1A now contains
  catalog code and offline fixtures, not canonical live outputs, sequencing
  payloads or evidence.
- an ML model has been trained. None has, and no ML threshold is active.
- automated evidence admission is running. It is not.
- M1 is complete. It is not; only the bounded M1A implementation/pilot is
  awaiting review, and M1B has not started.

## Goal

The aim is to grow the Atlas into a **species-agnostic** and
**sequencing-technology-agnostic** evidence system. It should discover public
sequencing datasets broadly, but admit only scientifically defensible
datasets into versioned releases. Intended future coverage includes, where
defensible, *Homo sapiens*, *Mus musculus*, *Saccharomyces cerevisiae*,
*Danio rerio* and other species. On the technology side it includes Illumina
short-read, Oxford Nanopore, PacBio HiFi, and further technologies where
metadata and evidence support them.

## Catalogued is not evidence

The expansion separates three layers:

```text
1. PUBLIC DATA CATALOG      broad metadata discovery: NOT evidence
2. EVIDENCE CANDIDATE       passes every hard eligibility criterion: NOT yet validated
3. VALIDATED RELEASE        passes frozen validation gates, frozen in an immutable manifest
```

> **catalogued metadata ≠ evidence candidate ≠ validated/released Evidence Atlas evidence**

A dataset can be catalogued without being comparable, eligible or validated.
Only layer 3 is Atlas evidence. Any count published for layers 1–2 is
labelled with its layer.

## Model

- **Identity:** organisms by NCBI Taxonomy ID, assemblies by accession.version,
  runs by INSDC accession. Species ≠ assembly; sample ≠ run.
- **Platform facets kept separate:** technology family → vendor → instrument
  family → instrument model, plus chemistry, read mode and basecaller.
  NovaSeq, Revio and PromethION are instrument families, not technologies.
- **Mirrors counted once:** NCBI SRA, ENA and DDBJ records of one run are one
  dataset.

## Role of automation

Scheduled, free CI (GitHub Actions) is intended to handle metadata
discovery, normalization, validation, manifests and release-candidate
builds. Public data stays at its source. Heavy compute is used selectively,
preferring existing public outputs over reprocessing raw reads. Publishing a
release stays a human-approved step.

## Role and limits of ML

ML may **assist** with messy metadata, such as proposing normalized values,
entity resolution, duplicate detection, triage and anomaly flags. It reports
confidence and can route records to human review. An ML-only value **never**
satisfies a hard eligibility gate: those fields need authoritative source
metadata, deterministic normalization of it, or curator confirmation. ML
**never** decides biological truth, benchmark truth, validation outcomes,
release inclusion, clinical interpretation, technology or caller rankings,
or trust scores. No model has been trained, and no ML threshold is active.
The current values are provisional placeholders, pending M2 calibration.

## Reproducibility and versioning

- Releases are immutable and semantically versioned (v1.0.0 → v1.1.0 → v2.0.0).
  Each has a manifest, source snapshot, provenance, a PASS validation report,
  checksums, a GitHub release and a Zenodo version.
- Continuous discovery feeds **future** releases. It never mutates a past
  release.
- v1.0.0 is protected by checksummed manifests of 467 frozen files
  ([`releases/v1.0.0/`](releases/v1.0.0/)), verified by the test suite.
  There are two lineages: 197 scientific-release files from the `v1.0.0` tag,
  and 270 later Evidence Explorer web-delivery files (commit `da19599`) that
  re-represent, but do not alter, the frozen observations.

## Current milestone and roadmap

```text
M0  Expansion protocol            FROZEN / APPROVED (2026-10-01)
M1A Bounded metadata pilot        IMPLEMENTATION READY, cloud pilot pending
M1B Automated metadata catalog    not started
M2  Normalization engine          not started
M3  Eligibility engine            not started
M4  Human multi-platform release  not started
M5  Multispecies release          not started
M6  Automated release pipeline    not started
```

- Protocol: [`docs/atlas/m0_expansion_protocol.md`](docs/atlas/m0_expansion_protocol.md)
  (lock: [`docs/atlas/m0_expansion_protocol.lock`](docs/atlas/m0_expansion_protocol.lock);
  verify with `python scripts/atlas/freeze_m0_protocol.py --check`)
- Roadmap with validation gates: [`docs/roadmap.md`](docs/roadmap.md)
- Public progress policy: [`docs/public_progress_policy.md`](docs/public_progress_policy.md)
- M1A catalog pilot: [`docs/atlas/m1a_catalog.md`](docs/atlas/m1a_catalog.md)
  (canonical run is manual GitHub Actions only; local tests are offline; no raw
  sequence processing, ML, evidence validation, release or deployment)

---

# Repository architecture

```text
omicsedge-benchmark-evidence/
│
├── docs/
│   ├── scientific_scope.md
│   ├── evidence_semantics.md
│   ├── conceptual_schema.md
│   ├── phase1b/
│   ├── phase2/
│   ├── atlas/                  # expansion protocol (in development)
│   ├── roadmap.md
│   └── public_progress_policy.md
│
├── schemas/
│   ├── experiment.schema.json
│   ├── benchmark_run.schema.json
│   ├── event.schema.json
│   ├── observation.schema.json
│   ├── provenance_link.schema.json
│   ├── variant.phase1b.schema.json
│   └── atlas/0.1.0/            # expansion entity schemas
│
├── config/
│   └── atlas/                  # controlled vocabularies + policies
│
├── releases/
│   └── v1.0.0/                 # frozen artifact manifest + release record
│
├── src/
│   ├── benchmark_evidence/     # v1 (frozen)
│   └── evidence_atlas/         # expansion protocol rules
│
├── scripts/
│   ├── phase1b/
│   ├── phase2/
│   └── atlas/
│
├── sql/
│   ├── event_evidence.sql
│   └── phase1b/
│
├── tests/
│
├── data/
│   ├── manifests/
│   ├── phase1b/
│   └── phase2/
│
├── results/
│   ├── phase1b/
│   └── phase2/
│
├── environment/
│
└── notebooks/
```

Large reconstructable genomic files are intentionally excluded from Git.

---

# Compute architecture

The project separates durable scientific artifacts from temporary heavy computation.

```mermaid
flowchart TB

    subgraph GitHub["GitHub · durable provenance"]
        A["Protocols"]
        B["Schemas"]
        C["Manifests"]
        D["Checksums"]
        E["Compact evidence"]
        F["Tests"]
    end

    subgraph Local["Mac · development"]
        G["Code"]
        H["Metadata"]
        I["Validation"]
        J["DuckDB / inspection"]
    end

    subgraph Colab["Colab · ephemeral heavy compute"]
        K["Large query VCFs"]
        L["Truth / reference assets"]
        M["hap.py + vcfeval"]
        N["Temporary benchmark outputs"]
    end

    GitHub --> Local
    GitHub --> Colab

    Colab -->|"compact validated results"| GitHub

    Local --> GitHub
```

Raw Phase 2 VCFs and large comparator workspaces therefore do **not** need to remain permanently on the development machine.

---

# Reproducibility

Frozen scientific decisions are represented using:

```text
protocol documents
.lock files
SHA-256 manifests
source URLs
source checksums
deterministic identifiers
deterministic selection algorithms
schema validation
synthetic adversarial tests
independent reconstruction checks
```

Phase 1B deterministic reconstruction reproduced the identity entities byte-for-byte.

Important frozen Phase 2 artifacts include:

```text
docs/phase2/phase2_protocol.md
docs/phase2/phase2_protocol.lock

docs/phase2/interval_selection_method.md
docs/phase2/interval_selection_method.lock

data/phase2/admitted_sources.tsv
data/phase2/context_beds.tsv
data/phase2/context_beds_downloaded.tsv

data/phase2/selected_intervals.tsv
data/phase2/selected_assessable_segments.bed
data/phase2/interval_panel.lock

results/phase2/interval_selection_summary.json
```

---

# Query model

The product-facing query is intended to begin from biological identity:

```sql
SELECT *
FROM variant_evidence
WHERE variant_id = ?;
```

and return the evidence without destroying its experimental structure:

```text
VARIANT
 ├── EVENT
 │    ├── benchmark run
 │    ├── experiment
 │    ├── technology
 │    └── OBSERVATION
 │
 ├── EVENT
 │    ├── benchmark run
 │    ├── experiment
 │    ├── technology
 │    └── OBSERVATION
 │
 └── provenance
```

The same variant can therefore expose multiple independent empirical histories.

---

# Roadmap

```mermaid
flowchart LR

    A["Phase 1A<br/>Empirical registry"] -->|PASS| B["Phase 1B<br/>Variant identity"]

    B -->|15/15 PASS| C["Phase 2A<br/>Source expansion"]

    C --> D["Phase 2B<br/>Context + panel"]

    D -->|FROZEN| E["Phase 2C<br/>Expanded benchmarking"]

    E --> F["Phase 2D<br/>Identity expansion"]

    F --> G["Phase 2E<br/>Product validation"]

    G --> H["Evidence Explorer"]

    H --> I["Public release"]
```

Current position:

```text
Phase 1A  ████████████████████  PASS
Phase 1B  ████████████████████  PASS
Phase 2A  ████████████████████  PASS
Phase 2B  ████████████████████  PASS / FROZEN
Phase 2C  ████████████████████  PASS
Phase 2D  ████████████████████  PASS
Phase 2E  ████████████████████  20 / 20 PASS
Explorer  ████████████████████  LIVE
```

---

# Local development

```bash
python -m pip install -e '.[dev]'
pytest
```

Phase-specific verification and reproducibility scripts live under:

```text
scripts/phase1b/
scripts/phase2/
```

Verify that the released v1.0.0 artifacts are unchanged:

```bash
python scripts/atlas/build_v1_freeze_manifest.py --check
```

---

# Data policy

The repository favors compact, reproducible artifacts.

Large public genomic resources are referenced by:

```text
source URL
artifact identity
release/version
checksum
retrieval provenance
```

rather than duplicated unnecessarily in Git.

Large Phase 2 computation is intended to occur in temporary compute environments, while validated compact evidence is retained.

---

# Scientific scope

Project 003 currently focuses on:

**germline small-variant benchmark evidence**

across multiple:

```text
samples
sequencing technologies
benchmark runs
genomic contexts
source artifacts
truth releases
comparator versions
```

The project is not currently intended to provide:

```text
clinical interpretation
variant pathogenicity
variant calling
patient-level analysis
technology purchasing recommendations
caller leaderboards
```

---

# Release, citation, and reuse

Project 003 is released as the **OmicsEdge Benchmark Evidence Registry v1.0.0** research release (Evidence Atlas v1.0.0).

For citation metadata, see:

- [`CITATION.cff`](CITATION.cff)

Original OmicsEdgeBio software code is released under the:

- [MIT License](LICENSE)

Public benchmark inputs, truth resources, source metadata, and derived materials may have separate source terms. See:

- [`THIRD_PARTY_DATA_NOTICE.md`](THIRD_PARTY_DATA_NOTICE.md)

The authoritative frozen Phase 2 release is:

- Archive: `results/phase2e/omicsedge_phase2_final_results.tar.gz`
- SHA-256: `186cbed74fa718a728f7a24b43d58118a308165fae385eb95cc4cb4444788ca3`
- Size: `8,708,768 bytes`
- Validation: **20 / 20 PASS**
- Zenodo DOI: [`10.5281/zenodo.23085673`](https://doi.org/10.5281/zenodo.23085673)

The registry is a research resource and does not provide clinical interpretation, pathogenicity assessment, reliability scoring, technology ranking, or medical advice.

---

# Vision

The longer-term goal is a searchable empirical evidence layer where a researcher can ask:

> **What do public benchmark experiments actually show for this variant, under which conditions, and with what provenance?**

Instead of returning a black-box confidence number, the registry should expose the observations necessary for the researcher to inspect the evidence directly.

<div align="center">

### Evidence first. Provenance preserved. Conclusions remain inspectable.

**OmicsEdgeBio**

</div>
