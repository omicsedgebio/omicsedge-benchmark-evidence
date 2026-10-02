"""Deterministic bounded-pilot orchestration and output generation."""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from evidence_atlas import protocol

from .models import CatalogAdapter, PilotTaxon, RequestSnapshot
from .normalize import TechnologyNormalizer, deduplicate_by_run_accession, normalize_ena_record
from .provenance import canonical_json_bytes, file_manifest, parameters_sha256, pretty_json_bytes


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    payload = b"".join(canonical_json_bytes(row) for row in rows)
    _write(path, payload)


def _counter_rows(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"value": key, "count": counter[key]} for key in sorted(counter)]


def _observations(records: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    technology = Counter()
    normalized_models = Counter()
    raw_models = Counter()
    unresolved: list[dict[str, Any]] = []
    for record in records:
        accession = record["run_accession"]
        platform = record["sequencing_run"]["platform"]
        family = platform["technology_family"]["value"]
        model = platform["instrument_model"]["value"]
        if family != "UNKNOWN":
            technology[family] += 1
        if model not in {"UNKNOWN", "UNSPECIFIED"}:
            normalized_models[model] += 1
        raw_model = record["raw_source_values"].get("instrument_model")
        if raw_model:
            raw_models[raw_model] += 1
        for field in record["catalog_record"]["normalization_confidence"]["unresolved_hard_gate_fields"]:
            raw_field = {
                "technology_family_id": "instrument_platform",
                "vendor_id": "instrument_platform",
                "instrument_family_id": "instrument_model",
                "library_strategy": "library_strategy",
                "library_source": "library_source",
                "sample_id": "secondary_sample_accession",
                "assembly_id": None,
            }.get(field)
            unresolved.append(
                {
                    "run_accession": accession,
                    "field": field,
                    "raw_value": record["raw_source_values"].get(raw_field, "") if raw_field else "",
                    "reason": "missing_or_not_deterministically_mappable",
                }
            )
    instruments = [
        {"kind": "normalized_model", **row} for row in _counter_rows(normalized_models)
    ] + [{"kind": "source_reported_model", **row} for row in _counter_rows(raw_models)]
    return (
        [{"kind": "technology_family", **row} for row in _counter_rows(technology)],
        instruments,
        sorted(unresolved, key=lambda row: (row["run_accession"], row["field"])),
    )


def _validate_bundle(bundle: Mapping[str, Any]) -> None:
    protocol.validate_schema("sequencing_run", bundle["sequencing_run"])
    protocol.validate_schema("source_record", bundle["source_record"])
    protocol.validate_catalog_record(bundle["catalog_record"])
    for artifact in bundle["derived_artifacts"]:
        protocol.validate_schema("derived_artifact", artifact)
    state = bundle["catalog_record"]["eligibility_state"]
    if state != "CATALOGUED" or bundle["catalog_record"]["layer"] != "PUBLIC_DATA_CATALOG":
        raise protocol.AtlasProtocolError("M1A may only create CATALOGUED public-data records")


def _request_filename(taxon: PilotTaxon, index: int, snapshot: RequestSnapshot) -> str:
    endpoint = snapshot.endpoint.rsplit("/", 1)[-1].replace("F", "_f").lower()
    return f"ena_{taxon.taxon_id}_{taxon.query_mode}_{index:02d}_{endpoint}_{snapshot.response_sha256[:16]}.tsv"


def _build_pilot(
    *,
    adapter: CatalogAdapter,
    taxa: Sequence[PilotTaxon],
    limit: int,
    output_dir: Path,
    results_dir: Path,
    technology_taxonomy_path: Path,
    clock: Callable[[], datetime] = _utc_now,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Run a bounded metadata-only pilot and write compact deterministic outputs."""

    if not taxa:
        raise ValueError("at least one taxon is required")
    if len(taxa) * limit > 400:
        raise ValueError("M1A live pilot may not exceed approximately 400 requested records")
    started = monotonic()
    run_started_at = _timestamp(clock())
    snapshots_dir = output_dir / "snapshots"
    normalized_dir = output_dir / "normalized"
    manifests_dir = output_dir / "manifests"
    for directory in (snapshots_dir, normalized_dir, manifests_dir, results_dir):
        directory.mkdir(parents=True, exist_ok=True)

    normalizer = TechnologyNormalizer.from_path(technology_taxonomy_path)
    all_bundles: list[Mapping[str, Any]] = []
    request_manifest: list[dict[str, Any]] = []
    taxon_summaries: list[dict[str, Any]] = []
    discovery_activities: list[dict[str, Any]] = []

    for taxon in taxa:
        result = adapter.discover(taxon, limit=limit)
        search_snapshot = next(
            snapshot for snapshot in result.requests if snapshot.endpoint.rstrip("/").endswith("/search")
        )
        snapshot_paths: dict[int, str] = {}
        for index, snapshot in enumerate(result.requests, start=1):
            filename = _request_filename(taxon, index, snapshot)
            path = snapshots_dir / filename
            _write(path, snapshot.response_body)
            relative = path.relative_to(output_dir).as_posix()
            snapshot_paths[id(snapshot)] = relative
            entry = snapshot.manifest_entry(relative)
            entry["pilot_taxon_id"] = taxon.taxon_id
            entry["pilot_query_mode"] = taxon.query_mode
            request_manifest.append(entry)

        bundles: list[Mapping[str, Any]] = []
        for row in result.records:
            bundle = normalize_ena_record(
                row,
                technology=normalizer,
                retrieved_at=search_snapshot.retrieved_at,
                endpoint=search_snapshot.endpoint,
                parameters=search_snapshot.parameters,
                response_sha256=search_snapshot.response_sha256,
                raw_snapshot_uri=snapshot_paths[id(search_snapshot)],
            )
            _validate_bundle(bundle)
            bundles.append(bundle)
        unique_taxon, duplicate_taxon = deduplicate_by_run_accession(bundles)
        all_bundles.extend(unique_taxon)
        technologies, instruments, taxon_unresolved = _observations(unique_taxon)
        missing_sample = sum(
            not (row["accessions"]["sample_accessions"] or row["accessions"]["biosample_accessions"])
            for row in unique_taxon
        )
        multiple_sample = sum(len(row["accessions"]["biosample_accessions"]) > 1 for row in unique_taxon)
        missing_study = sum(
            not (row["accessions"]["study_accessions"] or row["accessions"]["bioproject_accessions"])
            for row in unique_taxon
        )
        taxon_summaries.append(
            {
                "taxon_id": taxon.taxon_id,
                "scientific_name": taxon.scientific_name,
                "query_mode": taxon.query_mode,
                "source_reported_run_count": result.source_reported_count,
                "source_reported_count_method": "ENA Portal API /count aggregate; no run enumeration",
                "pilot_records_fetched": len(result.records),
                "unique_run_accessions": len(unique_taxon),
                "duplicate_run_accessions": duplicate_taxon,
                "technology_families_observed": technologies,
                "instrument_models_observed": instruments,
                "unresolved_metadata_fields": len(taxon_unresolved),
                "unresolved_technology_records": sum(
                    row["sequencing_run"]["platform"]["technology_family"]["value"] == "UNKNOWN"
                    or row["sequencing_run"]["platform"]["instrument_family"]["value"] == "UNKNOWN"
                    for row in unique_taxon
                ),
                "missing_sample_ids": missing_sample,
                "multiple_sample_ids": multiple_sample,
                "missing_study_ids": missing_study,
                "pagination": result.pagination_note,
            }
        )
        generated = [
            {"kind": "SOURCE_RECORD", "id": row["source_record"]["source_record_id"]}
            for row in unique_taxon
        ]
        if generated:
            activity = {
                "schema_version": "atlas-0.1.0",
                "activity_id": f"activity:ena:{taxon.taxon_id}:{search_snapshot.response_sha256[:16]}",
                "activity_type": "DISCOVERY_QUERY",
                "started_at": search_snapshot.retrieved_at,
                "ended_at": search_snapshot.retrieved_at,
                "agent": {"type": "SOURCE_SYNC", "id": "m1a-ena-catalog", "version": "0.1.0"},
                "parameters_sha256": parameters_sha256(search_snapshot.parameters),
                "used": [],
                "generated": generated,
            }
            protocol.validate_schema("provenance_activity", activity)
            discovery_activities.append(activity)

    unique_bundles, cross_scope_duplicates = deduplicate_by_run_accession(all_bundles)
    technologies, instruments, unresolved = _observations(unique_bundles)
    unique_bundles = list(unique_bundles)

    output_files = {
        "records": normalized_dir / "records.jsonl",
        "sequencing_runs": normalized_dir / "sequencing_runs.jsonl",
        "source_records": normalized_dir / "source_records.jsonl",
        "catalog_records": normalized_dir / "catalog_records.jsonl",
        "derived_artifacts": normalized_dir / "derived_artifacts.jsonl",
        "provenance_activities": normalized_dir / "provenance_activities.jsonl",
    }
    _write_jsonl(output_files["records"], unique_bundles)
    _write_jsonl(output_files["sequencing_runs"], (row["sequencing_run"] for row in unique_bundles))
    _write_jsonl(output_files["source_records"], (row["source_record"] for row in unique_bundles))
    _write_jsonl(output_files["catalog_records"], (row["catalog_record"] for row in unique_bundles))
    _write_jsonl(
        output_files["derived_artifacts"],
        (artifact for row in unique_bundles for artifact in row["derived_artifacts"]),
    )
    _write_jsonl(output_files["provenance_activities"], discovery_activities)

    elapsed = round(monotonic() - started, 3)
    summary = {
        "milestone": "M1A",
        "status": "BOUNDED_CATALOG_PILOT_NOT_EVIDENCE",
        "source": adapter.source_id,
        "result_type": "read_run",
        "run_started_at": run_started_at,
        "runtime_seconds": elapsed,
        "limits": {"per_taxon": limit, "maximum_total": 400, "raw_sequence_downloads": 0},
        "counting_unit": "distinct INSDC run_accession across the insdc mirror group",
        "counts": {
            "SOURCE_REPORTED_DISCOVERED": {
                "aggregate_run_count_sum_across_nonoverlapping_pilot_queries": sum(
                    row["source_reported_run_count"] for row in taxon_summaries
                ),
                "method": "ENA Portal API /count aggregates; not full enumeration",
            },
            "NORMALIZED": {
                "pilot_records_fetched": sum(row["pilot_records_fetched"] for row in taxon_summaries),
                "unique_run_accessions": len(unique_bundles),
                "duplicate_run_accessions_within_queries": sum(
                    row["duplicate_run_accessions"] for row in taxon_summaries
                ),
                "duplicate_run_accessions_across_query_scopes": cross_scope_duplicates,
            },
            "UNRESOLVED": {
                "metadata_fields": len(unresolved),
                "technology_records": sum(
                    row["sequencing_run"]["platform"]["technology_family"]["value"] == "UNKNOWN"
                    or row["sequencing_run"]["platform"]["instrument_family"]["value"] == "UNKNOWN"
                    for row in unique_bundles
                ),
                "missing_sample_ids": sum(
                    not (row["accessions"]["sample_accessions"] or row["accessions"]["biosample_accessions"])
                    for row in unique_bundles
                ),
                "multiple_sample_ids": sum(
                    len(row["accessions"]["biosample_accessions"]) > 1 for row in unique_bundles
                ),
                "missing_study_ids": sum(
                    not (row["accessions"]["study_accessions"] or row["accessions"]["bioproject_accessions"])
                    for row in unique_bundles
                ),
            },
        },
        "technology_families_observed": technologies,
        "instrument_models_observed": instruments,
        "taxa": taxon_summaries,
        "lifecycle_assertion": {
            "state": "CATALOGUED",
            "layer": "PUBLIC_DATA_CATALOG",
            "eligible_records": 0,
            "validated_records": 0,
            "released_records": 0,
        },
        "api_discrepancies": [
            "M1A intentionally uses bounded limit queries. It does not use ENA limit=0 or attempt full-archive ingestion.",
            "ENA introspection rows with an empty description omit that middle TSV cell; M1A accepts the unambiguous columnId/type form only for introspection.",
            "ENA intermittently returned HTTP 200 with an error payload during pilot probes; M1A validates response structure and retries malformed success bodies.",
        ],
        "output_manifest": {"path": "manifests/pilot_snapshot_manifest.json"},
    }
    summary_json = results_dir / "m1a_summary.json"
    _write(summary_json, pretty_json_bytes(summary))

    summary_tsv = results_dir / "m1a_summary.tsv"
    with summary_tsv.open("w", encoding="utf-8", newline="") as handle:
        columns = [
            "taxon_id",
            "scientific_name",
            "query_mode",
            "source_reported_run_count",
            "source_reported_count_method",
            "pilot_records_fetched",
            "unique_run_accessions",
            "duplicate_run_accessions",
            "unresolved_technology_records",
            "missing_sample_ids",
            "multiple_sample_ids",
            "missing_study_ids",
        ]
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in taxon_summaries:
            writer.writerow({column: row[column] for column in columns})

    unresolved_tsv = results_dir / "unresolved_metadata.tsv"
    with unresolved_tsv.open("w", encoding="utf-8", newline="") as handle:
        columns = ["run_accession", "field", "raw_value", "reason"]
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(unresolved)

    manifest_payload = {
        "manifest_version": "m1a-0.1.0",
        "milestone": "M1A",
        "scope": "bounded metadata-only pilot; not Evidence Atlas evidence",
        "requests": sorted(
            request_manifest,
            key=lambda row: (row["pilot_taxon_id"], row["endpoint"], row["response_sha256"]),
        ),
        "artifacts": file_manifest(
            [*output_files.values(), summary_json, summary_tsv, unresolved_tsv], output_dir.parent.parent.parent,
        ),
    }
    manifest_path = manifests_dir / "pilot_snapshot_manifest.json"
    _write(manifest_path, pretty_json_bytes(manifest_payload))
    return summary


def run_pilot(
    *,
    adapter: CatalogAdapter,
    taxa: Sequence[PilotTaxon],
    limit: int,
    output_dir: Path,
    results_dir: Path,
    technology_taxonomy_path: Path,
    clock: Callable[[], datetime] = _utc_now,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Build in staging and replace prior outputs only after full validation."""

    output_dir = output_dir.resolve()
    results_dir = results_dir.resolve()
    common_root = Path(os.path.commonpath((output_dir, results_dir)))
    if common_root == Path(common_root.anchor):
        raise ValueError("output and results directories must share a scoped project root")
    if output_dir == results_dir or output_dir in results_dir.parents or results_dir in output_dir.parents:
        raise ValueError("output and results directories must not overlap")
    common_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=".m1a-build-", dir=common_root) as temporary:
        stage_root = Path(temporary)
        stage_output = stage_root / output_dir.relative_to(common_root)
        stage_results = stage_root / results_dir.relative_to(common_root)
        summary = _build_pilot(
            adapter=adapter,
            taxa=taxa,
            limit=limit,
            output_dir=stage_output,
            results_dir=stage_results,
            technology_taxonomy_path=technology_taxonomy_path,
            clock=clock,
            monotonic=monotonic,
        )

        backup_output = stage_root / ".backup-output"
        backup_results = stage_root / ".backup-results"
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        results_dir.parent.mkdir(parents=True, exist_ok=True)
        if output_dir.exists():
            output_dir.rename(backup_output)
        if results_dir.exists():
            results_dir.rename(backup_results)
        try:
            stage_output.rename(output_dir)
            stage_results.rename(results_dir)
        except Exception:
            if output_dir.exists():
                shutil.rmtree(output_dir)
            if results_dir.exists():
                shutil.rmtree(results_dir)
            if backup_output.exists():
                backup_output.rename(output_dir)
            if backup_results.exists():
                backup_results.rename(results_dir)
            raise
        return summary
