# Evidence Atlas — Expansion Roadmap

Status: FROZEN / APPROVED (`FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION`, 2026-10-01). Locked by [`m0_expansion_protocol.lock`](atlas/m0_expansion_protocol.lock).

Released: **Evidence Atlas v1.0.0** (Project 003). It is frozen.

Frozen development milestone: **M0 — Evidence Atlas Expansion Protocol** (approved 2026-10-01)

Next: **M1 — Automated Public Data Catalog** (not started)

This roadmap is part of the frozen M0 protocol. The status block below is a
snapshot taken at the M0 freeze. Live progress is tracked in the repository
README. Changing a milestone's definition or gate requires a reviewed
amendment.

Each milestone advances only when its validation gate passes. Website and
LinkedIn milestones follow [public_progress_policy.md](public_progress_policy.md).
A milestone that is not reached is not announced.

```text
M0  Expansion protocol            ████████████████████  FROZEN / APPROVED
M1  Automated metadata catalog    ░░░░░░░░░░░░░░░░░░░░  NEXT · NOT STARTED
M2  Normalization engine          ░░░░░░░░░░░░░░░░░░░░  NOT STARTED
M3  Eligibility engine            ░░░░░░░░░░░░░░░░░░░░  NOT STARTED
M4  Human multi-platform release  ░░░░░░░░░░░░░░░░░░░░  NOT STARTED
M5  Multispecies release          ░░░░░░░░░░░░░░░░░░░░  NOT STARTED
M6  Automated release pipeline    ░░░░░░░░░░░░░░░░░░░░  NOT STARTED
```

---

## M0 — Expansion protocol

| | |
|---|---|
| Objective | Freeze the architecture, entity model, vocabularies, eligibility, ML, compute, release and publication rules before any expansion data is touched. |
| Inputs | v1.0.0 repository; the M0 brief. |
| Outputs | `docs/atlas/*`, `schemas/atlas/0.1.0/*`, `config/atlas/*`, `src/evidence_atlas/protocol.py`, `releases/v1.0.0/*`, this roadmap, `docs/public_progress_policy.md`. |
| Validation gate | All schemas valid (2020-12). All configs pass schema and integrity checks. Negative tests reject every listed protocol violation. v1 freeze check passes with 0 violations. Existing suite still green. Human review approves. |
| GitHub deliverable | Reviewed pull request; `m0_expansion_protocol.lock` generated on approval. |
| Website milestone | Optional "In development: cross-species / cross-platform expansion" line, with no counts. |
| LinkedIn milestone | Optional: "Expansion protocol frozen", only after approval and the lock. |
| Advance when | Protocol approved and locked; unresolved decisions U1–U10 recorded with owners. |

## M1 — Automated public-data catalog

| | |
|---|---|
| Objective | Scheduled, incremental, metadata-only discovery into the Public Data Catalog for a bounded initial scope: human + one non-human seed organism, and the INSDC group + GIAB indexes. |
| Inputs | `config/atlas/sources.json`; source APIs; seed organism/assembly registry. |
| Outputs | SOURCE_RECORD snapshots, CATALOG_RECORDs in `CATALOGUED`, discovery PROVENANCE_ACTIVITY records, compact sharded catalog snapshot, and a catalog statistics report with explicit counting units. |
| Validation gate | 100% of records schema-valid. INSDC mirror deduplication verified on a hand-checked sample (0 double counts). Re-running on an unchanged window is idempotent (byte-identical snapshot). Seed identifiers re-verified with `verify_seed_assemblies.py` and any NCBI status change reviewed (U7). No raw read files downloaded. Free-tier limits respected. |
| GitHub deliverable | Discovery workflow; catalog snapshot; statistics report; tests. |
| Website milestone | "Public data catalog operating", with catalogued counts clearly labelled *catalogued, not evidence*. |
| LinkedIn milestone | "Automated public-data catalog working", with a concrete, reproducible count and a link. |
| Advance when | Gate passes on two consecutive scheduled runs. |

## M2 — Metadata normalization engine

| | |
|---|---|
| Objective | Rules-first normalization of platform, library, organism and assembly fields, with an optional evaluated ML fallback for ambiguous strings. |
| Inputs | M1 catalog; taxonomy and organism registries; a frozen, checksummed labelled evaluation set created **before** any model training. |
| Outputs | `normalized_value` fields with method/confidence; rule tables; optional model plus calibration and evaluation report; updated taxonomy version. |
| Validation gate | Rules-only precision and coverage reported. If ML is used, thresholds are activated only with all six activation reports in `ml_policy.md` (frozen evaluation set, class-specific performance, calibration, abstention, error analysis, threshold rationale), chosen from that evidence (U6). ML must beat the rules-only baseline on coverage without losing precision. ML-only values still never satisfy a hard eligibility gate. Family-only strings never produce a model. |
| GitHub deliverable | Normalizer code, rule tables, evaluation report, model card (if any), tests. |
| Website milestone | "Metadata normalization evaluated", with the headline precision/coverage and a link to the report. |
| LinkedIn milestone | "Normalization engine evaluated", only with a published evaluation report. |
| Advance when | Evaluation report reviewed; thresholds frozen in a new `ml_policy` version. |

## M3 — Evidence eligibility engine

| | |
|---|---|
| Objective | Evaluate criteria E01–E13 deterministically and drive the lifecycle state machine, with a human curation pathway for `NEEDS_REVIEW`. |
| Inputs | Normalized catalog; eligibility policy; truth-source registry. |
| Outputs | ELIGIBILITY_ASSESSMENTs; state transitions with history; curation queue; per-criterion failure/abstention report. |
| Validation gate | Every assessment's outcome equals `aggregate_eligibility`. Every transition is allowed by the policy. A hand-audited sample confirms decisions. No record skips a state. U3 (cross-assembly) resolved. |
| GitHub deliverable | Eligibility engine, curation tooling, audit report, tests. |
| Website milestone | "Evidence eligibility system working", with candidate counts labelled *eligible candidates, not validated evidence*. |
| LinkedIn milestone | "Evidence eligibility system working". |
| Advance when | Audit passes; candidate set for M4 frozen **before** any benchmark outcome is inspected. |

## M4 — Human multi-platform release

| | |
|---|---|
| Objective | First expansion release: additional human samples and/or technologies (e.g. PacBio HiFi) under a frozen protocol, as v1.x or v2.0. |
| Inputs | Frozen candidate set from M3; frozen benchmark protocol; truth sources. |
| Outputs | Validated records; release manifest; validation report; GitHub Release; Zenodo version. |
| Validation gate | Frozen protocol gates all PASS; `validate_release_manifest` passes; v1 freeze check passes; independent re-verification of the archive (as in v1 Phase 2E). U2, U4, U5, U9 and U10 resolved. |
| GitHub deliverable | Tagged release with manifest and checksums. |
| Website milestone | New release published. "Latest" advances; v1.0.0 stays addressable. |
| LinkedIn milestone | "Human multi-platform release", with release DOI and concrete counts. |
| Advance when | Release published and verified. |

## M5 — Multispecies release

| | |
|---|---|
| Objective | First release containing validated non-human records. |
| Inputs | Catalog and eligibility for ≥1 non-human organism; a resolved non-human truth/comparator definition (U1). |
| Outputs | Release as in M4. |
| Validation gate | U1 resolved and frozen **before** data inspection; all protocol gates PASS; species and assembly facets fully resolved for every released record. |
| GitHub deliverable | Tagged release. |
| Website milestone | Multispecies release published. |
| LinkedIn milestone | "Multispecies release". |
| Advance when | Release published and verified. |

## M6 — End-to-end automated release pipeline

| | |
|---|---|
| Objective | Discovery → normalization → eligibility → validation → release-candidate build, automated in free CI. Publication stays a human-approved step. |
| Inputs | M1–M5 components. |
| Outputs | Pipeline that produces a release *candidate* plus reports. Human approval publishes. |
| Validation gate | Pipeline rebuilds the most recent release byte-identically from its recorded source snapshot. Failure modes are safe (no partial releases). Runs within free-tier limits. |
| GitHub deliverable | Pipeline workflows; reproducibility report. |
| Website milestone | "Automated release pipeline", describing the process, not a new dataset. |
| LinkedIn milestone | "End-to-end automated release pipeline". |
| Advance when | Two consecutive candidate builds pass and one is approved and released. |
