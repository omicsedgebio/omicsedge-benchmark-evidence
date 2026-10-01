#!/usr/bin/env python3
"""Build deterministic static web-delivery files from Explorer v1 only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


WEB_BUNDLE_SCHEMA_VERSION = "1.0.0"
EXPECTED_EXPLORER_SCHEMA_VERSION = "1.0.0"
EXPECTED_COUNTS = {
    "variants": 4_278,
    "events": 11_553,
    "observations": 23_106,
    "unresolved_events": 60,
}
EXPECTED_IDENTITY_STATE_COUNTS = {
    "EXACT_NORMALIZED_ALLELE": 11_223,
    "NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY": 270,
    "UNRESOLVED": 60,
}
EXPECTED_SAMPLES = ["HG002", "HG003", "HG004"]
EXPECTED_TECHNOLOGIES = ["ILLUMINA", "ONT"]
EXPECTED_BOUNDARY_FLAGS = {
    "reliability_scoring_disabled": True,
    "trust_scoring_disabled": True,
    "consensus_generation_disabled": True,
    "technology_ranking_disabled": True,
    "caller_ranking_disabled": True,
    "representation_equivalence_disabled": True,
    "clinical_interpretation_disabled": True,
    "per_variant_genomic_context_disabled": True,
}
ALLOWED_IDENTITY_STATES = set(EXPECTED_IDENTITY_STATE_COUNTS)
MAX_JSON_BYTES = 20 * 1024 * 1024

CANONICAL_FILES = (
    "explorer_manifest.json",
    "variants.json",
    "events.json",
    "evidence.json",
    "unresolved_events.json",
    "checksums.sha256",
)
CANONICAL_CHECKSUM_SCOPE = {
    "explorer_manifest.json",
    "variants.json",
    "events.json",
    "evidence.json",
    "unresolved_events.json",
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


class WebBuildError(RuntimeError):
    """Raised when the frozen web-delivery contract cannot be satisfied."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WebBuildError(message)


def progress(message: str) -> None:
    print(f"[explorer-web-v1] {message}", file=sys.stderr, flush=True)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_bytes(value: Any) -> bytes:
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


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def parse_checksum_manifest(path: Path) -> dict[str, str]:
    require(path.is_file(), f"checksum manifest missing: {path}")
    result: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        require(len(parts) == 2, f"invalid checksum line {line_number}: {path}")
        digest, relative = parts
        relative = relative.lstrip("* ")
        require(
            len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
            f"invalid SHA-256 on line {line_number}: {path}",
        )
        pure = PurePosixPath(relative)
        require(not pure.is_absolute() and ".." not in pure.parts, f"unsafe checksum path: {relative}")
        require(relative not in result, f"duplicate checksum entry: {relative}")
        result[relative] = digest
    require(bool(result), f"empty checksum manifest: {path}")
    return result


def load_json(path: Path) -> Any:
    require(path.is_file(), f"canonical Explorer input missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def unique_index(rows: Iterable[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        require(isinstance(value, str) and value, f"{label} has missing {key}")
        require(value not in result, f"duplicate {label} {key}: {value}")
        result[value] = row
    return result


def shard_key(event_id: str) -> str:
    """The complete frozen shard-assignment algorithm."""
    return hashlib.sha256(event_id.encode("utf-8")).hexdigest()[:2]


def shard_path(event_id: str) -> str:
    return f"evidence/{shard_key(event_id)}.json"


def scan_forbidden_fields(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_FIELDS:
                found.add(key)
            found.update(scan_forbidden_fields(child))
    elif isinstance(value, list):
        for child in value:
            found.update(scan_forbidden_fields(child))
    return found


def scan_genomic_context(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in GENOMIC_CONTEXT_FIELDS:
                found.add(key)
            found.update(scan_genomic_context(child))
    elif isinstance(value, list):
        for child in value:
            found.update(scan_genomic_context(child))
    elif isinstance(value, str) and value in GENOMIC_CONTEXT_VALUES:
        found.add(value)
    return found


def validate_canonical_inputs(canonical_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate all canonical inputs before any web output is generated."""
    canonical_dir = canonical_dir.resolve()
    for name in CANONICAL_FILES:
        require((canonical_dir / name).is_file(), f"canonical Explorer input missing: {name}")

    detached = parse_checksum_manifest(canonical_dir / "checksums.sha256")
    require(
        set(detached) == CANONICAL_CHECKSUM_SCOPE,
        "canonical Explorer checksum manifest has an unexpected scope",
    )
    for relative, expected in detached.items():
        actual = sha256_file(canonical_dir / relative)
        require(actual == expected, f"canonical Explorer checksum mismatch: {relative}")

    all_input_hashes = {name: sha256_file(canonical_dir / name) for name in CANONICAL_FILES}
    manifest = load_json(canonical_dir / "explorer_manifest.json")
    require(isinstance(manifest, dict), "canonical Explorer manifest is not an object")
    counts = manifest.get("entity_counts")
    require(isinstance(counts, dict), "canonical Explorer entity counts are missing")
    for key, expected in EXPECTED_COUNTS.items():
        require(counts.get(key) == expected, f"canonical {key} count differs: {counts.get(key)} != {expected}")
    require(manifest.get("sample_values") == EXPECTED_SAMPLES, "canonical sample values differ")
    require(manifest.get("technology_values") == EXPECTED_TECHNOLOGIES, "canonical technology values differ")
    require(
        manifest.get("identity_state_counts") == EXPECTED_IDENTITY_STATE_COUNTS,
        "canonical identity-state counts differ",
    )
    require(
        manifest.get("scientific_boundary_flags") == EXPECTED_BOUNDARY_FLAGS,
        "canonical scientific-boundary flags differ",
    )
    require(
        manifest.get("explorer_schema_version") == EXPECTED_EXPLORER_SCHEMA_VERSION,
        "canonical Explorer schema version differs",
    )
    progress("canonical Explorer checksums, counts, and boundaries verified")
    return manifest, all_input_hashes


def load_canonical_model(canonical_dir: Path) -> dict[str, Any]:
    model = {
        "variants": load_json(canonical_dir / "variants.json"),
        "events": load_json(canonical_dir / "events.json"),
        "evidence": load_json(canonical_dir / "evidence.json"),
        "unresolved_events": load_json(canonical_dir / "unresolved_events.json"),
    }
    for key, value in model.items():
        require(isinstance(value, list), f"canonical {key} is not a JSON array")
    require(len(model["variants"]) == EXPECTED_COUNTS["variants"], "canonical variants.json count differs")
    require(len(model["events"]) == EXPECTED_COUNTS["events"], "canonical events.json count differs")
    require(len(model["evidence"]) == EXPECTED_COUNTS["observations"], "canonical evidence.json count differs")
    require(
        len(model["unresolved_events"]) == EXPECTED_COUNTS["unresolved_events"],
        "canonical unresolved_events.json count differs",
    )
    progress("canonical Explorer records loaded")
    return model


def build_delivery_model(canonical: dict[str, Any]) -> dict[str, Any]:
    variants = unique_index(canonical["variants"], "variant_id", "canonical VARIANT")
    events = unique_index(canonical["events"], "event_id", "canonical EVENT")
    observations = unique_index(canonical["evidence"], "observation_id", "canonical OBSERVATION")
    unresolved = unique_index(canonical["unresolved_events"], "event_id", "canonical unresolved EVENT")

    require(set(unresolved) <= set(events), "canonical unresolved event is absent from events.json")
    require(
        set(unresolved)
        == {event_id for event_id, row in events.items() if row["identity_state"] == "UNRESOLVED"},
        "canonical unresolved_events.json does not exactly match UNRESOLVED events",
    )

    observations_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in observations.values():
        event_id = observation.get("event_id")
        require(event_id in events, f"canonical observation references absent event: {event_id}")
        observations_by_event[event_id].append(observation)
    require(set(observations_by_event) == set(events), "canonical EVENT without evidence or evidence without EVENT")

    search_records: list[dict[str, Any]] = []
    shard_index: dict[str, str] = {}
    shard_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_raw_decisions: dict[str, list[str]] = {}
    source_raw_variant_types: dict[str, list[str]] = {}

    for event_id in sorted(events):
        event = events[event_id]
        event_evidence = observations_by_event[event_id]
        require(
            len(event_evidence) == event.get("observation_count"),
            f"canonical event observation_count mismatch: {event_id}",
        )
        samples = {row.get("sample_id") for row in event_evidence}
        technologies = {row.get("technology") for row in event_evidence}
        require(len(samples) == 1 and None not in samples, f"event evidence disagrees on sample_id: {event_id}")
        require(
            len(technologies) == 1 and None not in technologies,
            f"event evidence disagrees on technology: {event_id}",
        )

        identity_state = event.get("identity_state")
        variant_id = event.get("variant_id")
        require(identity_state in ALLOWED_IDENTITY_STATES, f"unsupported identity state: {identity_state}")
        if identity_state == "EXACT_NORMALIZED_ALLELE":
            require(isinstance(variant_id, str) and variant_id in variants, f"exact event has absent variant: {event_id}")
            variant = variants[variant_id]
            normalized_fields = {
                "normalized_start_0based": variant["normalized_start_0based"],
                "normalized_end_0based": variant["normalized_end_0based"],
                "normalized_ref": variant["normalized_ref"],
                "normalized_alt": variant["normalized_alt"],
            }
        else:
            require(variant_id is None, f"non-exact event has a variant_id: {event_id}")
            if identity_state == "UNRESOLVED":
                require(event_id in unresolved, f"UNRESOLVED event absent from frozen unresolved set: {event_id}")
            if identity_state == "NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY":
                require(event_id not in unresolved, f"NOT_EVALUATED event was relabeled unresolved: {event_id}")
            normalized_fields = {
                "normalized_start_0based": None,
                "normalized_end_0based": None,
                "normalized_ref": None,
                "normalized_alt": None,
            }

        raw_decisions = sorted({row["raw_decision"] for row in event_evidence})
        raw_variant_types = sorted(
            {row["raw_variant_type"] for row in event_evidence if row.get("raw_variant_type") is not None}
        )
        source_raw_decisions[event_id] = raw_decisions
        source_raw_variant_types[event_id] = raw_variant_types
        relative_shard = shard_path(event_id)
        shard_index[event_id] = relative_shard
        shard_records[relative_shard].extend(event_evidence)
        search_records.append(
            {
                "event_id": event_id,
                "evidence_shard": relative_shard,
                "variant_id": variant_id,
                "identity_state": identity_state,
                "phase_origin": event["phase_origin"],
                "assembly": event["assembly"],
                "contig": event["contig"],
                "start_0based": event["start_0based"],
                "end_0based": event["end_0based"],
                "sample_id": next(iter(samples)),
                "technology": next(iter(technologies)),
                "raw_decisions": raw_decisions,
                "raw_variant_types": raw_variant_types,
                "observation_count": len(event_evidence),
                **normalized_fields,
            }
        )

    for relative, rows in shard_records.items():
        rows.sort(key=lambda row: (row["event_id"], row["observation_id"]))
        require(rows, f"empty evidence shard would be generated: {relative}")

    require(len(search_records) == EXPECTED_COUNTS["events"], "search index event count differs")
    require(len(shard_index) == EXPECTED_COUNTS["events"], "shard index event count differs")
    require(len(shard_records) <= 256, "more than 256 evidence shards would be generated")
    require(set(shard_index) == set(events), "shard index event set differs from canonical events")

    sharded_observation_ids = [
        row["observation_id"] for relative in sorted(shard_records) for row in shard_records[relative]
    ]
    require(
        len(sharded_observation_ids) == len(set(sharded_observation_ids)) == EXPECTED_COUNTS["observations"],
        "sharded observations are duplicated or missing",
    )
    require(set(sharded_observation_ids) == set(observations), "sharded observation IDs differ from canonical evidence")
    for event_id, rows in observations_by_event.items():
        paths = {shard_path(row["event_id"]) for row in rows}
        require(paths == {shard_index[event_id]}, f"event observations span multiple shards: {event_id}")

    search_by_event = unique_index(search_records, "event_id", "search record")
    require(
        {event_id: row["raw_decisions"] for event_id, row in search_by_event.items()} == source_raw_decisions,
        "search raw decisions differ from canonical evidence",
    )
    require(
        {event_id: row["raw_variant_types"] for event_id, row in search_by_event.items()}
        == source_raw_variant_types,
        "search raw variant types differ from canonical evidence",
    )

    identity_counts = dict(sorted(Counter(row["identity_state"] for row in search_records).items()))
    require(identity_counts == EXPECTED_IDENTITY_STATE_COUNTS, "web identity-state counts differ")
    samples = sorted({row["sample_id"] for row in search_records})
    technologies = sorted({row["technology"] for row in search_records})
    require(samples == EXPECTED_SAMPLES, "web sample values differ")
    require(technologies == EXPECTED_TECHNOLOGIES, "web technology values differ")

    generated = {
        "search_index": search_records,
        "shard_index": dict(sorted(shard_index.items())),
        "shard_records": dict(sorted(shard_records.items())),
    }
    forbidden = scan_forbidden_fields(generated)
    require(not forbidden, f"forbidden fields would be generated: {sorted(forbidden)}")
    context = scan_genomic_context(generated)
    require(not context, f"genomic-context fields or classifications would be generated: {sorted(context)}")
    progress("search records and deterministic shard assignments validated")
    return {
        **generated,
        "identity_state_counts": identity_counts,
        "sample_values": samples,
        "technology_values": technologies,
    }


def make_manifest(
    canonical_manifest: dict[str, Any],
    canonical_input_hashes: dict[str, str],
    delivery: dict[str, Any],
    search_index_sha256: str,
    shard_index_sha256: str,
    evidence_shard_sha256: dict[str, str],
    shard_sizes: list[int],
) -> dict[str, Any]:
    return {
        "web_bundle_schema_version": WEB_BUNDLE_SCHEMA_VERSION,
        "project": canonical_manifest["project"],
        "scientific_release": canonical_manifest["scientific_release"],
        "zenodo_doi": canonical_manifest["zenodo_doi"],
        "canonical_explorer_schema_version": canonical_manifest["explorer_schema_version"],
        "canonical_explorer_manifest_sha256": canonical_input_hashes["explorer_manifest.json"],
        "canonical_input_file_sha256": dict(sorted(canonical_input_hashes.items())),
        "event_count": EXPECTED_COUNTS["events"],
        "observation_count": EXPECTED_COUNTS["observations"],
        "variant_count": EXPECTED_COUNTS["variants"],
        "identity_state_counts": delivery["identity_state_counts"],
        "sample_values": delivery["sample_values"],
        "technology_values": delivery["technology_values"],
        "shard_count": len(evidence_shard_sha256),
        "maximum_shard_byte_size": max(shard_sizes),
        "search_index_sha256": search_index_sha256,
        "shard_index_sha256": shard_index_sha256,
        "evidence_shard_sha256": dict(sorted(evidence_shard_sha256.items())),
        "scientific_boundary_flags": dict(EXPECTED_BOUNDARY_FLAGS),
    }


def verify_generated_checksums(output_dir: Path) -> dict[str, str]:
    checksums = parse_checksum_manifest(output_dir / "checksums.sha256")
    expected_paths = {
        "manifest.json",
        "search_index.json",
        "shard_index.json",
        *(str(path.relative_to(output_dir)) for path in (output_dir / "evidence").glob("*.json")),
    }
    require(set(checksums) == expected_paths, "generated checksum manifest scope differs")
    for relative, expected in checksums.items():
        path = output_dir / relative
        require(path.is_file(), f"checksummed web output is missing: {relative}")
        require(sha256_file(path) == expected, f"generated checksum mismatch: {relative}")
    return checksums


def materialize_bundle(
    staging_dir: Path,
    canonical_manifest: dict[str, Any],
    canonical_input_hashes: dict[str, str],
    delivery: dict[str, Any],
) -> dict[str, Any]:
    evidence_dir = staging_dir / "evidence"
    evidence_dir.mkdir(parents=True)

    search_bytes = stable_json_bytes(delivery["search_index"])
    shard_index_bytes = stable_json_bytes(delivery["shard_index"])
    require(search_bytes == stable_json_bytes(list(delivery["search_index"])), "search serialization differs")
    require(shard_index_bytes == stable_json_bytes(dict(delivery["shard_index"])), "shard-index serialization differs")
    require(len(search_bytes) <= MAX_JSON_BYTES, "search_index.json exceeds 20 MiB")
    require(len(shard_index_bytes) <= MAX_JSON_BYTES, "shard_index.json exceeds 20 MiB")
    write_bytes(staging_dir / "search_index.json", search_bytes)
    write_bytes(staging_dir / "shard_index.json", shard_index_bytes)

    evidence_hashes: dict[str, str] = {}
    shard_sizes: list[int] = []
    for relative, rows in delivery["shard_records"].items():
        content = stable_json_bytes(rows)
        require(content == stable_json_bytes(list(rows)), f"shard serialization differs: {relative}")
        require(len(content) <= MAX_JSON_BYTES, f"evidence shard exceeds 20 MiB: {relative}")
        path = staging_dir / relative
        write_bytes(path, content)
        evidence_hashes[relative] = sha256_file(path)
        shard_sizes.append(len(content))

    manifest = make_manifest(
        canonical_manifest,
        canonical_input_hashes,
        delivery,
        sha256_file(staging_dir / "search_index.json"),
        sha256_file(staging_dir / "shard_index.json"),
        evidence_hashes,
        shard_sizes,
    )
    manifest_bytes = stable_json_bytes(manifest)
    require(manifest_bytes == stable_json_bytes(dict(manifest)), "manifest serialization differs")
    require(len(manifest_bytes) <= MAX_JSON_BYTES, "manifest.json exceeds 20 MiB")
    write_bytes(staging_dir / "manifest.json", manifest_bytes)

    json_paths = sorted(
        [staging_dir / "manifest.json", staging_dir / "search_index.json", staging_dir / "shard_index.json"]
        + list(evidence_dir.glob("*.json")),
        key=lambda path: str(path.relative_to(staging_dir)),
    )
    for path in json_paths:
        require(path.stat().st_size <= MAX_JSON_BYTES, f"JSON output exceeds 20 MiB: {path.name}")
    checksum_lines = [
        f"{sha256_file(path)}  {path.relative_to(staging_dir)}" for path in json_paths
    ]
    write_bytes(staging_dir / "checksums.sha256", ("\n".join(checksum_lines) + "\n").encode("utf-8"))
    verify_generated_checksums(staging_dir)
    progress("web JSON files materialized within the 20 MiB limit")
    return {
        "manifest": manifest,
        "relative_paths": [str(path.relative_to(staging_dir)) for path in json_paths]
        + ["checksums.sha256"],
        "output_sha256": {
            str(path.relative_to(staging_dir)): sha256_file(path)
            for path in [*json_paths, staging_dir / "checksums.sha256"]
        },
        "shard_sizes": sorted(shard_sizes),
    }


def publish_staging(staging_dir: Path, output_dir: Path) -> None:
    output_dir = output_dir.resolve()
    backup = output_dir.with_name(f".{output_dir.name}.backup-{os.getpid()}")
    require(not backup.exists(), f"stale output backup exists: {backup}")
    if output_dir.exists():
        os.replace(output_dir, backup)
    try:
        os.replace(staging_dir, output_dir)
    except Exception:
        if backup.exists() and not output_dir.exists():
            os.replace(backup, output_dir)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def build_web_bundle(canonical_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Build one web bundle using only the canonical Explorer v1 export."""
    canonical_dir = canonical_dir.resolve()
    output_dir = output_dir.resolve()

    # No output or staging directory is created before these validations pass.
    canonical_manifest, canonical_hashes = validate_canonical_inputs(canonical_dir)
    canonical_model = load_canonical_model(canonical_dir)
    delivery = build_delivery_model(canonical_model)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.staging-", dir=output_dir.parent)
    )
    try:
        result = materialize_bundle(staging_dir, canonical_manifest, canonical_hashes, delivery)
        publish_staging(staging_dir, output_dir)
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        raise

    shard_sizes = result["shard_sizes"]
    return {
        "output_dir": str(output_dir),
        "event_count": len(delivery["search_index"]),
        "observation_count": sum(len(rows) for rows in delivery["shard_records"].values()),
        "shard_count": len(shard_sizes),
        "minimum_shard_byte_size": min(shard_sizes),
        "median_shard_byte_size": statistics.median(shard_sizes),
        "maximum_shard_byte_size": max(shard_sizes),
        "identity_state_counts": delivery["identity_state_counts"],
        "output_sha256": result["output_sha256"],
    }


def parse_args() -> argparse.Namespace:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--canonical-dir",
        type=Path,
        default=repository_root / "results/explorer_v1",
        help="validated canonical Explorer v1 directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "results/explorer_web_v1",
        help="web-delivery output directory",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = build_web_bundle(args.canonical_dir, args.output_dir)
    except (WebBuildError, FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        print(f"EXPLORER_WEB_V1_STOP: {exc}")
        return 1
    print(
        json.dumps(
            {
                key: summary[key]
                for key in (
                    "output_dir",
                    "event_count",
                    "observation_count",
                    "shard_count",
                    "minimum_shard_byte_size",
                    "median_shard_byte_size",
                    "maximum_shard_byte_size",
                    "identity_state_counts",
                )
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
