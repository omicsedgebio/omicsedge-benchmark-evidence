# Evidence Atlas v1.0.0 — Immutability Policy

Status: FROZEN / APPROVED (`FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION`, 2026-10-01). Locked by [`m0_expansion_protocol.lock`](m0_expansion_protocol.lock). Enforced by tests.

## Released resource

| Field | Value |
|---|---|
| Release | OmicsEdge Benchmark Evidence Registry / Evidence Atlas **v1.0.0** (Project 003) |
| Git tag | `v1.0.0` → commit `c61b84335a8cdce0e27fedc146da263f3b10a7fd` |
| Zenodo DOI | [`10.5281/zenodo.23085673`](https://doi.org/10.5281/zenodo.23085673) |
| Registry schema version | `1.0.0` |
| Authoritative archive | `results/phase2e/omicsedge_phase2_final_results.tar.gz` |
| Archive SHA-256 | `186cbed74fa718a728f7a24b43d58118a308165fae385eb95cc4cb4444788ca3` |
| Archive size | 8,708,768 bytes |
| Validation | 20 / 20 PASS |

## What is frozen: two lineages

467 files are frozen, with SHA-256 digests computed from Git blob bytes.
**They do not all come from the `v1.0.0` tag.** They belong to two separate
lineages, and each lineage has its own manifest:

| Lineage | Source | Files | Manifest | Existed at the `v1.0.0` tag? |
|---|---|---|---|---|
| `scientific_release` | tag `v1.0.0` → commit `c61b84335a8cdce0e27fedc146da263f3b10a7fd` | 197 | [`scientific_release.sha256`](../../releases/v1.0.0/scientific_release.sha256) | **Yes** |
| `web_delivery` | commit `da195997c5fc14d7b11f55550a9650a4ab568811` (`da19599`) | 270 | [`web_delivery.sha256`](../../releases/v1.0.0/web_delivery.sha256) | **No**, added afterwards |

[`frozen_artifacts.sha256`](../../releases/v1.0.0/frozen_artifacts.sha256)
is the union of the two lineages (467 entries). It is kept for continuity,
and its own SHA-256 is unchanged from the first M0 draft. It is not a claim
that all 467 files existed at the tag.

1. **Scientific release (197 files).** Every file in the `v1.0.0` tag tree
   except the living repository files listed below. This includes all data,
   results, archives, protocols, `.lock` files, v1 schemas, scripts, SQL,
   environment files, notebooks, workflows, `src/benchmark_evidence/`, the
   licence, the third-party notice and the assets. This is the scientific
   release that Zenodo DOI `10.5281/zenodo.23085673` describes.
2. **Web delivery (270 files).** These are the validated Evidence Explorer
   delivery for the frozen v1 scientific release (`docs/explorer/`,
   `results/explorer_v1/`, `results/explorer_web_v1/`, `scripts/explorer/`).
   They were introduced after the tag in four commits: `0eec7d6` (data
   contract), `77d9293` (canonical export), `fbaf0e3` (web contract) and
   `da19599` (web bundle). **This later delivery does not alter the frozen
   scientific observations.** It provides the validated browser-delivery
   representation of them. Its own frozen contracts forbid recomputing
   outcomes, inferring identity, merging events or changing identity states.

[`releases/v1.0.0/release_record.json`](../../releases/v1.0.0/release_record.json)
records each lineage separately. `scientific_release` holds the version, git
tag, source commit, DOI, archive identity, file count and manifest hash.
`web_delivery` holds the source commit, role, `present_at_git_tag: false`,
`alters_scientific_observations: false`, the introducing commits, path
prefixes, file count and manifest hash. The generator refuses to build if any
web-delivery path already existed at the tag. Tests enforce the lineage
metadata. When the history is available, they also check against Git that
every scientific file exists at the tag and that no web-delivery file does.

### Living repository files (not frozen)

`README.md`, `CITATION.cff`, `pyproject.toml`, `.gitignore` and `tests/`.
These are repository infrastructure. They already changed after the tag (DOI
badge, citation DOI). They can evolve, but they must keep describing v1.0.0
accurately.

## Policy

1. **v1.0.0 is never silently mutated.** No frozen file is edited, replaced,
   regenerated or deleted. `tests/atlas/test_v1_freeze.py` fails if any frozen
   file is missing or differs by one byte.
2. **Corrections produce new releases.** If an error is found in v1.0.0, it is
   documented and corrected in a new version (e.g. v1.0.1 or v1.1.0) with its
   own manifest. The v1.0.0 files stay as published.
3. **Future discoveries produce new releases.** Expansion data never enters
   v1.0.0 and never changes v1.0.0 counts.
4. **Old releases remain reproducible.** The `v1.0.0` tag, the frozen
   manifest, the archive and the Zenodo record stay available. Tests verify the
   frozen files on every run.
5. **"Latest" may move. Old versions stay addressable.** The website's
   "latest" pointer may advance to a newer release. v1.0.0 must stay reachable
   at a stable versioned path and by DOI.
6. **Manifests, provenance and checksums are mandatory** for every release
   (see [release_model.md](release_model.md)).
7. **New code lives beside v1, not inside it.** Expansion code goes in new
   modules (`src/evidence_atlas/`, `scripts/atlas/`, `schemas/atlas/`,
   `config/atlas/`). `src/benchmark_evidence/` and the v1 schemas are frozen.

## Verification

```bash
python scripts/atlas/build_v1_freeze_manifest.py --check
```

```bash
pytest tests/atlas/test_v1_freeze.py
```

The generator recomputes every digest from the Git objects for `v1.0.0` and
`da19599`. It then verifies the working tree and confirms that all three
manifests and the release record are byte-identical to what it would produce. It refuses to write a
manifest if any frozen file has changed.
