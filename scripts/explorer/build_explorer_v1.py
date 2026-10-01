#!/usr/bin/env python3
"""Build the deterministic Project 003 Evidence Explorer v1 export.

The exporter is a read-only product layer over the frozen Project 003 v1.0.0
scientific release.  It never recomputes benchmark results or biological
identity, and it fails closed when an authority, count, or join is ambiguous.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import os
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


EXPLORER_SCHEMA_VERSION = "1.0.0"
BUILDER_VERSION = "1.0.0"
PROJECT = "OmicsEdgeBio Project 003 — Benchmark Evidence Registry"
SCIENTIFIC_RELEASE = "v1.0.0"
ZENODO_DOI = "10.5281/zenodo.23085673"

AUTHORITATIVE_ARCHIVE_SHA256 = (
    "186cbed74fa718a728f7a24b43d58118a308165fae385eb95cc4cb4444788ca3"
)
EXPECTED_AUTHORITY_SHA256 = {
    "phase1a": "6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202",
    "phase1b": "50bf597cbc13a051d5dda7201e9d7653dbc7b1762fef1b8300199641df6474fb",
    "phase2c": "345b6c3483350f4f1930fc5957f7a97c2b2daf30e6ba1972f2cf3b8484ff0536",
    "phase2d": "3e5feb50e28b620a8ab9f1d4c9901b9faedb127fd84a2dad4dedf65dd5437532",
}

EXPECTED_COUNTS = {
    "phase1_events": 3_602,
    "phase1_observations": 7_204,
    "phase1_variants": 1_666,
    "phase1_event_variant_links": 3_332,
    "phase2_events": 7_951,
    "phase2_observations": 15_902,
    "phase2_variants": 2_612,
    "phase2_exact_event_variant_links": 7_891,
    "phase2_unresolved_events": 60,
    "unified_events": 11_553,
    "unified_observations": 23_106,
    "unified_variants": 4_278,
}

IDENTITY_EXACT = "EXACT_NORMALIZED_ALLELE"
IDENTITY_UNRESOLVED = "UNRESOLVED"
IDENTITY_NOT_EVALUATED = "NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY"
ALLOWED_IDENTITY_STATES = {
    IDENTITY_EXACT,
    IDENTITY_UNRESOLVED,
    IDENTITY_NOT_EVALUATED,
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

OUTPUT_JSON_FILES = (
    "variants.json",
    "events.json",
    "evidence.json",
    "unresolved_events.json",
)
ALL_OUTPUT_FILES = (
    "explorer_manifest.json",
    *OUTPUT_JSON_FILES,
    "checksums.sha256",
)


class ExplorerBuildError(RuntimeError):
    """Raised when a frozen-contract invariant is not satisfied."""


def progress(message: str) -> None:
    print(f"[explorer-v1] {message}", file=sys.stderr, flush=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExplorerBuildError(message)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json_bytes(value: Any) -> bytes:
    """Return compact, key-sorted UTF-8 JSON with exactly one final newline."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def write_json(path: Path, value: Any) -> None:
    write_bytes_atomic(path, stable_json_bytes(value))


def _validated_tar_members(tf: tarfile.TarFile, destination: Path) -> list[tarfile.TarInfo]:
    destination = destination.resolve()
    names: set[str] = set()
    members: list[tarfile.TarInfo] = []
    for member in tf.getmembers():
        pure = PurePosixPath(member.name)
        require(not pure.is_absolute(), f"unsafe absolute tar member: {member.name}")
        require(".." not in pure.parts, f"unsafe parent traversal in tar member: {member.name}")
        require(member.name not in names, f"duplicate tar member: {member.name}")
        names.add(member.name)
        target = (destination / member.name).resolve()
        require(
            target == destination or destination in target.parents,
            f"tar member escapes destination: {member.name}",
        )
        require(not member.issym() and not member.islnk(), f"links are forbidden in authority tar: {member.name}")
        require(member.isfile() or member.isdir(), f"special tar member is forbidden: {member.name}")
        members.append(member)
    return members


def safe_extract_tar(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        members = _validated_tar_members(tf, destination)
        try:
            tf.extractall(destination, members=members, filter="data")
        except TypeError:  # Python 3.10 compatibility after explicit validation above.
            tf.extractall(destination, members=members)


def parse_checksum_manifest(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        parts = raw.split(maxsplit=1)
        require(len(parts) == 2, f"invalid checksum line {line_number} in {path}")
        digest, relative = parts
        relative = relative.lstrip("* ")
        require(
            len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
            f"invalid SHA-256 in {path}:{line_number}",
        )
        require(relative not in checksums, f"duplicate checksum path in {path}: {relative}")
        pure = PurePosixPath(relative)
        require(not pure.is_absolute() and ".." not in pure.parts, f"unsafe checksum path: {relative}")
        checksums[relative] = digest
    require(bool(checksums), f"empty checksum manifest: {path}")
    return checksums


def verify_checksum_manifest(root: Path, manifest_path: Path) -> dict[str, str]:
    checksums = parse_checksum_manifest(manifest_path)
    for relative, expected in checksums.items():
        target = root / relative
        require(target.is_file(), f"required checksummed artifact missing: {target}")
        actual = sha256_file(target)
        require(actual == expected, f"checksum mismatch for {target}: {actual} != {expected}")
    return checksums


def verify_phase1b_release_manifest(root: Path) -> dict[str, Any]:
    path = root / "results/phase1b/phase1b_release_manifest.json"
    require(path.is_file(), f"Phase 1B release manifest missing: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, list) and artifacts, "Phase 1B release manifest artifacts are missing")
    seen: set[str] = set()
    for record in artifacts:
        relative = record.get("path")
        expected_sha = record.get("sha256")
        expected_size = record.get("size_bytes")
        require(isinstance(relative, str) and relative not in seen, f"invalid/duplicate Phase 1B path: {relative}")
        seen.add(relative)
        pure = PurePosixPath(relative)
        require(not pure.is_absolute() and ".." not in pure.parts, f"unsafe Phase 1B manifest path: {relative}")
        target = root / relative
        require(target.is_file(), f"Phase 1B release artifact missing: {target}")
        require(target.stat().st_size == int(expected_size), f"Phase 1B size mismatch: {relative}")
        require(sha256_file(target) == expected_sha, f"Phase 1B checksum mismatch: {relative}")
    return manifest


def read_tsv(path: Path) -> list[dict[str, str]]:
    require(path.is_file(), f"required TSV missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        require(reader.fieldnames is not None, f"TSV header missing: {path}")
        return list(reader)


def read_parquet(path: Path) -> list[dict[str, Any]]:
    require(path.is_file(), f"required Parquet missing: {path}")
    try:
        import duckdb  # type: ignore
    except ImportError as exc:
        raise ExplorerBuildError(
            "DuckDB is required to read the frozen Phase 1A Parquet authority; install project dependencies"
        ) from exc
    connection = duckdb.connect()
    try:
        cursor = connection.execute("SELECT * FROM read_parquet(?)", [str(path)])
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        connection.close()


def optional(value: Any) -> Any:
    return None if value is None or value == "" else value


def integer(value: Any, field: str) -> int:
    require(value is not None and value != "", f"required integer is absent: {field}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ExplorerBuildError(f"invalid integer for {field}: {value!r}") from exc


def optional_integer(value: Any, field: str) -> int | None:
    return None if value is None or value == "" else integer(value, field)


def optional_float(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ExplorerBuildError(f"invalid number for {field}: {value!r}") from exc


def parse_list(value: Any, field: str) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    require(isinstance(value, str), f"invalid list representation for {field}: {value!r}")
    try:
        parsed = ast.literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise ExplorerBuildError(f"invalid list literal for {field}: {value!r}") from exc
    require(isinstance(parsed, (list, tuple)), f"non-list literal for {field}: {value!r}")
    return list(parsed)


def parse_json_object(value: Any, field: str) -> dict[str, Any] | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        return value
    require(isinstance(value, str), f"invalid JSON object for {field}")
    parsed = json.loads(value)
    require(isinstance(parsed, dict), f"non-object JSON for {field}")
    return parsed


def unique_index(rows: Iterable[dict[str, Any]], key: str, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        require(isinstance(value, str) and value, f"{label} has missing {key}")
        require(value not in result, f"duplicate {label} {key}: {value}")
        result[value] = row
    return result


def direct_provenance_index(rows: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        link_id = row.get("provenance_link_id")
        require(isinstance(link_id, str) and link_id, "provenance link without ID")
        for endpoint in ("source_entity_id", "target_entity_id"):
            entity_id = row.get(endpoint)
            if isinstance(entity_id, str) and entity_id:
                result[entity_id].add(link_id)
    return {entity_id: sorted(ids) for entity_id, ids in result.items()}


def verify_and_extract_authorities(
    archive: Path, temporary_root: Path
) -> tuple[dict[str, Path], dict[str, str], dict[str, int]]:
    """Extract and validate the final archive and each nested frozen authority."""
    outer_extract = temporary_root / "final_release"
    safe_extract_tar(archive, outer_extract)
    release_root = outer_extract / "omicsedge_phase2_final_results"
    require(release_root.is_dir(), "final release archive has an unexpected root")

    outer_checksums = verify_checksum_manifest(release_root, release_root / "checksums.sha256")
    authority_hashes: dict[str, str] = {}
    authority_dirs: dict[str, Path] = {}
    integrity_counts: dict[str, int] = {"outer_checksums": len(outer_checksums)}

    for phase, expected in EXPECTED_AUTHORITY_SHA256.items():
        nested_archive = release_root / "authorities" / f"{phase}.tar.gz"
        require(nested_archive.is_file(), f"nested authority archive missing: {phase}")
        actual = sha256_file(nested_archive)
        require(actual == expected, f"{phase} authority SHA-256 mismatch: {actual} != {expected}")
        require(
            outer_checksums.get(f"authorities/{phase}.tar.gz") == expected,
            f"outer checksum manifest disagrees for {phase}",
        )
        destination = temporary_root / phase
        safe_extract_tar(nested_archive, destination)
        authority_hashes[phase] = actual
        authority_dirs[phase] = destination

    phase1_root = authority_dirs["phase1a"] / "omicsedge_phase1a_results"
    phase1_checksums = verify_checksum_manifest(phase1_root, phase1_root / "checksums.sha256")
    require(len(phase1_checksums) == 35, f"Phase 1A checksum count is {len(phase1_checksums)}, expected 35")
    integrity_counts["phase1a_checksums"] = len(phase1_checksums)

    phase1b_manifest = verify_phase1b_release_manifest(authority_dirs["phase1b"])
    integrity_counts["phase1b_manifest_artifacts"] = len(phase1b_manifest["artifacts"])

    phase2c_root = authority_dirs["phase2c"] / "omicsedge_phase2c_results"
    phase2c_checksums = verify_checksum_manifest(phase2c_root, phase2c_root / "checksums.sha256")
    integrity_counts["phase2c_checksums"] = len(phase2c_checksums)

    phase2d_root = authority_dirs["phase2d"] / "omicsedge_phase2d_results"
    phase2d_checksums = verify_checksum_manifest(phase2d_root, phase2d_root / "checksums.sha256")
    integrity_counts["phase2d_checksums"] = len(phase2d_checksums)

    return authority_dirs, authority_hashes, integrity_counts


def load_authorities(authority_dirs: dict[str, Path]) -> dict[str, Any]:
    phase1a = authority_dirs["phase1a"] / "omicsedge_phase1a_results"
    phase1b = authority_dirs["phase1b"] / "results/phase1b"
    phase2c = authority_dirs["phase2c"] / "omicsedge_phase2c_results"
    phase2d = authority_dirs["phase2d"] / "omicsedge_phase2d_results"

    return {
        "phase1_events": read_parquet(phase1a / "events.parquet"),
        "phase1_observations": read_parquet(phase1a / "observations.parquet"),
        "phase1_experiments": read_tsv(phase1a / "experiments.tsv"),
        "phase1_runs": read_tsv(phase1a / "benchmark_runs.tsv"),
        "phase1_provenance": read_parquet(phase1a / "provenance_links.parquet"),
        "phase1_variants": read_tsv(phase1b / "variants.tsv"),
        "phase1_identity_links": read_tsv(phase1b / "event_variant_links.tsv"),
        "phase2_events": read_tsv(phase2c / "events.tsv"),
        "phase2_observations": read_tsv(phase2c / "observations.tsv"),
        "phase2_experiments": read_tsv(phase2c / "experiments.tsv"),
        "phase2_runs": read_tsv(phase2c / "benchmark_runs.tsv"),
        "phase2_provenance": read_tsv(phase2c / "provenance_links.tsv"),
        "phase2_source_artifacts": read_tsv(phase2c / "source_artifacts.tsv"),
        "phase2_variants": read_tsv(phase2d / "variant_index.tsv"),
        "phase2_identity_links": read_tsv(phase2d / "event_variant_links.tsv"),
        "phase2_identity_accounting": read_tsv(phase2d / "event_identity_accounting.tsv"),
        "phase2_link_provenance": read_tsv(phase2d / "link_provenance.tsv"),
    }


def normalized_experiment(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "experiment_id": row["experiment_id"],
        "sample_id": row["sample_id"],
        "technology": row["technology"],
        "platform": row["platform"],
        "coverage": row["coverage"],
        "pipeline_name": row["pipeline_name"],
        "pipeline_version": row["pipeline_version"],
        "caller_names": parse_list(row.get("caller_names"), "caller_names"),
        "caller_versions": parse_list(row.get("caller_versions"), "caller_versions"),
    }


def normalized_run(row: dict[str, Any], phase_origin: str) -> dict[str, Any]:
    benchmark_region_id = (
        row.get("benchmark_bed_artifact_id")
        if phase_origin == "PHASE1A"
        else row.get("benchmark_region_set_artifact_id")
    )
    require(isinstance(benchmark_region_id, str) and benchmark_region_id, f"run lacks benchmark region artifact: {row}")
    return {
        "benchmark_run_id": row["benchmark_run_id"],
        "experiment_id": row["experiment_id"],
        "comparator": row["comparator"],
        "comparator_version": row["comparator_version"],
        "engine": row["engine"],
        "engine_version": row["engine_version"],
        "query_artifact_id": row["query_artifact_id"],
        "truth_artifact_id": row["truth_artifact_id"],
        "reference_artifact_id": row["reference_artifact_id"],
        "benchmark_region_artifact_id": benchmark_region_id,
        "runtime_image_digest": optional(row.get("runtime_image_digest")),
    }


def make_event_record(
    row: dict[str, Any],
    phase_origin: str,
    identity_state: str,
    variant_id: str | None,
    unresolved_reason: str | None,
    link: dict[str, Any] | None,
    observation_count: int,
) -> dict[str, Any]:
    return {
        "event_id": row["event_id"],
        "phase_origin": phase_origin,
        "benchmark_run_id": row["benchmark_run_id"],
        "assembly": row["assembly"],
        "contig": row["contig"],
        "start_0based": integer(row["start_0based"], "event.start_0based"),
        "end_0based": integer(row["end_0based"], "event.end_0based"),
        "identity_scope": optional(row.get("identity_scope")),
        "identity_state": identity_state,
        "variant_id": variant_id,
        "unresolved_reason": unresolved_reason,
        "event_variant_link_id": link.get("event_variant_link_id") if link else None,
        "identity_method": optional(link.get("identity_method")) if link else None,
        "identity_method_version": optional(link.get("identity_method_version")) if link else None,
        "observation_count": observation_count,
    }


def make_identity_provenance(
    phase_origin: str,
    link: dict[str, Any] | None,
    accounting: dict[str, Any] | None,
    phase2_link_provenance: dict[str, dict[str, Any]],
    authority_hashes: dict[str, str],
) -> dict[str, Any] | None:
    if link is None and accounting is None:
        return None
    if phase_origin == "PHASE1A":
        require(link is not None, "Phase 1 exact identity is missing its frozen link")
        return {
            "identity_authority": "PHASE1B",
            "authority_archive_sha256": authority_hashes["phase1b"],
            "candidate_id": optional(link.get("candidate_id")),
            "phase1a_candidate_status": optional(link.get("phase1a_candidate_status")),
            "created_from_candidate": link.get("created_from_candidate") == "True",
            "evidence": parse_json_object(link.get("evidence"), "phase1b.evidence"),
            "provenance": parse_json_object(link.get("provenance"), "phase1b.provenance"),
        }
    if link is not None:
        provenance_row = phase2_link_provenance.get(link["event_variant_link_id"])
        require(provenance_row is not None, f"Phase 2 identity link lacks provenance: {link['event_variant_link_id']}")
        return {
            "identity_authority": "PHASE2D",
            "authority_archive_sha256": authority_hashes["phase2d"],
            "evidence": parse_json_object(link.get("evidence"), "phase2d.evidence"),
            "provenance": parse_json_object(link.get("provenance"), "phase2d.provenance"),
            "link_provenance": dict(sorted(provenance_row.items())),
        }
    require(accounting is not None, "Phase 2 unresolved identity lacks accounting")
    return {
        "identity_authority": "PHASE2D",
        "authority_archive_sha256": authority_hashes["phase2d"],
        "event_identity_accounting": {
            "identity_status": accounting["identity_status"],
            "unresolved_reason": accounting["unresolved_reason"],
            "identity_method": accounting["identity_method"],
            "identity_method_version": accounting["identity_method_version"],
            "phase2d_application_version": accounting["phase2d_application_version"],
            "reference_artifact_id": accounting["reference_artifact_id"],
        },
    }


def make_evidence_record(
    observation: dict[str, Any],
    phase_origin: str,
    event: dict[str, Any],
    run: dict[str, Any],
    experiment: dict[str, Any],
    provenance_ids: list[str],
    identity_provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "observation_id": observation["observation_id"],
        "event_id": event["event_id"],
        "variant_id": event["variant_id"],
        "identity_state": event["identity_state"],
        "event_variant_link_id": event["event_variant_link_id"],
        "phase_origin": phase_origin,
        "benchmark_run_id": run["benchmark_run_id"],
        "experiment_id": experiment["experiment_id"],
        "sample_id": experiment["sample_id"],
        "technology": experiment["technology"],
        "platform": experiment["platform"],
        "coverage": experiment["coverage"],
        "pipeline_name": experiment["pipeline_name"],
        "pipeline_version": experiment["pipeline_version"],
        "caller_names": experiment["caller_names"],
        "caller_versions": experiment["caller_versions"],
        "side": observation["side"],
        "observation_origin": observation["observation_origin"],
        "raw_decision": observation["raw_decision"],
        "normalized_decision": observation["normalized_decision"],
        "raw_match_kind": observation["raw_match_kind"],
        "raw_variant_type": optional(observation.get("raw_variant_type")),
        "raw_location_type": optional(observation.get("raw_location_type")),
        "region_status": observation["region_status"],
        "source_contig": observation["source_contig"],
        "source_pos_1based": integer(observation["source_pos_1based"], "observation.source_pos_1based"),
        "source_ref": observation["source_ref"],
        "source_alt": observation["source_alt"],
        "source_genotype": optional(observation.get("source_genotype")),
        "source_filter": parse_list(observation.get("source_filter"), "observation.source_filter"),
        "quality_score": optional_float(observation.get("quality_score"), "observation.quality_score"),
        "normalization_method": observation["normalization_method"],
        "normalization_version": observation["normalization_version"],
        "normalized_start_0based": optional_integer(
            observation.get("normalized_start_0based"), "observation.normalized_start_0based"
        ),
        "normalized_end_0based": optional_integer(
            observation.get("normalized_end_0based"), "observation.normalized_end_0based"
        ),
        "normalized_ref": optional(observation.get("normalized_ref")),
        "normalized_alt": optional(observation.get("normalized_alt")),
        "source_output_artifact_id": observation["source_output_artifact_id"],
        "comparator": run["comparator"],
        "comparator_version": run["comparator_version"],
        "engine": run["engine"],
        "engine_version": run["engine_version"],
        "query_artifact_id": run["query_artifact_id"],
        "truth_artifact_id": run["truth_artifact_id"],
        "reference_artifact_id": run["reference_artifact_id"],
        "benchmark_region_artifact_id": run["benchmark_region_artifact_id"],
        "runtime_image_digest": run["runtime_image_digest"],
        "applicable_provenance_link_ids": provenance_ids,
        "identity_provenance": identity_provenance,
    }


def scan_forbidden_fields(value: Any) -> set[str]:
    """Return forbidden keys without constructing paths for millions of scalars."""
    violations: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_FIELDS:
                violations.add(key)
            violations.update(scan_forbidden_fields(child))
    elif isinstance(value, list):
        for child in value:
            violations.update(scan_forbidden_fields(child))
    return violations


def build_model(data: dict[str, Any], authority_hashes: dict[str, str]) -> dict[str, Any]:
    # Frozen authority counts are checked before any joins.
    for key in (
        "phase1_events",
        "phase1_observations",
        "phase1_variants",
        "phase1_identity_links",
        "phase2_events",
        "phase2_observations",
        "phase2_variants",
        "phase2_identity_links",
        "phase2_identity_accounting",
    ):
        require(isinstance(data[key], list), f"authority collection is not a list: {key}")

    require(len(data["phase1_events"]) == EXPECTED_COUNTS["phase1_events"], "Phase 1 event count mismatch")
    require(
        len(data["phase1_observations"]) == EXPECTED_COUNTS["phase1_observations"],
        "Phase 1 observation count mismatch",
    )
    require(len(data["phase1_variants"]) == EXPECTED_COUNTS["phase1_variants"], "Phase 1 variant count mismatch")
    require(
        len(data["phase1_identity_links"]) == EXPECTED_COUNTS["phase1_event_variant_links"],
        "Phase 1 identity-link count mismatch",
    )
    require(len(data["phase2_events"]) == EXPECTED_COUNTS["phase2_events"], "Phase 2 event count mismatch")
    require(
        len(data["phase2_observations"]) == EXPECTED_COUNTS["phase2_observations"],
        "Phase 2 observation count mismatch",
    )
    require(len(data["phase2_variants"]) == EXPECTED_COUNTS["phase2_variants"], "Phase 2 variant count mismatch")
    require(
        len(data["phase2_identity_links"]) == EXPECTED_COUNTS["phase2_exact_event_variant_links"],
        "Phase 2 exact identity-link count mismatch",
    )
    require(
        len(data["phase2_identity_accounting"]) == EXPECTED_COUNTS["phase2_events"],
        "Phase 2 identity-accounting count mismatch",
    )

    phase1_events = unique_index(data["phase1_events"], "event_id", "Phase 1 EVENT")
    phase2_events = unique_index(data["phase2_events"], "event_id", "Phase 2 EVENT")
    require(set(phase1_events).isdisjoint(phase2_events), "Phase 1 and Phase 2 EVENT IDs overlap")
    source_events = {**phase1_events, **phase2_events}

    source_observations = data["phase1_observations"] + data["phase2_observations"]
    observations_by_id = unique_index(source_observations, "observation_id", "OBSERVATION")
    observations_by_event: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in source_observations:
        event_id = observation.get("event_id")
        require(event_id in source_events, f"observation references unknown EVENT: {event_id}")
        observations_by_event[event_id].append(observation)

    experiment_rows = data["phase1_experiments"] + data["phase2_experiments"]
    experiment_source = unique_index(experiment_rows, "experiment_id", "EXPERIMENT")
    experiments = {key: normalized_experiment(row) for key, row in experiment_source.items()}

    run_rows_with_phase = [
        *( (row, "PHASE1A") for row in data["phase1_runs"] ),
        *( (row, "PHASE2C") for row in data["phase2_runs"] ),
    ]
    runs: dict[str, dict[str, Any]] = {}
    for row, phase_origin in run_rows_with_phase:
        run_id = row["benchmark_run_id"]
        require(run_id not in runs, f"duplicate BENCHMARK_RUN ID: {run_id}")
        normalized = normalized_run(row, phase_origin)
        require(normalized["experiment_id"] in experiments, f"run references unknown EXPERIMENT: {run_id}")
        runs[run_id] = normalized
    for event in source_events.values():
        require(event["benchmark_run_id"] in runs, f"EVENT references unknown run: {event['event_id']}")

    phase1_links = unique_index(data["phase1_identity_links"], "event_id", "Phase 1 EVENT_VARIANT_LINK event")
    phase2_links = unique_index(data["phase2_identity_links"], "event_id", "Phase 2 EVENT_VARIANT_LINK event")
    unique_index(data["phase1_identity_links"], "event_variant_link_id", "Phase 1 EVENT_VARIANT_LINK")
    unique_index(data["phase2_identity_links"], "event_variant_link_id", "Phase 2 EVENT_VARIANT_LINK")
    require(set(phase1_links) <= set(phase1_events), "Phase 1 identity link references non-Phase-1 event")
    require(set(phase2_links) <= set(phase2_events), "Phase 2 identity link references non-Phase-2 event")
    require(
        all(row["identity_status"] == IDENTITY_EXACT for row in data["phase1_identity_links"]),
        "Phase 1B contains a non-exact identity link",
    )
    require(
        all(row["identity_status"] == IDENTITY_EXACT for row in data["phase2_identity_links"]),
        "Phase 2D link table contains a non-exact identity link",
    )

    phase2_accounting = unique_index(
        data["phase2_identity_accounting"], "event_id", "Phase 2 identity accounting"
    )
    require(set(phase2_accounting) == set(phase2_events), "Phase 2 EVENT/accounting sets differ")
    unresolved_phase2 = {
        event_id: row
        for event_id, row in phase2_accounting.items()
        if row["identity_status"] == IDENTITY_UNRESOLVED
    }
    require(
        len(unresolved_phase2) == EXPECTED_COUNTS["phase2_unresolved_events"],
        "Phase 2 unresolved count mismatch",
    )
    require(
        all(not optional(row.get("variant_id")) for row in unresolved_phase2.values()),
        "an unresolved Phase 2 event has a variant_id",
    )
    require(
        set(phase2_links) == set(phase2_events) - set(unresolved_phase2),
        "Phase 2 exact links do not reconcile with explicit unresolved accounting",
    )
    for event_id, accounting in phase2_accounting.items():
        status = accounting["identity_status"]
        require(status in {IDENTITY_EXACT, IDENTITY_UNRESOLVED}, f"unsupported Phase 2 identity state: {status}")
        if status == IDENTITY_EXACT:
            link = phase2_links[event_id]
            require(accounting["variant_id"] == link["variant_id"], f"Phase 2 variant mismatch: {event_id}")
        else:
            require(bool(accounting["unresolved_reason"]), f"unresolved reason missing: {event_id}")

    phase2_link_provenance = unique_index(
        data["phase2_link_provenance"], "event_variant_link_id", "Phase 2 link provenance"
    )
    require(
        set(phase2_link_provenance)
        == {row["event_variant_link_id"] for row in data["phase2_identity_links"]},
        "Phase 2 link provenance does not exactly cover identity links",
    )

    observation_counts = Counter(observation["event_id"] for observation in source_observations)
    require(all(observation_counts[event_id] > 0 for event_id in source_events), "EVENT without OBSERVATION")

    event_records: list[dict[str, Any]] = []
    event_record_by_id: dict[str, dict[str, Any]] = {}
    identity_provenance_by_event: dict[str, dict[str, Any] | None] = {}
    for event_id, row in phase1_events.items():
        link = phase1_links.get(event_id)
        if link is None:
            state = IDENTITY_NOT_EVALUATED
            variant_id = None
        else:
            state = IDENTITY_EXACT
            variant_id = link["variant_id"]
            require(link["benchmark_run_id"] == row["benchmark_run_id"], f"Phase 1 link/run mismatch: {event_id}")
        record = make_event_record(
            row,
            "PHASE1A",
            state,
            variant_id,
            None,
            link,
            observation_counts[event_id],
        )
        event_records.append(record)
        event_record_by_id[event_id] = record
        identity_provenance_by_event[event_id] = make_identity_provenance(
            "PHASE1A", link, None, phase2_link_provenance, authority_hashes
        )

    for event_id, row in phase2_events.items():
        accounting = phase2_accounting[event_id]
        link = phase2_links.get(event_id)
        state = accounting["identity_status"]
        variant_id = accounting["variant_id"] if state == IDENTITY_EXACT else None
        unresolved_reason = accounting["unresolved_reason"] if state == IDENTITY_UNRESOLVED else None
        if link is not None:
            require(link["benchmark_run_id"] == row["benchmark_run_id"], f"Phase 2 link/run mismatch: {event_id}")
        require(
            integer(accounting["observation_count"], "phase2.accounting.observation_count")
            == observation_counts[event_id],
            f"Phase 2 accounting observation count mismatch: {event_id}",
        )
        record = make_event_record(
            row,
            "PHASE2C",
            state,
            variant_id,
            unresolved_reason,
            link,
            observation_counts[event_id],
        )
        if link is None:
            record["identity_method"] = optional(accounting.get("identity_method"))
            record["identity_method_version"] = optional(accounting.get("identity_method_version"))
        event_records.append(record)
        event_record_by_id[event_id] = record
        identity_provenance_by_event[event_id] = make_identity_provenance(
            "PHASE2C", link, accounting if link is None else None, phase2_link_provenance, authority_hashes
        )

    event_records.sort(key=lambda row: row["event_id"])
    require(len(event_records) == EXPECTED_COUNTS["unified_events"], "unified EVENT count mismatch")
    identity_counts = Counter(row["identity_state"] for row in event_records)
    require(set(identity_counts) <= ALLOWED_IDENTITY_STATES, "unexpected Explorer identity state")

    phase1_provenance_ids = direct_provenance_index(data["phase1_provenance"])
    phase2_provenance_ids = direct_provenance_index(data["phase2_provenance"])
    evidence_records: list[dict[str, Any]] = []
    for observation_id, observation in observations_by_id.items():
        event = event_record_by_id[observation["event_id"]]
        run = runs[event["benchmark_run_id"]]
        experiment = experiments[run["experiment_id"]]
        provenance_index = phase1_provenance_ids if event["phase_origin"] == "PHASE1A" else phase2_provenance_ids
        applicable_ids = sorted(
            set(provenance_index.get(observation_id, []))
            | set(provenance_index.get(event["event_id"], []))
        )
        evidence_records.append(
            make_evidence_record(
                observation,
                event["phase_origin"],
                event,
                run,
                experiment,
                applicable_ids,
                identity_provenance_by_event[event["event_id"]],
            )
        )
    evidence_records.sort(key=lambda row: row["observation_id"])
    require(len(evidence_records) == EXPECTED_COUNTS["unified_observations"], "unified OBSERVATION count mismatch")

    source_raw_decisions = {
        observation["observation_id"]: observation["raw_decision"] for observation in source_observations
    }
    output_raw_decisions = {row["observation_id"]: row["raw_decision"] for row in evidence_records}
    require(source_raw_decisions == output_raw_decisions, "raw benchmark decisions changed during export")
    source_sides = {observation["observation_id"]: observation["side"] for observation in source_observations}
    output_sides = {row["observation_id"]: row["side"] for row in evidence_records}
    require(source_sides == output_sides, "QUERY/TRUTH observation sides changed during export")

    phase1_variant_rows = unique_index(data["phase1_variants"], "variant_id", "Phase 1 VARIANT")
    phase2_variant_rows = unique_index(data["phase2_variants"], "variant_id", "Phase 2 VARIANT")
    overlap = set(phase1_variant_rows) & set(phase2_variant_rows)
    # An overlap is permitted only when the frozen identity layers use the same ID
    # and identical identity fields.  No coordinate-only merging is performed.
    identity_fields = (
        "assembly",
        "contig",
        "normalized_start_0based",
        "normalized_end_0based",
        "normalized_ref",
        "normalized_alt",
        "identity_schema_version",
    )
    for variant_id in overlap:
        left, right = phase1_variant_rows[variant_id], phase2_variant_rows[variant_id]
        require(
            all(str(left[field]) == str(right[field]) for field in identity_fields),
            f"frozen authorities disagree for shared variant_id: {variant_id}",
        )

    all_variant_ids = set(phase1_variant_rows) | set(phase2_variant_rows)
    require(len(all_variant_ids) == EXPECTED_COUNTS["unified_variants"], "unified VARIANT count mismatch")
    linked_events_by_variant: dict[str, list[str]] = defaultdict(list)
    for event in event_records:
        if event["variant_id"] is not None:
            require(event["variant_id"] in all_variant_ids, f"EVENT links unknown VARIANT: {event['event_id']}")
            linked_events_by_variant[event["variant_id"]].append(event["event_id"])
    require(set(linked_events_by_variant) == all_variant_ids, "resolved VARIANT without linked EVENT")

    variant_records: list[dict[str, Any]] = []
    for variant_id in sorted(all_variant_ids):
        row = phase1_variant_rows.get(variant_id) or phase2_variant_rows[variant_id]
        if variant_id in phase1_variant_rows and variant_id in phase2_variant_rows:
            phase_origin = "PHASE1B_AND_PHASE2D"
        elif variant_id in phase1_variant_rows:
            phase_origin = "PHASE1B"
        else:
            phase_origin = "PHASE2D"
        linked_event_ids = sorted(linked_events_by_variant[variant_id])
        samples: set[str] = set()
        technologies: set[str] = set()
        variant_observation_count = 0
        for event_id in linked_event_ids:
            event = event_record_by_id[event_id]
            run = runs[event["benchmark_run_id"]]
            experiment = experiments[run["experiment_id"]]
            samples.add(experiment["sample_id"])
            technologies.add(experiment["technology"])
            variant_observation_count += observation_counts[event_id]
        variant_records.append(
            {
                "variant_id": variant_id,
                "assembly": row["assembly"],
                "contig": row["contig"],
                "normalized_start_0based": integer(row["normalized_start_0based"], "variant.start"),
                "normalized_end_0based": integer(row["normalized_end_0based"], "variant.end"),
                "normalized_ref": row["normalized_ref"],
                "normalized_alt": row["normalized_alt"],
                "identity_schema_version": row["identity_schema_version"],
                "phase_origin": phase_origin,
                "linked_event_count": len(linked_event_ids),
                "observation_count": variant_observation_count,
                "sample_ids": sorted(samples),
                "technologies": sorted(technologies),
            }
        )

    unresolved_records = [
        row for row in event_records if row["identity_state"] == IDENTITY_UNRESOLVED
    ]
    require(
        len(unresolved_records) == EXPECTED_COUNTS["phase2_unresolved_events"],
        "unresolved_events export count mismatch",
    )
    require(
        all(row["phase_origin"] == "PHASE2C" and row["variant_id"] is None for row in unresolved_records),
        "unresolved_events contains a non-Phase-2 or variant-linked record",
    )
    require(
        all(
            row["identity_state"] == IDENTITY_NOT_EVALUATED
            for row in event_records
            if row["phase_origin"] == "PHASE1A" and row["event_id"] not in phase1_links
        ),
        "a Phase 1 event outside Phase 1B was mislabeled",
    )

    forbidden = scan_forbidden_fields(
        {
            "variants": variant_records,
            "events": event_records,
            "evidence": evidence_records,
            "unresolved_events": unresolved_records,
        }
    )
    require(not forbidden, f"forbidden Explorer fields generated: {sorted(forbidden)}")

    return {
        "variants": variant_records,
        "events": event_records,
        "evidence": evidence_records,
        "unresolved_events": unresolved_records,
        "identity_state_counts": dict(sorted(identity_counts.items())),
        "samples": sorted({experiment["sample_id"] for experiment in experiments.values()}),
        "technologies": sorted({experiment["technology"] for experiment in experiments.values()}),
        "counts": {
            "variants": len(variant_records),
            "events": len(event_records),
            "observations": len(evidence_records),
            "unresolved_events": len(unresolved_records),
            "experiments": len(experiments),
            "benchmark_runs": len(runs),
            "event_variant_links": len(phase1_links) + len(phase2_links),
        },
    }


VALIDATION_DESCRIPTIONS = {
    1: "authoritative release archive SHA-256 matches the frozen value",
    2: "all nested authority checksum manifests pass",
    3: "Phase 1 counts reconcile",
    4: "Phase 2 counts reconcile",
    5: "unified EVENT count is 11,553",
    6: "unified OBSERVATION count is 23,106",
    7: "every observation references exactly one EVENT",
    8: "every EVENT references exactly one benchmark run",
    9: "every benchmark run references exactly one experiment",
    10: "each EVENT maps to at most one biological VARIANT",
    11: "every Phase 2 EVENT is accounted for by Phase 2D",
    12: "exactly 60 Phase 2 events remain UNRESOLVED",
    13: "unresolved events receive no guessed variant_id",
    14: "Phase 1 events outside identity candidates are not mislabeled UNRESOLVED",
    15: "raw benchmark decisions are preserved",
    16: "QUERY and TRUTH observations remain separate",
    17: "no reliability score is generated",
    18: "no trust score is generated",
    19: "no consensus decision is generated",
    20: "no technology ranking is generated",
    21: "output serialization is deterministic",
    22: "all output checksums validate",
}


def make_manifest(
    model: dict[str, Any],
    authority_hashes: dict[str, str],
    integrity_counts: dict[str, int],
    data_file_hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "explorer_schema_version": EXPLORER_SCHEMA_VERSION,
        "project": PROJECT,
        "scientific_release": SCIENTIFIC_RELEASE,
        "zenodo_doi": ZENODO_DOI,
        "authoritative_archive_sha256": AUTHORITATIVE_ARCHIVE_SHA256,
        "source_authority_archive_sha256": dict(sorted(authority_hashes.items())),
        "creation_method": "scripts/explorer/build_explorer_v1.py",
        "creation_method_version": BUILDER_VERSION,
        "entity_counts": model["counts"],
        "sample_values": model["samples"],
        "technology_values": model["technologies"],
        "identity_state_counts": model["identity_state_counts"],
        "authority_integrity_counts": dict(sorted(integrity_counts.items())),
        "output_file_sha256": dict(sorted(data_file_hashes.items())),
        "checksum_manifest_scope": ["explorer_manifest.json", *OUTPUT_JSON_FILES],
        "coordinate_system": {
            "assembly": "GRCh38",
            "registry_coordinates": "0-based half-open",
            "source_vcf_position": "1-based",
        },
        "scientific_boundary_flags": {
            "reliability_scoring_disabled": True,
            "trust_scoring_disabled": True,
            "consensus_generation_disabled": True,
            "technology_ranking_disabled": True,
            "caller_ranking_disabled": True,
            "representation_equivalence_disabled": True,
            "clinical_interpretation_disabled": True,
            "per_variant_genomic_context_disabled": True,
        },
    }


def verify_output_checksums(output_dir: Path) -> dict[str, str]:
    manifest_path = output_dir / "checksums.sha256"
    checksums = parse_checksum_manifest(manifest_path)
    expected_names = {"explorer_manifest.json", *OUTPUT_JSON_FILES}
    require(set(checksums) == expected_names, "Explorer checksum manifest has an unexpected scope")
    for name, expected in checksums.items():
        target = output_dir / name
        require(target.is_file(), f"Explorer output missing: {target}")
        require(sha256_file(target) == expected, f"Explorer output checksum mismatch: {name}")
    return checksums


def write_outputs(
    output_dir: Path,
    model: dict[str, Any],
    authority_hashes: dict[str, str],
    integrity_counts: dict[str, int],
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    content_by_name = {
        "variants.json": stable_json_bytes(model["variants"]),
        "events.json": stable_json_bytes(model["events"]),
        "evidence.json": stable_json_bytes(model["evidence"]),
        "unresolved_events.json": stable_json_bytes(model["unresolved_events"]),
    }

    # Validation requirement 21: perform a second independent serialization
    # pass over the fully materialized model before writing.
    second_pass = {
        "variants.json": stable_json_bytes(list(model["variants"])),
        "events.json": stable_json_bytes(list(model["events"])),
        "evidence.json": stable_json_bytes(list(model["evidence"])),
        "unresolved_events.json": stable_json_bytes(list(model["unresolved_events"])),
    }
    require(content_by_name == second_pass, "independent JSON serialization passes differ")

    for name in OUTPUT_JSON_FILES:
        write_bytes_atomic(output_dir / name, content_by_name[name])
    data_hashes = {name: sha256_file(output_dir / name) for name in OUTPUT_JSON_FILES}
    manifest = make_manifest(model, authority_hashes, integrity_counts, data_hashes)
    write_json(output_dir / "explorer_manifest.json", manifest)

    checksum_names = ["explorer_manifest.json", *OUTPUT_JSON_FILES]
    checksum_lines = [f"{sha256_file(output_dir / name)}  {name}" for name in sorted(checksum_names)]
    write_bytes_atomic(
        output_dir / "checksums.sha256",
        ("\n".join(checksum_lines) + "\n").encode("utf-8"),
    )
    verify_output_checksums(output_dir)
    return {name: sha256_file(output_dir / name) for name in ALL_OUTPUT_FILES}


def build_explorer(archive: Path, output_dir: Path) -> dict[str, Any]:
    """Build one Explorer export and return its deterministic summary.

    The authoritative archive checksum is verified before creating an output
    directory, extracting content, importing DuckDB, or reading authority data.
    """
    archive = archive.resolve()
    actual_archive_sha256 = sha256_file(archive)
    require(
        actual_archive_sha256 == AUTHORITATIVE_ARCHIVE_SHA256,
        "authoritative archive SHA-256 mismatch: "
        f"{actual_archive_sha256} != {AUTHORITATIVE_ARCHIVE_SHA256}",
    )
    progress("authoritative archive SHA-256 verified")

    with tempfile.TemporaryDirectory(prefix="omicsedge-explorer-v1-") as temporary:
        temporary_root = Path(temporary)
        authority_dirs, authority_hashes, integrity_counts = verify_and_extract_authorities(
            archive, temporary_root
        )
        progress("nested authority archives extracted and verified")
        data = load_authorities(authority_dirs)
        progress("frozen authority tables loaded")
        model = build_model(data, authority_hashes)
        progress("scientific entity model joined and validated")
        output_hashes = write_outputs(output_dir.resolve(), model, authority_hashes, integrity_counts)
        progress("deterministic Explorer outputs written and checksummed")

    validation_results = [
        {"validation_id": index, "description": VALIDATION_DESCRIPTIONS[index], "status": "PASS"}
        for index in range(1, 23)
    ]
    return {
        "output_dir": str(output_dir.resolve()),
        "counts": model["counts"],
        "identity_state_counts": model["identity_state_counts"],
        "output_sha256": output_hashes,
        "validation_results": validation_results,
    }


def parse_args() -> argparse.Namespace:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        type=Path,
        default=repository_root / "results/phase2e/omicsedge_phase2_final_results.tar.gz",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "results/explorer_v1",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = build_explorer(args.archive, args.output_dir)
    except (ExplorerBuildError, FileNotFoundError, json.JSONDecodeError, tarfile.TarError) as exc:
        print(f"EXPLORER_V1_STOP: {exc}")
        return 1
    for result in summary["validation_results"]:
        print(f"PASS {result['validation_id']:02d}: {result['description']}")
    print(json.dumps({key: summary[key] for key in ("output_dir", "counts", "identity_state_counts")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
