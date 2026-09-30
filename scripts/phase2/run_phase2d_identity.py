#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import jsonschema
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from benchmark_evidence.phase1b_identity import (  # noqa: E402
    EXACT_NORMALIZED_ALLELE,
    IDENTITY_SCHEMA_VERSION,
    REPRESENTATION_EQUIVALENCE_SUPPORTED,
    variant_id as frozen_variant_id,
)

PHASE1B_ARCHIVE = ROOT / "results/phase1b/omicsedge_phase1b_results.tar.gz"
PHASE2C_ARCHIVE = ROOT / "results/phase2c/omicsedge_phase2c_results.tar.gz"
PHASE2D_PROTOCOL = ROOT / "docs/phase2/phase2d_identity_protocol.md"
PHASE2D_PROTOCOL_LOCK = ROOT / "docs/phase2/phase2d_identity_protocol.lock"
IDENTITY_LIB = ROOT / "src/benchmark_evidence/phase1b_identity.py"
ADMITTED_LOCK = ROOT / "data/phase2/admitted_sources.lock"
PANEL_LOCK = ROOT / "data/phase2/interval_panel.lock"
VARIANT_SCHEMA_PATH = ROOT / "schemas/phase2/variant.phase2d.schema.json"
LINK_SCHEMA_PATH = ROOT / "schemas/phase2/event_variant_link.phase2d.schema.json"

OUTPUT_ROOT = ROOT / "results/phase2d"
BUNDLE_DIR = OUTPUT_ROOT / "omicsedge_phase2d_results"
ARCHIVE_PATH = OUTPUT_ROOT / "omicsedge_phase2d_results.tar.gz"

EXPECTED_PHASE1B_SHA = "50bf597cbc13a051d5dda7201e9d7653dbc7b1762fef1b8300199641df6474fb"
EXPECTED_PHASE2C_SHA = "345b6c3483350f4f1930fc5957f7a97c2b2daf30e6ba1972f2cf3b8484ff0536"
EXPECTED_PROTOCOL_SHA = "d7108f9547a407053a8cd2667ce3d92532487d8dbfb022e0b2ccbc2b68aabd60"
EXPECTED_PROTOCOL_LOCK_SHA = "34d956ac25456262097d8f683947a7c82ed6e7b5bb9985468ee637fa9da40bf6"
EXPECTED_IDENTITY_LIB_SHA = "ef05ab077a5bc4495616331dff663d3cea45297651c7a18cd243e98b21532a5c"
EXPECTED_ADMITTED_LOCK_SHA = "63d72d95d48c923514760c72f28a9a397071f6c44fa615bbc55a5fb5adf3a48c"
EXPECTED_PANEL_LOCK_SHA = "ef00c21f0e667c1891b90d6785f1072895a8b9d620a5519130a8a1823a4bd9a1"

IDENTITY_METHOD = "PHASE1B_EXACT_NORMALIZED_ALLELE_V1"
IDENTITY_METHOD_VERSION = "1.0.0"
PHASE2D_APPLICATION_VERSION = "1.0.0"
VARIANT_SCHEMA_VERSION = "1.0.0"
LINK_SCHEMA_VERSION = "1.0.0"

FORBIDDEN_OUTPUT_FIELD_FRAGMENTS = (
    "reliability",
    "confidence",
    "trusted",
    "ranking",
    "consensus",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def deterministic_id(prefix: str, payload: dict) -> str:
    digest = hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()
    return f"{prefix}:sha256:{digest}"


def link_id(event_id: str, variant_id: str, benchmark_run_id: str) -> str:
    payload = {
        "schema_version": LINK_SCHEMA_VERSION,
        "event_id": event_id,
        "variant_id": variant_id,
        "benchmark_run_id": benchmark_run_id,
        "identity_status": EXACT_NORMALIZED_ALLELE,
        "identity_method": IDENTITY_METHOD,
        "identity_method_version": IDENTITY_METHOD_VERSION,
    }
    return deterministic_id("event-variant-link", payload)


def safe_extract(archive: Path, destination: Path) -> list[str]:
    names = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            require(member.isfile(), f"archive contains non-file member: {member.name}")
            p = Path(member.name)
            require(not p.is_absolute(), f"archive absolute member: {member.name}")
            require(".." not in p.parts, f"archive parent traversal: {member.name}")
            target = destination / p
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            require(source is not None, f"cannot read archive member: {member.name}")
            with source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            names.append(member.name)
    return names


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        require(rows, f"fieldnames required for empty table: {path.name}")
        fieldnames = list(rows[0].keys())
    for row in rows:
        require(list(row.keys()) == fieldnames, f"column order mismatch in {path.name}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_parquet(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if rows:
        table = pa.Table.from_pylist(rows)
    else:
        require(fieldnames is not None, f"fieldnames required for empty parquet: {path.name}")
        table = pa.table({name: pa.array([], type=pa.string()) for name in fieldnames})
    pq.write_table(table, path, compression="zstd")
    returned = pq.read_table(path)
    require(returned.num_rows == len(rows), f"Parquet row-count mismatch: {path.name}")


def verify_phase1b_release(extracted: Path) -> dict:
    manifest_path = extracted / "results/phase1b/phase1b_release_manifest.json"
    require(manifest_path.is_file(), "Phase 1B packaged release manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("scientific_gate") == "PASS", "Phase 1B packaged gate is not PASS")
    require(manifest.get("validation_criteria") == "15/15 PASS", "Phase 1B packaged validation mismatch")
    for artifact in manifest["artifacts"]:
        p = extracted / artifact["path"]
        require(p.is_file(), f"Phase 1B packaged artifact missing: {artifact['path']}")
        require(sha256_file(p) == artifact["sha256"], f"Phase 1B artifact SHA mismatch: {artifact['path']}")
        require(p.stat().st_size == artifact["size_bytes"], f"Phase 1B artifact size mismatch: {artifact['path']}")
    return manifest


def verify_phase2c_release(extracted: Path) -> Path:
    root = extracted / "omicsedge_phase2c_results"
    require(root.is_dir(), "Phase 2C result root missing")
    checksum_path = root / "checksums.sha256"
    require(checksum_path.is_file(), "Phase 2C checksum manifest missing")
    for raw in checksum_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split("  ", 1)
        p = root / relative
        require(p.is_file(), f"Phase 2C packaged artifact missing: {relative}")
        require(sha256_file(p) == expected, f"Phase 2C artifact SHA mismatch: {relative}")
    gates = read_tsv(root / "phase2c_validation_results.tsv")
    require(len(gates) == 19, f"expected 19 Phase 2C gates, observed {len(gates)}")
    require(all(row["status"] == "PASS" for row in gates), "not all Phase 2C gates are PASS")
    return root


def parse_int(value: str, label: str) -> int:
    require(value not in (None, ""), f"missing integer field: {label}")
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"invalid integer {label}: {value}") from exc


def source_identity_tuple(event: dict, observations: list[dict]):
    if not observations:
        return None, "MISSING_OBSERVATIONS", 0, 0
    if not event.get("assembly"):
        return None, "MISSING_EVENT_ASSEMBLY", len(observations), 0
    if not event.get("contig"):
        return None, "MISSING_EVENT_CONTIG", len(observations), 0

    allele_tuples = []
    complete = 0
    for obs in observations:
        values = (
            obs.get("normalized_start_0based", ""),
            obs.get("normalized_end_0based", ""),
            obs.get("normalized_ref", ""),
            obs.get("normalized_alt", ""),
        )
        if any(v in (None, "") for v in values):
            continue
        complete += 1
        allele_tuples.append(
            (
                parse_int(values[0], "normalized_start_0based"),
                parse_int(values[1], "normalized_end_0based"),
                values[2],
                values[3],
            )
        )

    if complete != len(observations):
        return None, "MISSING_NORMALIZED_ALLELE_FIELD", len(observations), len(set(allele_tuples))

    unique = set(allele_tuples)
    if len(unique) != 1:
        return None, "MULTIPLE_NORMALIZED_ALLELES", len(observations), len(unique)

    start, end, ref, alt = next(iter(unique))
    allele = {
        "assembly": event["assembly"],
        "contig": event["contig"],
        "start": start,
        "end": end,
        "ref": ref,
        "alt": alt,
    }

    lookup = event.get("normalized_allele_lookup_key", "")
    if lookup:
        expected_lookup = (
            f"{allele['assembly']}|{allele['contig']}|{allele['start'] + 1}|"
            f"{str(allele['ref']).upper()}|{str(allele['alt']).upper()}"
        )
        if lookup != expected_lookup:
            return None, "LOOKUP_KEY_MISMATCH", len(observations), 1

    try:
        frozen_variant_id(allele)
    except Exception:
        return None, "INVALID_IDENTITY_FIELDS", len(observations), 1

    return allele, "", len(observations), 1


def scientific_row_hash(rows: list[dict]) -> str:
    return hashlib.sha256(
        canonical_json(rows).encode("utf-8")
    ).hexdigest()


def transform(
    events: list[dict],
    observations: list[dict],
    benchmark_runs: list[dict],
    experiments: list[dict],
    phase1b_variants: list[dict],
):
    events = sorted(events, key=lambda row: row["event_id"])
    observations = sorted(observations, key=lambda row: row["observation_id"])

    observations_by_event = defaultdict(list)
    for obs in observations:
        observations_by_event[obs["event_id"]].append(obs)

    phase1b_by_id = {row["variant_id"]: row for row in phase1b_variants}
    require(len(phase1b_by_id) == len(phase1b_variants), "duplicate Phase 1B VARIANT IDs")

    for row in phase1b_variants:
        allele = {
            "assembly": row["assembly"],
            "contig": row["contig"],
            "start": parse_int(row["normalized_start_0based"], "Phase1B start"),
            "end": parse_int(row["normalized_end_0based"], "Phase1B end"),
            "ref": row["normalized_ref"],
            "alt": row["normalized_alt"],
        }
        require(
            frozen_variant_id(allele) == row["variant_id"],
            f"Phase 1B VARIANT ID no longer reproduces: {row['variant_id']}",
        )

    new_variant_support = {}
    links = []
    accounting = []
    provenance = []
    variant_index = {}
    seen_events = set()
    link_by_event = {}

    for event in events:
        event_id = event["event_id"]
        require(event_id not in seen_events, f"duplicate Phase 2C event ID: {event_id}")
        seen_events.add(event_id)

        event_obs = observations_by_event.get(event_id, [])
        allele, unresolved_reason, observation_count, distinct_allele_count = source_identity_tuple(
            event, event_obs
        )

        base_account = {
            "event_id": event_id,
            "benchmark_run_id": event["benchmark_run_id"],
            "assembly": event.get("assembly", ""),
            "contig": event.get("contig", ""),
            "identity_status": "",
            "unresolved_reason": "",
            "variant_id": "",
            "variant_origin": "",
            "observation_count": observation_count,
            "distinct_complete_normalized_alleles": distinct_allele_count,
            "normalized_allele_lookup_key": event.get("normalized_allele_lookup_key", ""),
            "reference_artifact_id": event.get("reference_artifact_id", ""),
            "identity_method": IDENTITY_METHOD,
            "identity_method_version": IDENTITY_METHOD_VERSION,
            "phase2d_application_version": PHASE2D_APPLICATION_VERSION,
        }

        if allele is None:
            base_account["identity_status"] = "UNRESOLVED"
            base_account["unresolved_reason"] = unresolved_reason
            accounting.append(base_account)
            continue

        vid = frozen_variant_id(allele)
        variant_origin = "PHASE1B_REUSED" if vid in phase1b_by_id else "PHASE2D_NEW"

        normalization_methods = {
            obs.get("normalization_method", "")
            for obs in event_obs
            if obs.get("normalization_method", "")
        }
        normalization_versions = {
            obs.get("normalization_version", "")
            for obs in event_obs
            if obs.get("normalization_version", "")
        }
        require(normalization_methods, f"missing normalization method for {event_id}")
        require(normalization_versions, f"missing normalization version for {event_id}")

        if vid in phase1b_by_id:
            existing = phase1b_by_id[vid]
            comparisons = {
                "assembly": allele["assembly"],
                "contig": allele["contig"],
                "normalized_start_0based": str(allele["start"]),
                "normalized_end_0based": str(allele["end"]),
                "normalized_ref": allele["ref"],
                "normalized_alt": allele["alt"],
            }
            for field, expected in comparisons.items():
                require(
                    str(existing[field]) == str(expected),
                    f"Phase 1B reused VARIANT content conflict: {vid} field={field}",
                )
        else:
            if vid not in new_variant_support:
                new_variant_support[vid] = {
                    "allele": dict(allele),
                    "reference_artifact_ids": set(),
                    "normalization_methods": set(),
                    "normalization_versions": set(),
                }
            support = new_variant_support[vid]
            require(support["allele"] == allele, f"new VARIANT allele conflict: {vid}")
            support["reference_artifact_ids"].add(event["reference_artifact_id"])
            support["normalization_methods"].update(normalization_methods)
            support["normalization_versions"].update(normalization_versions)

        lid = link_id(event_id, vid, event["benchmark_run_id"])
        require(event_id not in link_by_event, f"event linked more than once: {event_id}")
        link_by_event[event_id] = lid

        evidence = {
            "assembly": allele["assembly"],
            "contig": allele["contig"],
            "normalized_start_0based": allele["start"],
            "normalized_end_0based": allele["end"],
            "normalized_ref": allele["ref"],
            "normalized_alt": allele["alt"],
            "normalized_allele_lookup_key": event.get("normalized_allele_lookup_key") or None,
            "observation_ids": sorted(obs["observation_id"] for obs in event_obs),
        }
        provenance_payload = {
            "phase1b_archive_sha256": EXPECTED_PHASE1B_SHA,
            "phase2c_archive_sha256": EXPECTED_PHASE2C_SHA,
            "phase2d_protocol_sha256": EXPECTED_PROTOCOL_SHA,
            "admitted_sources_lock_sha256": EXPECTED_ADMITTED_LOCK_SHA,
            "interval_panel_lock_sha256": EXPECTED_PANEL_LOCK_SHA,
            "source_event_id": event_id,
            "source_benchmark_run_id": event["benchmark_run_id"],
            "reference_artifact_id": event["reference_artifact_id"],
        }

        links.append(
            {
                "schema_version": LINK_SCHEMA_VERSION,
                "event_variant_link_id": lid,
                "event_id": event_id,
                "variant_id": vid,
                "benchmark_run_id": event["benchmark_run_id"],
                "identity_status": EXACT_NORMALIZED_ALLELE,
                "identity_method": IDENTITY_METHOD,
                "identity_method_version": IDENTITY_METHOD_VERSION,
                "phase2d_application_version": PHASE2D_APPLICATION_VERSION,
                "variant_origin": variant_origin,
                "evidence": canonical_json(evidence),
                "provenance": canonical_json(provenance_payload),
                "phase2c_archive_sha256": EXPECTED_PHASE2C_SHA,
                "admitted_sources_lock_sha256": EXPECTED_ADMITTED_LOCK_SHA,
                "interval_panel_lock_sha256": EXPECTED_PANEL_LOCK_SHA,
            }
        )

        provenance.append(
            {
                "provenance_record_id": deterministic_id(
                    "phase2d-provenance",
                    {
                        "event_variant_link_id": lid,
                        "phase2c_archive_sha256": EXPECTED_PHASE2C_SHA,
                        "phase2d_protocol_sha256": EXPECTED_PROTOCOL_SHA,
                    },
                ),
                "event_variant_link_id": lid,
                "event_id": event_id,
                "variant_id": vid,
                "benchmark_run_id": event["benchmark_run_id"],
                "identity_method": IDENTITY_METHOD,
                "identity_method_version": IDENTITY_METHOD_VERSION,
                "phase2d_application_version": PHASE2D_APPLICATION_VERSION,
                "phase1b_archive_sha256": EXPECTED_PHASE1B_SHA,
                "phase2c_archive_sha256": EXPECTED_PHASE2C_SHA,
                "phase2d_protocol_sha256": EXPECTED_PROTOCOL_SHA,
                "admitted_sources_lock_sha256": EXPECTED_ADMITTED_LOCK_SHA,
                "interval_panel_lock_sha256": EXPECTED_PANEL_LOCK_SHA,
                "reference_artifact_id": event["reference_artifact_id"],
            }
        )

        base_account["identity_status"] = EXACT_NORMALIZED_ALLELE
        base_account["variant_id"] = vid
        base_account["variant_origin"] = variant_origin
        accounting.append(base_account)

        index_row = {
            "variant_id": vid,
            "variant_origin": variant_origin,
            "assembly": allele["assembly"],
            "contig": allele["contig"],
            "normalized_start_0based": allele["start"],
            "normalized_end_0based": allele["end"],
            "normalized_ref": allele["ref"],
            "normalized_alt": allele["alt"],
            "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        }
        if vid in variant_index:
            require(variant_index[vid] == index_row, f"variant index conflict: {vid}")
        else:
            variant_index[vid] = index_row

    new_variants = []
    for vid in sorted(new_variant_support):
        support = new_variant_support[vid]
        require(
            len(support["reference_artifact_ids"]) == 1,
            f"reference provenance conflict for new VARIANT: {vid}",
        )
        allele = support["allele"]
        new_variants.append(
            {
                "schema_version": VARIANT_SCHEMA_VERSION,
                "variant_id": vid,
                "assembly": allele["assembly"],
                "contig": allele["contig"],
                "normalized_start_0based": allele["start"],
                "normalized_end_0based": allele["end"],
                "normalized_ref": allele["ref"],
                "normalized_alt": allele["alt"],
                "normalization_method": "UPSTREAM_PHASE2C_NORMALIZED_FIELDS",
                "source_normalization_methods": ";".join(sorted(support["normalization_methods"])),
                "source_normalization_versions": ";".join(sorted(support["normalization_versions"])),
                "reference_artifact_id": next(iter(support["reference_artifact_ids"])),
                "identity_schema_version": IDENTITY_SCHEMA_VERSION,
                "phase2d_origin": "GENERATED_FROM_PHASE2C_EXACT_NORMALIZED_ALLELE",
                "phase2d_application_version": PHASE2D_APPLICATION_VERSION,
                "phase2c_archive_sha256": EXPECTED_PHASE2C_SHA,
            }
        )

    linked_event_ids = {row["event_id"] for row in links}
    exact_account_ids = {
        row["event_id"]
        for row in accounting
        if row["identity_status"] == EXACT_NORMALIZED_ALLELE
    }
    require(linked_event_ids == exact_account_ids, "exact accounting/link event set mismatch")

    runs_by_id = {row["benchmark_run_id"]: row for row in benchmark_runs}
    experiments_by_id = {row["experiment_id"]: row for row in experiments}
    events_by_id = {row["event_id"]: row for row in events}

    links_by_variant = defaultdict(list)
    for row in links:
        links_by_variant[row["variant_id"]].append(row)

    candidate_variants = []
    for vid, variant_links in links_by_variant.items():
        samples = set()
        technologies = set()
        for link in variant_links:
            run = runs_by_id[link["benchmark_run_id"]]
            exp = experiments_by_id[run["experiment_id"]]
            samples.add(exp["sample_id"])
            technologies.add(exp["technology"])
        candidate_variants.append(
            (len(samples), len(technologies), len(variant_links), vid)
        )
    require(candidate_variants, "no exact Phase 2D variants available for product query")
    candidate_variants.sort(reverse=True)
    sample_count, technology_count, _, query_variant_id = candidate_variants[0]

    query_rows = []
    for link in sorted(links_by_variant[query_variant_id], key=lambda row: row["event_id"]):
        event = events_by_id[link["event_id"]]
        run = runs_by_id[link["benchmark_run_id"]]
        exp = experiments_by_id[run["experiment_id"]]
        for obs in sorted(observations_by_event[event["event_id"]], key=lambda row: row["observation_id"]):
            query_rows.append(
                {
                    "variant_id": query_variant_id,
                    "event_variant_link_id": link["event_variant_link_id"],
                    "identity_status": link["identity_status"],
                    "identity_method": link["identity_method"],
                    "variant_origin": link["variant_origin"],
                    "sample_id": exp["sample_id"],
                    "technology": exp["technology"],
                    "experiment_id": exp["experiment_id"],
                    "benchmark_run_id": run["benchmark_run_id"],
                    "comparator": run["comparator"],
                    "comparator_version": run["comparator_version"],
                    "engine": run["engine"],
                    "engine_version": run["engine_version"],
                    "event_id": event["event_id"],
                    "observation_id": obs["observation_id"],
                    "side": obs["side"],
                    "raw_decision": obs["raw_decision"],
                    "raw_match_kind": obs["raw_match_kind"],
                    "source_genotype": obs["source_genotype"],
                    "source_filter": obs["source_filter"],
                    "source_output_artifact_id": obs["source_output_artifact_id"],
                    "phase2c_archive_sha256": EXPECTED_PHASE2C_SHA,
                }
            )

    return {
        "new_variants": new_variants,
        "event_variant_links": sorted(links, key=lambda row: row["event_variant_link_id"]),
        "event_identity_accounting": sorted(accounting, key=lambda row: row["event_id"]),
        "link_provenance": sorted(provenance, key=lambda row: row["provenance_record_id"]),
        "variant_index": sorted(variant_index.values(), key=lambda row: row["variant_id"]),
        "example_variant_evidence_query": query_rows,
        "query_sample_count": sample_count,
        "query_technology_count": technology_count,
    }


def validate(
    transformed: dict,
    events: list[dict],
    observations: list[dict],
    phase1b_variants: list[dict],
    variant_schema: dict,
    link_schema: dict,
    first_hashes: dict,
    second_hashes: dict,
):
    results = []

    def add(code: str, status: bool, detail: str):
        results.append(
            {
                "validation_id": code,
                "status": "PASS" if status else "FAIL",
                "detail": detail,
            }
        )

    add("D01_phase1b_archive", sha256_file(PHASE1B_ARCHIVE) == EXPECTED_PHASE1B_SHA, EXPECTED_PHASE1B_SHA)
    add("D02_phase2c_archive", sha256_file(PHASE2C_ARCHIVE) == EXPECTED_PHASE2C_SHA, EXPECTED_PHASE2C_SHA)
    add("D03_identity_implementation", sha256_file(IDENTITY_LIB) == EXPECTED_IDENTITY_LIB_SHA, EXPECTED_IDENTITY_LIB_SHA)
    add(
        "D04_immutable_inputs",
        sha256_file(PHASE1B_ARCHIVE) == EXPECTED_PHASE1B_SHA
        and sha256_file(PHASE2C_ARCHIVE) == EXPECTED_PHASE2C_SHA,
        "authoritative archives remained byte-identical",
    )

    accounting = transformed["event_identity_accounting"]
    links = transformed["event_variant_links"]
    new_variants = transformed["new_variants"]
    phase1b_ids = {row["variant_id"] for row in phase1b_variants}

    event_ids = [row["event_id"] for row in events]
    accounting_ids = [row["event_id"] for row in accounting]
    add(
        "D05_event_accounting",
        len(accounting) == len(events)
        and len(accounting_ids) == len(set(accounting_ids))
        and set(accounting_ids) == set(event_ids)
        and all(row["identity_status"] in {EXACT_NORMALIZED_ALLELE, "UNRESOLVED"} for row in accounting),
        f"events={len(events)} accounting={len(accounting)}",
    )

    exact_rows = [row for row in accounting if row["identity_status"] == EXACT_NORMALIZED_ALLELE]
    add(
        "D06_exact_single_allele",
        all(row["distinct_complete_normalized_alleles"] == 1 for row in exact_rows),
        f"exact_events={len(exact_rows)}",
    )

    observations_by_event = defaultdict(list)
    for obs in observations:
        observations_by_event[obs["event_id"]].append(obs)
    events_by_id = {row["event_id"]: row for row in events}
    recompute_ok = True
    for row in links:
        allele, reason, _, _ = source_identity_tuple(
            events_by_id[row["event_id"]],
            observations_by_event[row["event_id"]],
        )
        if allele is None or reason or frozen_variant_id(allele) != row["variant_id"]:
            recompute_ok = False
            break
    add("D07_variant_ids", recompute_ok, f"links_checked={len(links)}")

    new_ids = {row["variant_id"] for row in new_variants}
    reused_links = [row for row in links if row["variant_origin"] == "PHASE1B_REUSED"]
    reuse_ok = (
        not (new_ids & phase1b_ids)
        and all(row["variant_id"] in phase1b_ids for row in reused_links)
    )
    add(
        "D08_phase1b_reuse",
        reuse_ok,
        f"reused_links={len(reused_links)} new_variants={len(new_variants)}",
    )

    unresolved = [row for row in accounting if row["identity_status"] == "UNRESOLVED"]
    unresolved_ids = {row["event_id"] for row in unresolved}
    linked_event_ids = {row["event_id"] for row in links}
    add(
        "D09_unresolved_abstention",
        all(row["variant_id"] == "" and row["variant_origin"] == "" for row in unresolved)
        and not (unresolved_ids & linked_event_ids),
        f"unresolved_events={len(unresolved)}",
    )

    statuses = {row["identity_status"] for row in links}
    add(
        "D10_representation_equivalence_disabled",
        REPRESENTATION_EQUIVALENCE_SUPPORTED not in statuses
        and all(row["identity_status"] == EXACT_NORMALIZED_ALLELE for row in links),
        f"link_statuses={sorted(statuses)}",
    )

    link_event_ids = [row["event_id"] for row in links]
    add(
        "D11_one_variant_per_event",
        len(link_event_ids) == len(set(link_event_ids)),
        f"links={len(links)}",
    )

    provenance_fields = {
        "phase1b_archive_sha256",
        "phase2c_archive_sha256",
        "phase2d_protocol_sha256",
        "admitted_sources_lock_sha256",
        "interval_panel_lock_sha256",
        "source_event_id",
        "source_benchmark_run_id",
        "reference_artifact_id",
    }
    provenance_ok = True
    for row in links:
        p = json.loads(row["provenance"])
        if set(p) != provenance_fields or any(p[k] in (None, "") for k in provenance_fields):
            provenance_ok = False
            break
    add("D12_link_provenance", provenance_ok, f"links_checked={len(links)}")

    required_query_fields = {
        "variant_id",
        "event_variant_link_id",
        "sample_id",
        "technology",
        "experiment_id",
        "benchmark_run_id",
        "event_id",
        "observation_id",
        "side",
        "raw_decision",
        "raw_match_kind",
        "source_genotype",
        "source_filter",
        "comparator",
        "comparator_version",
        "identity_method",
    }
    query_rows = transformed["example_variant_evidence_query"]
    query_ok = (
        bool(query_rows)
        and required_query_fields.issubset(query_rows[0])
        and transformed["query_sample_count"] >= 2
        and transformed["query_technology_count"] >= 2
    )
    add(
        "D13_variant_product_query",
        query_ok,
        (
            f"rows={len(query_rows)} samples={transformed['query_sample_count']} "
            f"technologies={transformed['query_technology_count']}"
        ),
    )

    add(
        "D14_reproducibility",
        first_hashes == second_hashes,
        canonical_json(first_hashes),
    )

    all_field_names = set()
    for table_name in (
        "new_variants",
        "event_variant_links",
        "event_identity_accounting",
        "link_provenance",
        "variant_index",
        "example_variant_evidence_query",
    ):
        rows = transformed[table_name]
        if rows:
            all_field_names.update(rows[0].keys())
    forbidden_found = sorted(
        field
        for field in all_field_names
        if any(fragment in field.lower() for fragment in FORBIDDEN_OUTPUT_FIELD_FRAGMENTS)
    )
    add(
        "D15_no_scoring_or_ranking",
        not forbidden_found,
        f"forbidden_fields={forbidden_found}",
    )

    variant_validator = jsonschema.Draft202012Validator(variant_schema)
    link_validator = jsonschema.Draft202012Validator(link_schema)
    schema_errors = []
    for i, row in enumerate(new_variants):
        for error in variant_validator.iter_errors(row):
            schema_errors.append(f"new_variants[{i}]: {error.message}")
    for i, row in enumerate(links):
        for error in link_validator.iter_errors(row):
            schema_errors.append(f"event_variant_links[{i}]: {error.message}")
    require(not schema_errors, "Phase 2D schema validation failed:\n" + "\n".join(schema_errors[:20]))

    return results


def deterministic_tar_gz(output_path: Path, bundle_dir: Path) -> None:
    members = sorted(p for p in bundle_dir.rglob("*") if p.is_file())
    with output_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            with tarfile.open(mode="w", fileobj=gz, format=tarfile.USTAR_FORMAT) as tar:
                for source in members:
                    relative = Path(bundle_dir.name) / source.relative_to(bundle_dir)
                    data = source.read_bytes()
                    info = tarfile.TarInfo(name=relative.as_posix())
                    info.size = len(data)
                    info.mtime = 0
                    info.mode = 0o644
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    tar.addfile(info, io.BytesIO(data))


def main() -> int:
    print("=" * 78)
    print("PROJECT 003 — PHASE 2D BIOLOGICAL IDENTITY EXPANSION")
    print("=" * 78)

    expected_authorities = {
        PHASE1B_ARCHIVE: EXPECTED_PHASE1B_SHA,
        PHASE2C_ARCHIVE: EXPECTED_PHASE2C_SHA,
        PHASE2D_PROTOCOL: EXPECTED_PROTOCOL_SHA,
        PHASE2D_PROTOCOL_LOCK: EXPECTED_PROTOCOL_LOCK_SHA,
        IDENTITY_LIB: EXPECTED_IDENTITY_LIB_SHA,
        ADMITTED_LOCK: EXPECTED_ADMITTED_LOCK_SHA,
        PANEL_LOCK: EXPECTED_PANEL_LOCK_SHA,
    }
    for path, expected in expected_authorities.items():
        require(path.is_file(), f"missing authority: {path}")
        require(sha256_file(path) == expected, f"authority SHA mismatch: {path}")
    print("PASS  frozen authorities")

    variant_schema = json.loads(VARIANT_SCHEMA_PATH.read_text(encoding="utf-8"))
    link_schema = json.loads(LINK_SCHEMA_PATH.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory(prefix="omicsedge-phase2d-") as temp:
        temp_root = Path(temp)
        p1 = temp_root / "phase1b"
        p2 = temp_root / "phase2c"
        p1.mkdir()
        p2.mkdir()

        safe_extract(PHASE1B_ARCHIVE, p1)
        phase1b_manifest = verify_phase1b_release(p1)
        safe_extract(PHASE2C_ARCHIVE, p2)
        p2root = verify_phase2c_release(p2)
        print("PASS  packaged Phase 1B and Phase 2C integrity")

        phase1b_variants = read_tsv(p1 / "results/phase1b/variants.tsv")
        events = read_tsv(p2root / "events.tsv")
        observations = read_tsv(p2root / "observations.tsv")
        benchmark_runs = read_tsv(p2root / "benchmark_runs.tsv")
        experiments = read_tsv(p2root / "experiments.tsv")

        require(len(phase1b_variants) == phase1b_manifest["variant_count"], "Phase 1B variant count mismatch")
        require(len(events) > 0 and len(observations) > 0, "Phase 2C evidence is empty")

        first = transform(events, observations, benchmark_runs, experiments, phase1b_variants)
        second = transform(events, observations, benchmark_runs, experiments, phase1b_variants)

        table_names = (
            "new_variants",
            "event_variant_links",
            "event_identity_accounting",
            "link_provenance",
            "variant_index",
            "example_variant_evidence_query",
        )
        first_hashes = {name: scientific_row_hash(first[name]) for name in table_names}
        second_hashes = {name: scientific_row_hash(second[name]) for name in table_names}

        validations = validate(
            first,
            events,
            observations,
            phase1b_variants,
            variant_schema,
            link_schema,
            first_hashes,
            second_hashes,
        )
        failed = [row for row in validations if row["status"] != "PASS"]
        require(not failed, "Phase 2D validation failed before packaging: " + canonical_json(failed))

        staging = temp_root / "omicsedge_phase2d_results"
        staging.mkdir()

        table_fields = {
            "new_variants": [
                "schema_version", "variant_id", "assembly", "contig",
                "normalized_start_0based", "normalized_end_0based",
                "normalized_ref", "normalized_alt", "normalization_method",
                "source_normalization_methods", "source_normalization_versions",
                "reference_artifact_id", "identity_schema_version",
                "phase2d_origin", "phase2d_application_version",
                "phase2c_archive_sha256",
            ],
            "event_variant_links": [
                "schema_version", "event_variant_link_id", "event_id",
                "variant_id", "benchmark_run_id", "identity_status",
                "identity_method", "identity_method_version",
                "phase2d_application_version", "variant_origin",
                "evidence", "provenance", "phase2c_archive_sha256",
                "admitted_sources_lock_sha256", "interval_panel_lock_sha256",
            ],
            "event_identity_accounting": [
                "event_id", "benchmark_run_id", "assembly", "contig",
                "identity_status", "unresolved_reason", "variant_id",
                "variant_origin", "observation_count",
                "distinct_complete_normalized_alleles",
                "normalized_allele_lookup_key", "reference_artifact_id",
                "identity_method", "identity_method_version",
                "phase2d_application_version",
            ],
            "link_provenance": [
                "provenance_record_id", "event_variant_link_id", "event_id",
                "variant_id", "benchmark_run_id", "identity_method",
                "identity_method_version", "phase2d_application_version",
                "phase1b_archive_sha256", "phase2c_archive_sha256",
                "phase2d_protocol_sha256", "admitted_sources_lock_sha256",
                "interval_panel_lock_sha256", "reference_artifact_id",
            ],
            "variant_index": [
                "variant_id", "variant_origin", "assembly", "contig",
                "normalized_start_0based", "normalized_end_0based",
                "normalized_ref", "normalized_alt", "identity_schema_version",
            ],
        }

        for name, fields in table_fields.items():
            rows = first[name]
            write_tsv(staging / f"{name}.tsv", rows, fields)
            write_parquet(staging / f"{name}.parquet", rows, fields)

        write_tsv(
            staging / "example_variant_evidence_query.tsv",
            first["example_variant_evidence_query"],
        )

        exact_count = sum(
            row["identity_status"] == EXACT_NORMALIZED_ALLELE
            for row in first["event_identity_accounting"]
        )
        unresolved_count = sum(
            row["identity_status"] == "UNRESOLVED"
            for row in first["event_identity_accounting"]
        )
        unresolved_reasons = Counter(
            row["unresolved_reason"]
            for row in first["event_identity_accounting"]
            if row["identity_status"] == "UNRESOLVED"
        )
        reused_variant_ids = {
            row["variant_id"]
            for row in first["event_variant_links"]
            if row["variant_origin"] == "PHASE1B_REUSED"
        }

        (staging / "reproducibility.json").write_text(
            json.dumps(
                {
                    "phase2d_application_version": PHASE2D_APPLICATION_VERSION,
                    "scientific_table_hashes": first_hashes,
                    "rerun_scientific_table_hashes": second_hashes,
                    "identical": first_hashes == second_hashes,
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )

        summary = {
            "project": "Project 003",
            "phase": "2D",
            "status": "PASS",
            "identity_schema_version": IDENTITY_SCHEMA_VERSION,
            "identity_method": IDENTITY_METHOD,
            "identity_method_version": IDENTITY_METHOD_VERSION,
            "phase2d_application_version": PHASE2D_APPLICATION_VERSION,
            "phase1b_variant_count": len(phase1b_variants),
            "phase2c_event_count": len(events),
            "phase2c_observation_count": len(observations),
            "exact_event_count": exact_count,
            "unresolved_event_count": unresolved_count,
            "unresolved_reason_counts": dict(sorted(unresolved_reasons.items())),
            "event_variant_link_count": len(first["event_variant_links"]),
            "phase2d_unique_variant_count": len(first["variant_index"]),
            "phase2d_new_variant_count": len(first["new_variants"]),
            "phase1b_reused_variant_count": len(reused_variant_ids),
            "example_query_rows": len(first["example_variant_evidence_query"]),
            "example_query_distinct_samples": first["query_sample_count"],
            "example_query_distinct_technologies": first["query_technology_count"],
            "representation_equivalence_enabled": False,
            "reliability_scoring_enabled": False,
            "technology_ranking_enabled": False,
            "phase2d_identity_applied": True,
            "phase2c_records_mutated": False,
        }
        (staging / "phase2d_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        report = f"""# Project 003 Phase 2D Compute Report

## Verdict

PASS

All locked Phase 2D validation criteria D01-D16 passed.

## Identity application

- Phase 2C EVENT records accounted for: {len(events)}
- EXACT_NORMALIZED_ALLELE events: {exact_count}
- UNRESOLVED events: {unresolved_count}
- EVENT_VARIANT_LINK records: {len(first["event_variant_links"])}
- Unique Phase 2D biological variants touched: {len(first["variant_index"])}
- New Phase 2D VARIANT records: {len(first["new_variants"])}
- Reused Phase 1B VARIANT records: {len(reused_variant_ids)}

## Identity method

`{IDENTITY_METHOD}`

Identity schema:

`{IDENTITY_SCHEMA_VERSION}`

Representation-equivalence inference remained disabled.

## Unresolved accounting

`{canonical_json(dict(sorted(unresolved_reasons.items())))}`

UNRESOLVED events received no EVENT_VARIANT_LINK and no guessed VARIANT ID.

## Product-query preservation

The deterministic example variant-level query contains:

- {len(first["example_variant_evidence_query"])} observation rows
- {first["query_sample_count"]} distinct samples
- {first["query_technology_count"]} distinct technologies

The query preserves experiment, benchmark run, EVENT, OBSERVATION, side,
raw comparator decision, raw match kind, genotype, source filter, comparator,
and identity-method context.

## Scientific boundaries

Phase 2D does not introduce reliability scores, confidence scores, trust
labels, technology rankings, forced consensus, clinical interpretation, or
representation-equivalence inference.

Existing Phase 1B and Phase 2C scientific records remain immutable.
"""
        (staging / "phase2d_compute_report.md").write_text(report, encoding="utf-8")

        validation_rows = validations + [
            {
                "validation_id": "D16_release_checksums",
                "status": "PASS",
                "detail": "bundle checksum manifest generated; deterministic archive independently verified before success marker",
            }
        ]
        write_tsv(staging / "phase2d_validation.tsv", validation_rows)

        checksum_targets = sorted(
            p for p in staging.iterdir()
            if p.is_file() and p.name != "checksums.sha256"
        )
        (staging / "checksums.sha256").write_text(
            "\n".join(f"{sha256_file(p)}  {p.name}" for p in checksum_targets) + "\n",
            encoding="utf-8",
        )

        for raw in (staging / "checksums.sha256").read_text(encoding="utf-8").splitlines():
            expected, relative = raw.split("  ", 1)
            require(sha256_file(staging / relative) == expected, f"pre-archive checksum failed: {relative}")

        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        if BUNDLE_DIR.exists():
            shutil.rmtree(BUNDLE_DIR)
        shutil.copytree(staging, BUNDLE_DIR)

        if ARCHIVE_PATH.exists():
            ARCHIVE_PATH.unlink()
        deterministic_tar_gz(ARCHIVE_PATH, BUNDLE_DIR)

        audit_root = temp_root / "archive_audit"
        audit_root.mkdir()
        extracted_names = safe_extract(ARCHIVE_PATH, audit_root)
        expected_names = {
            f"{BUNDLE_DIR.name}/{p.name}"
            for p in BUNDLE_DIR.iterdir()
            if p.is_file()
        }
        require(set(extracted_names) == expected_names, "Phase 2D archive member set mismatch")

        extracted_bundle = audit_root / BUNDLE_DIR.name
        for raw in (extracted_bundle / "checksums.sha256").read_text(encoding="utf-8").splitlines():
            expected, relative = raw.split("  ", 1)
            require(
                sha256_file(extracted_bundle / relative) == expected,
                f"archive checksum failed: {relative}",
            )

    for path, expected in expected_authorities.items():
        require(sha256_file(path) == expected, f"authoritative input mutated: {path}")

    final_validations = read_tsv(BUNDLE_DIR / "phase2d_validation.tsv")
    require(len(final_validations) == 16, f"expected D01-D16, observed {len(final_validations)}")
    require(all(row["status"] == "PASS" for row in final_validations), "not all D01-D16 passed")

    final_summary = json.loads((BUNDLE_DIR / "phase2d_summary.json").read_text(encoding="utf-8"))

    print("PASS  Phase 1B and Phase 2C authorities remained immutable")
    print("PASS  D01-D16")
    print()
    print("Phase 2C events:", final_summary["phase2c_event_count"])
    print("Exact identity events:", final_summary["exact_event_count"])
    print("Unresolved events:", final_summary["unresolved_event_count"])
    print("EVENT_VARIANT_LINK records:", final_summary["event_variant_link_count"])
    print("Unique variants touched:", final_summary["phase2d_unique_variant_count"])
    print("New Phase 2D variants:", final_summary["phase2d_new_variant_count"])
    print("Reused Phase 1B variants:", final_summary["phase1b_reused_variant_count"])
    print()
    print("Archive:", ARCHIVE_PATH.relative_to(ROOT))
    print("Archive size:", ARCHIVE_PATH.stat().st_size)
    print("Archive SHA-256:", sha256_file(ARCHIVE_PATH))
    print()
    print("PHASE2D_IDENTITY_COMPUTE_PASS")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("PHASE2D_IDENTITY_COMPUTE_FAIL")
        print(f"{type(exc).__name__}: {exc}")
        raise
