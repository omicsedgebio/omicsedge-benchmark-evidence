from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmark_evidence import RegistryValidationError, validate_bundle


FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_registry.json"


@pytest.fixture()
def synthetic_bundle() -> dict:
    return json.loads(FIXTURE.read_text())


def test_synthetic_bundle_is_explicitly_non_scientific(synthetic_bundle: dict) -> None:
    assert synthetic_bundle["fixture_notice"].startswith("SYNTHETIC")
    assert all(
        artifact["uri"].startswith(("https://example.invalid/", "urn:synthetic:"))
        for artifact in synthetic_bundle["source_artifacts"]
    )


def test_synthetic_bundle_validates(synthetic_bundle: dict) -> None:
    validate_bundle(synthetic_bundle)


def test_unresolved_run_artifact_fails(synthetic_bundle: dict) -> None:
    broken = copy.deepcopy(synthetic_bundle)
    broken["benchmark_runs"][0]["truth_artifact_id"] = "missing-artifact"
    with pytest.raises(RegistryValidationError, match="unresolved truth_artifact_id"):
        validate_bundle(broken)


def test_cross_run_event_reference_fails(synthetic_bundle: dict) -> None:
    broken = copy.deepcopy(synthetic_bundle)
    broken["observations"][0]["benchmark_run_id"] = "another-run"
    with pytest.raises(RegistryValidationError, match="different runs"):
        validate_bundle(broken)


def test_missing_raw_artifact_lineage_fails(synthetic_bundle: dict) -> None:
    broken = copy.deepcopy(synthetic_bundle)
    broken["provenance_links"] = [
        link for link in broken["provenance_links"] if link["relation"] != "NORMALIZED_FROM"
    ]
    with pytest.raises(RegistryValidationError, match="missing NORMALIZED_FROM"):
        validate_bundle(broken)


def test_padded_interval_must_contain_core(synthetic_bundle: dict) -> None:
    broken = copy.deepcopy(synthetic_bundle)
    broken["benchmark_runs"][0]["padded_interval"]["start_0based"] = 150
    with pytest.raises(RegistryValidationError, match="does not contain core interval"):
        validate_bundle(broken)


def test_unknown_is_not_silently_replaced_by_null(synthetic_bundle: dict) -> None:
    broken = copy.deepcopy(synthetic_bundle)
    broken["experiments"][0]["caller_versions"] = [None]
    with pytest.raises(RegistryValidationError, match="caller_versions"):
        validate_bundle(broken)


def test_duplicate_identifier_fails(synthetic_bundle: dict) -> None:
    broken = copy.deepcopy(synthetic_bundle)
    broken["events"].append(copy.deepcopy(broken["events"][0]))
    with pytest.raises(RegistryValidationError, match="duplicate event_id"):
        validate_bundle(broken)
