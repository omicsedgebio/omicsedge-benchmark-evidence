# Public Progress Policy

Status: FROZEN / APPROVED (`FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION`, 2026-10-01). Locked by [`m0_expansion_protocol.lock`](atlas/m0_expansion_protocol.lock).

This policy decides what each public surface says about Evidence Atlas, and
when. It exists so the published picture never runs ahead of the evidence.

## Three surfaces

### GitHub: the engineering and scientific record

Shows real development as it happens:

- code, protocols and schemas;
- manifests, checksums and validation reports;
- release notes and reproducibility instructions;
- tests and their results;
- open and resolved scientific decisions.

GitHub is the place for detail, including work in progress, failures and
reversals. Work in progress is labelled as such (e.g.
`Status: PROPOSED_FOR_REVIEW`).

### omicsedge.bio: business-relevant, defensible milestones

Shows only:

- **released capability**, such as Evidence Atlas v1.0.0, with DOI;
- **meaningful in-development capability**, clearly labelled *in
  development*;
- **real aggregate counts**, each with its counting unit and layer (e.g.
  "catalogued INSDC runs" versus "validated released records");
- **scientific boundaries**: no trust scores, no rankings, no clinical
  interpretation;
- links to the GitHub repository and the release.

The website is **not** a development log. It does not mirror commits, partial
results or internal milestones. It changes only when a milestone gate passes
or a release is published.

Wording rules:

- Never imply that catalogued means validated evidence.
- Future capabilities use future or in-development wording. They are never
  described as available.
- Counts from the catalog or candidate layers are always labelled with their
  layer.
- v1.0.0 stays described and reachable after newer releases.

### LinkedIn: major milestones only

A LinkedIn announcement requires **all** of:

1. a real technical or scientific change;
2. reproducible evidence (a validation or evaluation report);
3. a concrete result (a number, a release or a capability);
4. a public GitHub artifact (tag, release, report);
5. website status updated, where appropriate.

Not announced: ordinary commits, refactors, cosmetic or documentation
changes, dependency bumps, protocol drafts that are not yet approved, and
anything whose gate has not passed.

## Candidate major milestones

| Milestone | Announce when | Required artifact |
|---|---|---|
| M0 Expansion protocol frozen | Protocol approved and lock file committed | Locked protocol, schemas, passing tests |
| M1 Automated public-data catalog working | M1 gate passes on two consecutive scheduled runs | Catalog snapshot + statistics report |
| M2 Normalization engine evaluated | Evaluation report published | Evaluation report (+ model card if ML) |
| M3 Evidence eligibility system working | Audit passes | Audit report + assessment data |
| M4 Human multi-platform release | Release published and verified | Tagged release, manifest, DOI |
| M5 Multispecies release | Release published and verified | Tagged release, manifest, DOI |
| M6 End-to-end automated release pipeline | Reproducible candidate build plus an approved release | Reproducibility report |

## Surface matrix

| Event | GitHub | omicsedge.bio | LinkedIn |
|---|---|---|---|
| Commit / PR / refactor | ✔ | — | — |
| Protocol draft under review | ✔ | — | — |
| Milestone gate passed | ✔ | ✔ (if business-relevant) | ✔ (if in the table above) |
| Release published | ✔ | ✔ | ✔ |
| Failure or reversal | ✔ (documented) | update only if a public claim is affected | — |
| Correction to a released version | ✔ (new release) | ✔ (note on the affected version) | only if it changes a previously announced claim |

## State at the M0 freeze (2026-10-01)

- **GitHub:** M0 protocol approved and locked
  (`docs/atlas/m0_expansion_protocol.lock`).
- **omicsedge.bio:** unchanged by M0. Any update follows this policy and is a
  separate, deliberate step.
- **LinkedIn:** M0 now meets the conditions for an announcement, but nothing
  has been drafted or published. That is a separate, deliberate step.
