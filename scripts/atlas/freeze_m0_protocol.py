#!/usr/bin/env python3
"""Freeze the approved M0 Evidence Atlas Expansion Protocol.

Writes ``docs/atlas/m0_expansion_protocol.lock`` in the repository's existing
``.lock`` convention (``key=value`` rows, ``<artifact>_sha256=`` digests and a
``status=FROZEN_...`` row), covering the approved M0 artifacts:

* protocol documents, roadmap and public-progress policy;
* entity and configuration schemas;
* controlled vocabularies, policies and verified seed-identifier provenance;
* executable policy (``src/evidence_atlas``) and M0 scripts (including this one);
* v1 freeze/release metadata (``releases/``).

The frozen v1 scientific data is NOT hashed here; it remains protected by
``releases/v1.0.0/*.sha256``, which this lock pins. Tests and README.md are
living files and are not locked, matching the existing convention.

Usage (from the repository root):

    python scripts/atlas/freeze_m0_protocol.py           # write the lock
    python scripts/atlas/freeze_m0_protocol.py --check   # verify only
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from evidence_atlas import protocol  # noqa: E402

LOCK = protocol.M0_LOCK
PROTOCOL_DOC = "docs/atlas/m0_expansion_protocol.md"
APPROVAL_DATE = "2026-10-01"
BASE_COMMIT = "da195997c5fc14d7b11f55550a9650a4ab568811"

LOCKED_GLOBS = (
    "docs/atlas/*.md",
    "docs/roadmap.md",
    "docs/public_progress_policy.md",
    "schemas/atlas/**/*",
    "config/atlas/**/*",
    "src/evidence_atlas/*.py",
    "scripts/atlas/*.py",
    "releases/README.md",
    "releases/v1.0.0/*",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locked_paths() -> list[str]:
    paths: set[str] = set()
    for pattern in LOCKED_GLOBS:
        for path in REPO_ROOT.glob(pattern):
            if path.is_file() and "__pycache__" not in path.parts and path != LOCK:
                paths.add(path.relative_to(REPO_ROOT).as_posix())
    return sorted(paths)


def build_lock_text() -> str:
    v1_frozen = set(protocol.read_sha256_manifest(protocol.V1_FREEZE_MANIFEST))
    paths = locked_paths()
    overlap = v1_frozen & set(paths)
    if overlap:
        raise SystemExit(f"M0 lock must not absorb frozen v1 artifacts: {sorted(overlap)}")
    if PROTOCOL_DOC not in paths:
        raise SystemExit(f"protocol document missing: {PROTOCOL_DOC}")

    eligibility = protocol.load_config("eligibility_policy")
    ml_policy = protocol.load_config("ml_policy")
    record = protocol._load_json(protocol.V1_RELEASE_RECORD)

    rows = [
        ("project", "OmicsEdgeBio Evidence Atlas"),
        ("milestone", "M0"),
        ("title", "M0 — Evidence Atlas Expansion Protocol"),
        ("approval_date", APPROVAL_DATE),
        ("base_commit", BASE_COMMIT),
        ("protocol", PROTOCOL_DOC),
        ("protocol_sha256", sha256(REPO_ROOT / PROTOCOL_DOC)),
        ("entity_schema_version", protocol.SCHEMA_VERSION),
        ("eligibility_policy_version", eligibility["policy_version"]),
        ("ml_policy_version", ml_policy["policy_version"]),
        ("technology_taxonomy_version", protocol.load_config("technology_taxonomy")["taxonomy_version"]),
        ("organisms_assemblies_version", protocol.load_config("organisms_assemblies")["registry_version"]),
        ("sources_version", protocol.load_config("sources")["source_registry_version"]),
        ("v1_scientific_release_commit", record["scientific_release"]["source_commit"]),
        ("v1_web_delivery_commit", record["web_delivery"]["source_commit"]),
        ("v1_combined_freeze_manifest_sha256", record["combined_freeze"]["manifest_sha256"]),
        ("v1_frozen_file_count", str(record["combined_freeze"]["file_count"])),
        ("v1_scientific_data_hashed_by_this_lock", "false"),
    ]
    rows += [(f"{path}_sha256", sha256(REPO_ROOT / path)) for path in paths]
    rows += [
        ("locked_file_count", str(len(paths))),
        ("ml_only_value_satisfies_hard_gate", "false"),
        ("ml_thresholds_active", str(ml_policy["thresholds"]["active"]).lower()),
        ("ml_models_active", str(len(ml_policy["model_registry"]["active_models"]))),
        ("ml_model_trained", "false"),
        ("genomic_data_downloaded", "false"),
        ("m1_implementation_started", "false"),
        ("website_modified", "false"),
        ("deployment_performed", "false"),
        ("reliability_scoring_enabled", "false"),
        ("technology_ranking_enabled", "false"),
        ("status", protocol.M0_LOCK_STATUS),
    ]
    return "".join(f"{key}={value}\n" for key, value in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args()

    if protocol.v1_freeze_violations():
        print("V1_FREEZE_VERIFICATION_FAIL", file=sys.stderr)
        return 1

    if args.check:
        violations = protocol.m0_lock_violations()
        if violations:
            print("\n".join(violations), file=sys.stderr)
            print("M0_LOCK_VERIFICATION_FAIL", file=sys.stderr)
            return 1
        print(f"verified {len(protocol.lock_file_entries(protocol.parse_lock(LOCK)))} locked artifacts")
        print("M0_LOCK_VERIFICATION_PASS")
        return 0

    LOCK.write_text(build_lock_text())
    if protocol.m0_lock_violations():
        print("M0_LOCK_VERIFICATION_FAIL", file=sys.stderr)
        return 1
    print(f"wrote {LOCK.relative_to(REPO_ROOT)}")
    print("M0_LOCK_VERIFICATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
