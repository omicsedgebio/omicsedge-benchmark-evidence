"""Validate structural and cross-entity invariants for registry bundles."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ENTITY_COLLECTIONS = {
    "EVENT": ("events", "event_id", "event.schema.json"),
    "EXPERIMENT": ("experiments", "experiment_id", "experiment.schema.json"),
    "BENCHMARK_RUN": ("benchmark_runs", "benchmark_run_id", "benchmark_run.schema.json"),
    "OBSERVATION": ("observations", "observation_id", "observation.schema.json"),
    "SOURCE_ARTIFACT": ("source_artifacts", "source_artifact_id", "source_artifact.schema.json"),
    "PROVENANCE_LINK": ("provenance_links", "provenance_link_id", "provenance_link.schema.json"),
}


class RegistryValidationError(ValueError):
    """Raised when a registry bundle violates schema or lineage invariants."""


def _schema_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "schemas"


def _validate_interval(name: str, interval: dict[str, Any], errors: list[str]) -> None:
    if interval["end_0based"] <= interval["start_0based"]:
        errors.append(f"{name}: end_0based must be greater than start_0based")


def validate_bundle(bundle: dict[str, Any], schema_directory: Path | None = None) -> None:
    """Validate JSON Schemas, references, and Phase 1A provenance invariants."""

    schema_directory = schema_directory or _schema_directory()
    errors: list[str] = []
    by_type: dict[str, dict[str, dict[str, Any]]] = {}

    for entity_type, (collection, id_field, schema_name) in ENTITY_COLLECTIONS.items():
        records = bundle.get(collection)
        if not isinstance(records, list):
            errors.append(f"{collection}: must be an array")
            continue

        schema = json.loads((schema_directory / schema_name).read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        entity_map: dict[str, dict[str, Any]] = {}
        for index, record in enumerate(records):
            for validation_error in sorted(validator.iter_errors(record), key=lambda item: list(item.path)):
                location = ".".join(str(part) for part in validation_error.path)
                errors.append(
                    f"{collection}[{index}]"
                    + (f".{location}" if location else "")
                    + f": {validation_error.message}"
                )
            if not isinstance(record, dict) or id_field not in record:
                continue
            identifier = record[id_field]
            if identifier in entity_map:
                errors.append(f"{collection}: duplicate {id_field} {identifier!r}")
            entity_map[identifier] = record
        by_type[entity_type] = entity_map

    artifacts = by_type.get("SOURCE_ARTIFACT", {})
    experiments = by_type.get("EXPERIMENT", {})
    runs = by_type.get("BENCHMARK_RUN", {})
    events = by_type.get("EVENT", {})
    observations = by_type.get("OBSERVATION", {})

    for event_id, event in events.items():
        if event.get("benchmark_run_id") not in runs:
            errors.append(f"EVENT {event_id}: unresolved benchmark_run_id")
        if event.get("reference_artifact_id") not in artifacts:
            errors.append(f"EVENT {event_id}: unresolved reference_artifact_id")
        if all(key in event for key in ("start_0based", "end_0based")):
            _validate_interval(f"EVENT {event_id}", event, errors)

    artifact_fields = (
        "query_artifact_id",
        "truth_artifact_id",
        "benchmark_bed_artifact_id",
        "reference_artifact_id",
    )
    for run_id, run in runs.items():
        if run.get("experiment_id") not in experiments:
            errors.append(f"BENCHMARK_RUN {run_id}: unresolved experiment_id")
        for field in artifact_fields:
            if run.get(field) not in artifacts:
                errors.append(f"BENCHMARK_RUN {run_id}: unresolved {field}")
        for output_id in run.get("output_artifact_ids", []):
            if output_id not in artifacts:
                errors.append(f"BENCHMARK_RUN {run_id}: unresolved output artifact {output_id!r}")
        for interval_name in ("core_interval", "padded_interval"):
            if isinstance(run.get(interval_name), dict):
                _validate_interval(f"BENCHMARK_RUN {run_id}.{interval_name}", run[interval_name], errors)
        core = run.get("core_interval")
        padded = run.get("padded_interval")
        if isinstance(core, dict) and isinstance(padded, dict):
            if (core.get("assembly"), core.get("contig")) != (padded.get("assembly"), padded.get("contig")):
                errors.append(f"BENCHMARK_RUN {run_id}: core and padded intervals use different references")
            elif not (
                padded.get("start_0based", 1) <= core.get("start_0based", 0)
                and padded.get("end_0based", 0) >= core.get("end_0based", 1)
            ):
                errors.append(f"BENCHMARK_RUN {run_id}: padded interval does not contain core interval")

    for experiment_id, experiment in experiments.items():
        for artifact_id in experiment.get("metadata_artifact_ids", []):
            if artifact_id not in artifacts:
                errors.append(f"EXPERIMENT {experiment_id}: unresolved metadata artifact {artifact_id!r}")

    for observation_id, observation in observations.items():
        run_id = observation.get("benchmark_run_id")
        event_id = observation.get("event_id")
        if run_id not in runs:
            errors.append(f"OBSERVATION {observation_id}: unresolved benchmark_run_id")
        if event_id not in events:
            errors.append(f"OBSERVATION {observation_id}: unresolved event_id")
        elif events[event_id].get("benchmark_run_id") != run_id:
            errors.append(f"OBSERVATION {observation_id}: event and observation use different runs")
        if observation.get("source_output_artifact_id") not in artifacts:
            errors.append(f"OBSERVATION {observation_id}: unresolved source_output_artifact_id")

    links = list(by_type.get("PROVENANCE_LINK", {}).values())
    for link in links:
        source_type = link.get("source_entity_type")
        target_type = link.get("target_entity_type")
        if link.get("source_entity_id") not in by_type.get(source_type, {}):
            errors.append(f"PROVENANCE_LINK {link.get('provenance_link_id')}: unresolved source endpoint")
        if link.get("target_entity_id") not in by_type.get(target_type, {}):
            errors.append(f"PROVENANCE_LINK {link.get('provenance_link_id')}: unresolved target endpoint")

    normalized_from_targets = {
        link["target_entity_id"]
        for link in links
        if link.get("relation") == "NORMALIZED_FROM"
        and link.get("source_entity_type") == "SOURCE_ARTIFACT"
        and link.get("target_entity_type") == "OBSERVATION"
    }
    missing_lineage = sorted(set(observations) - normalized_from_targets)
    if missing_lineage:
        errors.append(f"observations missing NORMALIZED_FROM artifact lineage: {missing_lineage}")

    run_counts = Counter(observation.get("benchmark_run_id") for observation in observations.values())
    for run_id, run in runs.items():
        if run.get("run_status") == "SUCCEEDED" and run_counts[run_id] == 0:
            errors.append(f"BENCHMARK_RUN {run_id}: succeeded run has no observations")

    if errors:
        raise RegistryValidationError("\n".join(errors))
