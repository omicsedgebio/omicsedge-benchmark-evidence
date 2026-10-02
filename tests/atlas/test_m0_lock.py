"""The approved M0 protocol is frozen by docs/atlas/m0_expansion_protocol.lock."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from evidence_atlas import protocol
from evidence_atlas.protocol import AtlasProtocolError

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def lock() -> dict[str, str]:
    return protocol.parse_lock(protocol.M0_LOCK)


@pytest.fixture(scope="module")
def entries(lock) -> dict[str, str]:
    return protocol.lock_file_entries(lock)


def test_m0_lock_verifies() -> None:
    assert protocol.m0_lock_violations() == []


def test_lock_status_and_identity(lock) -> None:
    assert lock["status"] == "FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION"
    assert lock["milestone"] == "M0"
    assert lock["title"] == "M0 — Evidence Atlas Expansion Protocol"
    assert lock["approval_date"] == "2026-10-01"
    assert lock["protocol"] == "docs/atlas/m0_expansion_protocol.md"


def test_protocol_document_declares_frozen_approved_status() -> None:
    text = (REPO / "docs/atlas/m0_expansion_protocol.md").read_text()
    assert text.startswith("# M0 — Evidence Atlas Expansion Protocol\n")
    assert "Status: FROZEN / APPROVED (`FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION`, 2026-10-01)" in text
    assert "Date: 2026-10-01" in text


def test_lock_records_governance_flags(lock) -> None:
    for key in ("ml_only_value_satisfies_hard_gate", "ml_thresholds_active", "ml_model_trained",
                "genomic_data_downloaded", "m1_implementation_started", "website_modified",
                "deployment_performed", "v1_scientific_data_hashed_by_this_lock",
                "reliability_scoring_enabled", "technology_ranking_enabled"):
        assert lock[key] == "false", key
    assert lock["ml_models_active"] == "0"


def test_lock_pins_policy_versions_to_current_configs(lock) -> None:
    assert lock["entity_schema_version"] == protocol.SCHEMA_VERSION
    assert lock["eligibility_policy_version"] == protocol.load_config("eligibility_policy")["policy_version"]
    assert lock["ml_policy_version"] == protocol.load_config("ml_policy")["policy_version"]


@pytest.mark.parametrize(
    "path",
    [
        "docs/atlas/m0_expansion_protocol.md",
        "docs/atlas/ml_policy.md",
        "docs/atlas/evidence_eligibility_policy.md",
        "docs/atlas/v1_immutability_policy.md",
        "docs/roadmap.md",
        "docs/public_progress_policy.md",
        "schemas/atlas/0.1.0/common.defs.schema.json",
        "schemas/atlas/0.1.0/catalog_record.schema.json",
        "schemas/atlas/0.1.0/config/ml_policy.config.schema.json",
        "config/atlas/eligibility_policy.json",
        "config/atlas/ml_policy.json",
        "config/atlas/organisms_assemblies.json",
        "config/atlas/provenance/assembly_verification.json",
        "src/evidence_atlas/protocol.py",
        "scripts/atlas/freeze_m0_protocol.py",
        "releases/v1.0.0/release_record.json",
        "releases/v1.0.0/frozen_artifacts.sha256",
        "releases/v1.0.0/scientific_release.sha256",
        "releases/v1.0.0/web_delivery.sha256",
    ],
)
def test_approved_artifact_is_locked(entries, path) -> None:
    assert path in entries


def test_every_schema_and_config_is_locked(entries) -> None:
    for path in protocol.schema_paths():
        assert path.relative_to(REPO).as_posix() in entries
    for name in protocol.CONFIG_NAMES:
        assert f"config/atlas/{name}.json" in entries


def test_lock_does_not_absorb_frozen_v1_data(entries, lock) -> None:
    v1 = protocol.read_sha256_manifest(protocol.V1_FREEZE_MANIFEST)
    assert not set(entries) & set(v1)
    record = protocol._load_json(protocol.V1_RELEASE_RECORD)
    assert lock["v1_combined_freeze_manifest_sha256"] == record["combined_freeze"]["manifest_sha256"]
    assert lock["v1_frozen_file_count"] == "467"


def test_living_files_are_not_locked(entries) -> None:
    assert "README.md" not in entries
    assert not any(p.startswith("tests/") for p in entries)
    assert "docs/atlas/m0_expansion_protocol.lock" not in entries


def test_lock_detects_tampering(tmp_path, entries) -> None:
    rel_lock = protocol.M0_LOCK.relative_to(protocol.REPO_ROOT)
    (tmp_path / rel_lock).parent.mkdir(parents=True)
    shutil.copy(protocol.M0_LOCK, tmp_path / rel_lock)
    for rel in entries:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    assert protocol.m0_lock_violations(tmp_path) == []

    with (tmp_path / "config/atlas/ml_policy.json").open("a") as fh:
        fh.write(" ")
    (tmp_path / "docs/roadmap.md").unlink()
    assert protocol.m0_lock_violations(tmp_path) == [
        "CHANGED config/atlas/ml_policy.json",
        "MISSING docs/roadmap.md",
    ]


def test_lock_detects_status_and_count_tampering(tmp_path, entries) -> None:
    rel_lock = protocol.M0_LOCK.relative_to(protocol.REPO_ROOT)
    (tmp_path / rel_lock).parent.mkdir(parents=True)
    for rel in entries:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, tmp_path / rel)
    text = protocol.M0_LOCK.read_text()
    first_entry = next(line for line in text.splitlines() if "/" in line.split("=", 1)[0])
    tampered = text.replace("status=FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION", "status=DRAFT")
    tampered = tampered.replace(first_entry + "\n", "")
    (tmp_path / rel_lock).write_text(tampered)
    violations = protocol.m0_lock_violations(tmp_path)
    assert "STATUS DRAFT" in violations
    assert any(v.startswith("COUNT") for v in violations)


def test_parse_lock_rejects_malformed_and_duplicate_rows(tmp_path) -> None:
    bad = tmp_path / "bad.lock"
    bad.write_text("status=X\nnot a row\n")
    with pytest.raises(AtlasProtocolError, match="invalid lock row"):
        protocol.parse_lock(bad)
    bad.write_text("status=X\nstatus=Y\n")
    with pytest.raises(AtlasProtocolError, match="duplicate lock key"):
        protocol.parse_lock(bad)


def test_locked_digests_are_well_formed(entries) -> None:
    assert all(len(d) == 64 and int(d, 16) >= 0 for d in entries.values())
    assert hashlib.sha256(b"").hexdigest() not in entries.values()
