# Evidence Atlas — Release Model

Status: FROZEN / APPROVED (`FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION`, 2026-10-01). Locked by [`m0_expansion_protocol.lock`](m0_expansion_protocol.lock).

Machine-readable: [`schemas/atlas/0.1.0/release_manifest.schema.json`](../../schemas/atlas/0.1.0/release_manifest.schema.json)

Invariants: `validate_release_manifest` in [`src/evidence_atlas/protocol.py`](../../src/evidence_atlas/protocol.py)

## Principle

> Continuous discovery does **not** mean continuously mutating a released
> dataset.

The catalog layer changes continuously. A release is a frozen, versioned
snapshot of validated records and is never edited after publication.

## Versions

| Version | Meaning (illustrative) |
|---|---|
| v1.0.0 | Released Project 003: human, GRCh38, Illumina + ONT, HG002–HG004 (frozen). |
| v1.x.0 | Backwards-compatible additions under the same evidence semantics (e.g. new validated records or samples). |
| v1.0.x | Corrections that change no evidence semantics (documentation or metadata fixes with full disclosure). |
| v2.0.0 | Breaking change in evidence semantics or entity model (e.g. first multispecies release, if it changes the record contract). |

Rules, all enforced:

- the version advances strictly past `previous_release`;
- `release_kind` matches the semver bump (MAJOR resets minor and patch;
  MINOR resets patch);
- the Git tag is exactly `v<release_version>`;
- a release contains at most one version of each record;
- artifact paths are unique.

## Required release contents

| Item | Field / artifact |
|---|---|
| Version | `release_version`, `release_kind`, `previous_release` |
| Schema version | `entity_schema_version` (+ each record's `schema_version`) |
| Policy versions | `policy_versions.{eligibility_policy, ml_policy, technology_taxonomy, organisms_assemblies, sources}` |
| Manifest | the release manifest itself, plus `records[]` with `content_sha256` per record version |
| Source snapshot | `source_snapshot` with per-source retrieval time and raw snapshot SHA-256 |
| Provenance | `provenance.build_activity_id`, `workflow`, `workflow_run_url` |
| Validation report | `validation_report` with `verdict` **PASS** and `gates_passed == gates_total` |
| Checksums | `checksums_manifest` and `artifacts[].sha256` |
| GitHub release | `git.tag`, `git.commit` (full 40-character SHA) |
| Zenodo | `zenodo.deposit_status`; `DEPOSITED` requires `version_doi` |
| Website metadata | `website.release_path` (stable, versioned), `is_latest_at_publication` |

A manifest whose validation verdict is not `PASS` fails the schema. A release
cannot be built from failed validation.

## Release procedure (from M4 onward)

1. Freeze the candidate set: `VALIDATED` records only.
2. Build the bundle and manifest in GitHub Actions (manual dispatch).
3. Run `validate_release_manifest` and the protocol test suite. Any failure
   stops the release.
4. Tag `v<version>` and publish the GitHub Release with the bundle and
   checksums.
5. Deposit to Zenodo as a new version and record the version DOI in a
   follow-up commit. The tagged manifest is never edited. The DOI relation is
   recorded in a release record beside it, as v1 does in
   `releases/v1.0.0/release_record.json`.
6. Transition included records `VALIDATED → RELEASED` with a `RELEASE_BUILD`
   actor and the release version.
7. Update website release metadata. "Latest" may advance. Older versions keep
   their versioned paths.

## Directory convention

```text
releases/
  v1.0.0/
    release_record.json          # identity, DOI, archive, counts
    frozen_artifacts.sha256      # immutable file manifest
  v1.1.0/                         # future
    release_manifest.json        # validates against release_manifest.schema.json
    checksums.sha256
    validation_report.json
```

## Relationship to v1.0.0

v1.0.0 predates the atlas-0.1.0 manifest schema. It is described by
`releases/v1.0.0/release_record.json` and its frozen artifact manifest. It is
not retrofitted, because retrofitting would itself mutate the release. The
first atlas-0.1.0 release manifest sets `previous_release: "1.0.0"`.
