from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "results/explorer_v1"
ARCHIVE = ROOT / "results/phase2e/omicsedge_phase2_final_results.tar.gz"
EXPECTED_ARCHIVE_SHA256 = "186cbed74fa718a728f7a24b43d58118a308165fae385eb95cc4cb4444788ca3"
FORBIDDEN = {
    "reliability_score",
    "trust_score",
    "confidence_score",
    "consensus",
    "consensus_decision",
    "trusted",
    "technology_winner",
    "caller_winner",
    "preferred_technology",
    "pathogenicity",
    "clinical_significance",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(name: str):
    path = OUTPUT / name
    assert path.is_file(), f"missing Explorer output; run the exporter first: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def explorer() -> dict:
    return {
        "manifest": load_json("explorer_manifest.json"),
        "variants": load_json("variants.json"),
        "events": load_json("events.json"),
        "evidence": load_json("evidence.json"),
        "unresolved": load_json("unresolved_events.json"),
    }


def test_frozen_release_and_unified_counts(explorer: dict) -> None:
    assert sha256(ARCHIVE) == EXPECTED_ARCHIVE_SHA256
    assert explorer["manifest"]["entity_counts"] == {
        "benchmark_runs": 6,
        "event_variant_links": 11_223,
        "events": 11_553,
        "experiments": 6,
        "observations": 23_106,
        "unresolved_events": 60,
        "variants": 4_278,
    }
    assert len(explorer["events"]) == 11_553
    assert len(explorer["evidence"]) == 23_106


def test_phase1_exact_identity(explorer: dict) -> None:
    records = [
        row
        for row in explorer["events"]
        if row["phase_origin"] == "PHASE1A"
        and row["identity_state"] == "EXACT_NORMALIZED_ALLELE"
    ]
    assert len(records) == 3_332
    assert all(row["variant_id"] and row["event_variant_link_id"] for row in records)


def test_phase1_not_evaluated_identity(explorer: dict) -> None:
    records = [
        row
        for row in explorer["events"]
        if row["phase_origin"] == "PHASE1A"
        and row["identity_state"] == "NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY"
    ]
    assert len(records) == 270
    assert all(row["variant_id"] is None for row in records)
    assert all(row["unresolved_reason"] is None for row in records)


def test_phase2_exact_identity(explorer: dict) -> None:
    records = [
        row
        for row in explorer["events"]
        if row["phase_origin"] == "PHASE2C"
        and row["identity_state"] == "EXACT_NORMALIZED_ALLELE"
    ]
    assert len(records) == 7_891
    assert all(row["variant_id"] and row["event_variant_link_id"] for row in records)


def test_phase2_unresolved_identity_has_no_guessed_variant(explorer: dict) -> None:
    unresolved = explorer["unresolved"]
    assert len(unresolved) == 60
    assert all(row["phase_origin"] == "PHASE2C" for row in unresolved)
    assert all(row["identity_state"] == "UNRESOLVED" for row in unresolved)
    assert all(row["variant_id"] is None for row in unresolved)
    assert all(row["event_variant_link_id"] is None for row in unresolved)
    assert all(row["unresolved_reason"] == "MISSING_NORMALIZED_ALLELE_FIELD" for row in unresolved)


def test_observations_are_preserved_not_collapsed(explorer: dict) -> None:
    evidence = explorer["evidence"]
    observation_ids = [row["observation_id"] for row in evidence]
    assert len(observation_ids) == len(set(observation_ids)) == 23_106
    assert all(row["event_id"] for row in evidence)
    assert Counter(row["phase_origin"] for row in evidence) == {
        "PHASE1A": 7_204,
        "PHASE2C": 15_902,
    }


def test_query_and_truth_observations_remain_separate(explorer: dict) -> None:
    sides_by_event: dict[str, set[str]] = defaultdict(set)
    for row in explorer["evidence"]:
        assert row["side"] in {"QUERY", "TRUTH"}
        sides_by_event[row["event_id"]].add(row["side"])
    assert all(sides == {"QUERY", "TRUTH"} for sides in sides_by_event.values())


def _forbidden_keys(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN:
                found.add(key)
            found.update(_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_forbidden_keys(child))
    return found


def test_forbidden_fields_are_absent(explorer: dict) -> None:
    assert not _forbidden_keys(explorer)


@pytest.mark.parametrize(
    "name",
    [
        "explorer_manifest.json",
        "variants.json",
        "events.json",
        "evidence.json",
        "unresolved_events.json",
    ],
)
def test_json_serialization_is_canonical_and_newline_terminated(name: str) -> None:
    path = OUTPUT / name
    raw = path.read_bytes()
    parsed = json.loads(raw)
    expected = (
        json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    assert raw == expected


def test_output_checksum_manifest() -> None:
    checksum_path = OUTPUT / "checksums.sha256"
    lines = checksum_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    for line in lines:
        digest, name = line.split(maxsplit=1)
        assert sha256(OUTPUT / name) == digest

