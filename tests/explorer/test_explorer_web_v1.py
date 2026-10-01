from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CANONICAL = ROOT / "results/explorer_v1"
OUTPUT = ROOT / "results/explorer_web_v1"
BUILDER = ROOT / "scripts/explorer/build_explorer_web_v1.py"
MAX_JSON_BYTES = 20 * 1024 * 1024
EXPECTED_IDENTITY_COUNTS = {
    "EXACT_NORMALIZED_ALLELE": 11_223,
    "NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY": 270,
    "UNRESOLVED": 60,
}
FORBIDDEN_FIELDS = {
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
GENOMIC_CONTEXT_FIELDS = {
    "genomic_context",
    "genomic_contexts",
    "context_class",
    "context_classes",
    "context_label",
    "context_labels",
    "homopolymer",
    "tandem_repeat",
    "low_mappability",
    "segmental_duplication",
    "non_difficult",
}
GENOMIC_CONTEXT_VALUES = {
    "HOMOPOLYMER",
    "TANDEM_REPEAT",
    "LOW_MAPPABILITY",
    "SEGMENTAL_DUPLICATION",
    "NON_DIFFICULT",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_bytes(value) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def load_json(path: Path):
    assert path.is_file(), f"missing web output; run the web builder first: {path}"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def recursive_keys(value) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(key)
            keys.update(recursive_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(recursive_keys(child))
    return keys


def recursive_context_values(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            found.update(recursive_context_values(child))
    elif isinstance(value, list):
        for child in value:
            found.update(recursive_context_values(child))
    elif isinstance(value, str) and value in GENOMIC_CONTEXT_VALUES:
        found.add(value)
    return found


@pytest.fixture(scope="module")
def canonical_summary() -> dict:
    events = load_json(CANONICAL / "events.json")
    variants = load_json(CANONICAL / "variants.json")
    event_by_id = {row["event_id"]: row for row in events}
    variant_by_id = {row["variant_id"]: row for row in variants}

    decisions: dict[str, set[str]] = defaultdict(set)
    variant_types: dict[str, set[str]] = defaultdict(set)
    samples: dict[str, set[str]] = defaultdict(set)
    technologies: dict[str, set[str]] = defaultdict(set)
    observation_ids_by_event: dict[str, set[str]] = defaultdict(set)
    observation_hashes: dict[str, str] = {}
    evidence = load_json(CANONICAL / "evidence.json")
    for row in evidence:
        event_id = row["event_id"]
        observation_id = row["observation_id"]
        assert observation_id not in observation_hashes
        observation_hashes[observation_id] = hashlib.sha256(stable_bytes(row)).hexdigest()
        observation_ids_by_event[event_id].add(observation_id)
        decisions[event_id].add(row["raw_decision"])
        if row.get("raw_variant_type") is not None:
            variant_types[event_id].add(row["raw_variant_type"])
        samples[event_id].add(row["sample_id"])
        technologies[event_id].add(row["technology"])

    return {
        "events": event_by_id,
        "variants": variant_by_id,
        "observation_hashes": observation_hashes,
        "observation_ids_by_event": dict(observation_ids_by_event),
        "decisions": {key: sorted(value) for key, value in decisions.items()},
        "variant_types": {key: sorted(value) for key, value in variant_types.items()},
        "samples": dict(samples),
        "technologies": dict(technologies),
    }


@pytest.fixture(scope="module")
def web_summary() -> dict:
    manifest = load_json(OUTPUT / "manifest.json")
    search = load_json(OUTPUT / "search_index.json")
    shard_index = load_json(OUTPUT / "shard_index.json")
    search_by_event = {row["event_id"]: row for row in search}

    observation_hashes: dict[str, str] = {}
    observation_ids_by_event: dict[str, set[str]] = defaultdict(set)
    event_shards: dict[str, set[str]] = defaultdict(set)
    recursive_found_keys: set[str] = set()
    recursive_found_context_values: set[str] = set()
    for shard in sorted((OUTPUT / "evidence").glob("*.json")):
        rows = load_json(shard)
        assert rows == sorted(rows, key=lambda row: (row["event_id"], row["observation_id"]))
        relative = str(shard.relative_to(OUTPUT))
        for row in rows:
            observation_id = row["observation_id"]
            assert observation_id not in observation_hashes
            observation_hashes[observation_id] = hashlib.sha256(stable_bytes(row)).hexdigest()
            observation_ids_by_event[row["event_id"]].add(observation_id)
            event_shards[row["event_id"]].add(relative)
            recursive_found_keys.update(recursive_keys(row))
            recursive_found_context_values.update(recursive_context_values(row))

    recursive_found_keys.update(recursive_keys(manifest))
    recursive_found_keys.update(recursive_keys(search))
    recursive_found_keys.update(recursive_keys(shard_index))
    recursive_found_context_values.update(recursive_context_values(manifest))
    recursive_found_context_values.update(recursive_context_values(search))
    recursive_found_context_values.update(recursive_context_values(shard_index))
    return {
        "manifest": manifest,
        "search": search,
        "search_by_event": search_by_event,
        "shard_index": shard_index,
        "observation_hashes": observation_hashes,
        "observation_ids_by_event": dict(observation_ids_by_event),
        "event_shards": dict(event_shards),
        "recursive_keys": recursive_found_keys,
        "recursive_context_values": recursive_found_context_values,
    }


def test_exact_event_shard_assignment(web_summary: dict) -> None:
    for event_id, relative in web_summary["shard_index"].items():
        expected_key = hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:2]
        assert relative == f"evidence/{expected_key}.json"


def test_all_observations_for_event_remain_together(
    canonical_summary: dict, web_summary: dict
) -> None:
    assert set(web_summary["event_shards"]) == set(canonical_summary["events"])
    for event_id, paths in web_summary["event_shards"].items():
        assert paths == {web_summary["shard_index"][event_id]}


def test_no_duplicate_missing_or_projected_observations(
    canonical_summary: dict, web_summary: dict
) -> None:
    assert len(web_summary["observation_hashes"]) == 23_106
    assert web_summary["observation_hashes"] == canonical_summary["observation_hashes"]
    assert web_summary["observation_ids_by_event"] == canonical_summary["observation_ids_by_event"]


def test_search_and_shard_index_counts(web_summary: dict) -> None:
    assert len(web_summary["search"]) == 11_553
    assert len(web_summary["search_by_event"]) == 11_553
    assert len(web_summary["shard_index"]) == 11_553
    assert set(web_summary["search_by_event"]) == set(web_summary["shard_index"])


def test_identity_states_and_variant_coordinates_are_preserved(
    canonical_summary: dict, web_summary: dict
) -> None:
    identity_counts = Counter()
    biological_fields = (
        "normalized_start_0based",
        "normalized_end_0based",
        "normalized_ref",
        "normalized_alt",
    )
    for event_id, search in web_summary["search_by_event"].items():
        event = canonical_summary["events"][event_id]
        assert search["identity_state"] == event["identity_state"]
        assert search["variant_id"] == event["variant_id"]
        identity_counts[search["identity_state"]] += 1
        if search["identity_state"] == "EXACT_NORMALIZED_ALLELE":
            variant = canonical_summary["variants"][search["variant_id"]]
            assert all(search[field] == variant[field] for field in biological_fields)
        else:
            assert search["variant_id"] is None
            assert all(search[field] is None for field in biological_fields)
    assert dict(sorted(identity_counts.items())) == EXPECTED_IDENTITY_COUNTS


def test_unresolved_and_not_evaluated_remain_distinct(web_summary: dict) -> None:
    unresolved = [
        row for row in web_summary["search"] if row["identity_state"] == "UNRESOLVED"
    ]
    not_evaluated = [
        row
        for row in web_summary["search"]
        if row["identity_state"] == "NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY"
    ]
    assert len(unresolved) == 60
    assert len(not_evaluated) == 270
    assert all(row["variant_id"] is None for row in unresolved + not_evaluated)
    assert all(row["phase_origin"] == "PHASE1A" for row in not_evaluated)


def test_search_retrieval_fields_come_from_canonical_evidence(
    canonical_summary: dict, web_summary: dict
) -> None:
    for event_id, search in web_summary["search_by_event"].items():
        assert search["raw_decisions"] == canonical_summary["decisions"][event_id]
        assert search["raw_variant_types"] == canonical_summary["variant_types"][event_id]
        assert canonical_summary["samples"][event_id] == {search["sample_id"]}
        assert canonical_summary["technologies"][event_id] == {search["technology"]}
        assert search["raw_decisions"] == sorted(set(search["raw_decisions"]))
        assert search["raw_variant_types"] == sorted(set(search["raw_variant_types"]))


def test_forbidden_and_genomic_context_fields_are_absent(web_summary: dict) -> None:
    assert not (FORBIDDEN_FIELDS & web_summary["recursive_keys"])
    assert not (GENOMIC_CONTEXT_FIELDS & {key.lower() for key in web_summary["recursive_keys"]})
    assert not web_summary["recursive_context_values"]


def test_every_json_is_canonical_and_within_size_limit() -> None:
    json_paths = sorted(OUTPUT.glob("*.json")) + sorted((OUTPUT / "evidence").glob("*.json"))
    assert len(list((OUTPUT / "evidence").glob("*.json"))) <= 256
    for path in json_paths:
        raw = path.read_bytes()
        assert len(raw) <= MAX_JSON_BYTES
        assert raw == stable_bytes(json.loads(raw))


def test_checksum_manifest_is_complete_sorted_and_valid() -> None:
    lines = (OUTPUT / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    entries = [line.split(maxsplit=1) for line in lines]
    relative_paths = [relative for _, relative in entries]
    expected_paths = sorted(
        ["manifest.json", "search_index.json", "shard_index.json"]
        + [str(path.relative_to(OUTPUT)) for path in (OUTPUT / "evidence").glob("*.json")]
    )
    assert relative_paths == expected_paths
    assert "checksums.sha256" not in relative_paths
    for expected, relative in entries:
        assert sha256(OUTPUT / relative) == expected


def test_manifest_contract(web_summary: dict) -> None:
    manifest = web_summary["manifest"]
    assert manifest["web_bundle_schema_version"] == "1.0.0"
    assert manifest["event_count"] == 11_553
    assert manifest["observation_count"] == 23_106
    assert manifest["variant_count"] == 4_278
    assert manifest["identity_state_counts"] == EXPECTED_IDENTITY_COUNTS
    assert manifest["sample_values"] == ["HG002", "HG003", "HG004"]
    assert manifest["technology_values"] == ["ILLUMINA", "ONT"]
    assert manifest["shard_count"] == len(list((OUTPUT / "evidence").glob("*.json")))
    assert all(manifest["scientific_boundary_flags"].values())


def test_two_independent_builds_are_byte_identical(tmp_path: Path) -> None:
    build_a = tmp_path / "build-a"
    build_b = tmp_path / "build-b"
    for output in (build_a, build_b):
        subprocess.run(
            [sys.executable, str(BUILDER), "--output-dir", str(output)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    paths_a = sorted(str(path.relative_to(build_a)) for path in build_a.rglob("*") if path.is_file())
    paths_b = sorted(str(path.relative_to(build_b)) for path in build_b.rglob("*") if path.is_file())
    assert paths_a == paths_b
    assert {relative: sha256(build_a / relative) for relative in paths_a} == {
        relative: sha256(build_b / relative) for relative in paths_b
    }
