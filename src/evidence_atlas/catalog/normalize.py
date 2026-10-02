"""Rules-only mapping from ENA metadata into the frozen M0 entity model."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from .provenance import parameters_sha256, sha256_bytes


SCHEMA_VERSION = "atlas-0.1.0"
NORMALIZER = {"id": "m1a-catalog-rules", "version": "0.1.0"}
RUN_RE = re.compile(r"^[SED]RR[0-9]{6,}$")
EXPERIMENT_RE = re.compile(r"^[SED]RX[0-9]{6,}$")
STUDY_RE = re.compile(r"^[SED]RP[0-9]{6,}$")
BIOSAMPLE_RE = re.compile(r"^SAM(?:N|EA|D)[0-9]+$")
BIOPROJECT_RE = re.compile(r"^PRJ(?:NA|EB|DB)[0-9]+$")


def _key(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.strip().casefold())


def _value(raw: str | None, value: str | int, method: str, confidence: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "raw_value": raw,
        "value": value,
        "method": method,
        "confidence": confidence,
    }
    if method in {"SOURCE_CONTROLLED", "RULE_EXACT", "RULE_PATTERN"}:
        result["normalizer"] = NORMALIZER
    return result


def unresolved(raw: str | None) -> dict[str, Any]:
    return _value(raw, "UNKNOWN", "UNRESOLVED", 0)


def source_value(raw: str | None) -> dict[str, Any]:
    return unresolved(raw) if raw in {None, ""} else _value(raw, raw, "SOURCE_CONTROLLED", 1.0)


class TechnologyNormalizer:
    """Exact-only normalizer backed by the frozen M0 technology taxonomy."""

    PLATFORM_RULES = {
        "illumina": ("short_read_sbs", "illumina"),
        "oxford nanopore": ("nanopore", "oxford_nanopore"),
        "pacbio smrt": ("smrt", "pacbio"),
        "ion torrent": ("semiconductor", "thermo_ion_torrent"),
        "ls454": ("pyrosequencing", "roche_454"),
        "capillary": ("capillary_electrophoresis", "capillary_vendors"),
        "complete genomics": ("short_read_dnb", "mgi"),
        "bgiseq": ("short_read_dnb", "mgi"),
        "dnbseq": ("short_read_dnb", "mgi"),
        "element": ("short_read_avidity", "element"),
        "ultima": ("short_read_flow_sbs", "ultima"),
    }

    def __init__(self, taxonomy: Mapping[str, Any]) -> None:
        self.families = {row["id"]: row for row in taxonomy["instrument_families"]}
        self.models = {row["id"]: row for row in taxonomy["instrument_models"]}
        self.model_aliases: dict[str, str] = {}
        self.family_aliases: dict[str, str] = {}
        for row in taxonomy["instrument_models"]:
            for alias in [row["label"], *row["source_aliases"]]:
                self.model_aliases[_key(alias)] = row["id"]
        for row in taxonomy["instrument_families"]:
            for alias in [row["label"], *row["family_level_aliases"]]:
                self.family_aliases[_key(alias)] = row["id"]

    @classmethod
    def from_path(cls, path: Path) -> "TechnologyNormalizer":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def normalize(self, instrument_platform: str | None, instrument_model: str | None) -> dict[str, Any]:
        platform_raw = instrument_platform or None
        model_raw = instrument_model or None
        model_id = self.model_aliases.get(_key(model_raw)) if model_raw else None
        family_id = None
        normalized_model: dict[str, Any]
        if model_id:
            family_id = self.models[model_id]["instrument_family_id"]
            normalized_model = _value(model_raw, model_id, "RULE_EXACT", 1.0)
        else:
            family_id = self.family_aliases.get(_key(model_raw)) if model_raw else None
            normalized_model = (
                _value(model_raw, "UNSPECIFIED", "RULE_EXACT", 1.0) if family_id else unresolved(model_raw)
            )

        if family_id:
            family = self.families[family_id]
            technology_id = family["technology_family_id"]
            vendor_id = family["vendor_id"]
            family_value = _value(model_raw, family_id, "RULE_EXACT", 1.0)
            technology_value = _value(model_raw, technology_id, "RULE_EXACT", 1.0)
            vendor_value = _value(model_raw, vendor_id, "RULE_EXACT", 1.0)
        else:
            platform_rule = self.PLATFORM_RULES.get(_key(platform_raw)) if platform_raw else None
            if platform_rule:
                technology_id, vendor_id = platform_rule
                technology_value = _value(platform_raw, technology_id, "RULE_EXACT", 1.0)
                vendor_value = _value(platform_raw, vendor_id, "RULE_EXACT", 1.0)
            else:
                technology_value = unresolved(platform_raw)
                vendor_value = unresolved(platform_raw)
            family_value = unresolved(model_raw)

        return {
            "technology_family": technology_value,
            "vendor": vendor_value,
            "instrument_family": family_value,
            "instrument_model": normalized_model,
            "chemistry": [],
            "read_mode": unresolved(None),
        }


def _integer(raw: str | None) -> int | None:
    if raw in {None, ""}:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def _identifier(raw: str | None, pattern: re.Pattern[str]) -> str | None:
    return raw if raw and pattern.fullmatch(raw) else None


def _file_parts(raw: str | None) -> list[str]:
    return [] if not raw else raw.split(";")


def _accession_parts(*raw_values: str | None) -> list[str]:
    values: list[str] = []
    for raw in raw_values:
        for value in _file_parts(raw):
            if value and value not in values:
                values.append(value)
    return values


def _ftp_uri(value: str) -> str:
    return value if "://" in value else f"ftp://{value}"


def _file_artifacts(row: Mapping[str, str], run_id: str) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    specs = (
        ("fastq", "FASTQ", "fastq_ftp", "fastq_md5", "fastq_bytes"),
        ("submitted", "OTHER", "submitted_ftp", "submitted_md5", "submitted_bytes"),
    )
    seen: set[str] = set()
    for label, kind, url_field, checksum_field, size_field in specs:
        urls = _file_parts(row.get(url_field))
        checksums = _file_parts(row.get(checksum_field))
        sizes = _file_parts(row.get(size_field))
        for index, url in enumerate(urls, start=1):
            uri = _ftp_uri(url)
            if uri in seen:
                continue
            seen.add(uri)
            md5 = checksums[index - 1].lower() if index <= len(checksums) else ""
            size = _integer(sizes[index - 1]) if index <= len(sizes) else None
            checksum: str | dict[str, str] = "UNKNOWN"
            if re.fullmatch(r"[0-9a-f]{32}", md5):
                checksum = {"algorithm": "md5", "value": md5, "source": "PUBLISHER"}
            token = sha256_bytes(uri.encode("utf-8"))[:16]
            artifacts.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "artifact_id": f"artifact:{run_id.split(':', 1)[1]}:{label}:{index}:{token}",
                    "artifact_kind": kind,
                    "origin": "SOURCE_HOSTED",
                    "uri": uri,
                    "size_bytes": size,
                    "checksum": checksum,
                    "derived_from": [{"kind": "SEQUENCING_RUN", "id": run_id}],
                    "availability": "PUBLIC",
                }
            )
    return artifacts


def _read_type(layout: Mapping[str, Any], technology: Mapping[str, Any]) -> dict[str, Any]:
    raw = layout["raw_value"]
    if layout["value"] == "PAIRED" and technology["value"] not in {"UNKNOWN", "nanopore", "smrt"}:
        return _value(raw, "SHORT_PAIRED_END", "RULE_EXACT", 1.0)
    if layout["value"] == "SINGLE" and technology["value"] in {"nanopore", "smrt"}:
        return _value(raw, "LONG_SINGLE_MOLECULE", "RULE_EXACT", 1.0)
    if layout["value"] == "SINGLE" and technology["value"] != "UNKNOWN":
        return _value(raw, "SHORT_SINGLE_END", "RULE_EXACT", 1.0)
    return unresolved(raw)


def normalize_ena_record(
    row: Mapping[str, str],
    *,
    technology: TechnologyNormalizer,
    retrieved_at: str,
    endpoint: str,
    parameters: Mapping[str, Any],
    response_sha256: str,
    raw_snapshot_uri: str,
) -> dict[str, Any]:
    """Map one ENA row to frozen M0 entities plus audit-only raw metadata."""

    accession = row.get("run_accession", "")
    if not RUN_RE.fullmatch(accession):
        raise ValueError(f"invalid INSDC run accession: {accession!r}")
    run_id = f"run:{accession.lower()}"
    source_record_id = f"source-record:ena:{accession.lower()}:{response_sha256[:16]}"
    catalog_record_id = f"catalog-record:insdc:{accession.lower()}"
    platform = technology.normalize(row.get("instrument_platform"), row.get("instrument_model"))

    sample_values = _accession_parts(row.get("sample_accession"), row.get("secondary_sample_accession"))
    biosamples = [value for value in sample_values if BIOSAMPLE_RE.fullmatch(value)]
    insdc_samples = [value for value in sample_values if value not in biosamples]
    biosample = biosamples[0] if len(biosamples) == 1 else None
    sample_accession = insdc_samples[0] if len(insdc_samples) == 1 else None
    multiple_samples = len(biosamples) > 1 or (not biosamples and len(insdc_samples) > 1)
    sample_token = None if multiple_samples else (biosample or sample_accession)
    sample_id = f"sample:{sample_token.lower()}" if sample_token else f"sample:unknown:{accession.lower()}"
    study_values = _accession_parts(row.get("study_accession"), row.get("secondary_study_accession"))
    bioprojects = [value for value in study_values if BIOPROJECT_RE.fullmatch(value)]
    insdc_studies = [value for value in study_values if STUDY_RE.fullmatch(value)]
    bioproject = bioprojects[0] if len(bioprojects) == 1 else None
    study_accession = insdc_studies[0] if len(insdc_studies) == 1 else None
    study_token = bioproject or study_accession
    study_id = f"study:{study_token.lower()}" if study_token else f"study:unknown:{accession.lower()}"

    library = {
        "strategy": source_value(row.get("library_strategy")),
        "source": source_value(row.get("library_source")),
        "selection": source_value(row.get("library_selection")),
        "layout": source_value(row.get("library_layout")),
    }
    artifacts = _file_artifacts(row, run_id)
    run: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "run_accession": accession,
        "sample_id": sample_id,
        "study_id": study_id,
        "library": library,
        "assay": source_value(row.get("library_strategy")),
        "platform": platform,
        "read_type": _read_type(library["layout"], platform["technology_family"]),
        "basecaller": {
            "name": unresolved(None),
            "version": "UNKNOWN",
            "model": "UNKNOWN",
        },
        "total_bases": _integer(row.get("base_count")),
        "read_count": _integer(row.get("read_count")),
        "coverage": {"status": "UNKNOWN", "value": None},
        "public_file_artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
        "source_record_ids": [source_record_id],
    }
    experiment = _identifier(row.get("experiment_accession"), EXPERIMENT_RE)
    if experiment:
        run["experiment_accession"] = experiment

    source_record = {
        "schema_version": SCHEMA_VERSION,
        "source_record_id": source_record_id,
        "source_id": "ena",
        "source_accession": accession,
        "canonical_accession": accession,
        "mirror_group_id": "insdc",
        "retrieved_at": retrieved_at,
        "query": {
            "endpoint": endpoint,
            "parameters": dict(sorted(parameters.items())),
            "parameters_sha256": parameters_sha256(parameters),
        },
        "raw_snapshot_sha256": response_sha256,
        "raw_snapshot_uri": raw_snapshot_uri,
        "source_status": "PUBLIC",
        "terms": {
            "terms_id": "ena-current-terms-unreviewed-m1a",
            "terms_url": "https://www.ebi.ac.uk/about/terms-of-use",
            "compatibility": "UNREVIEWED",
            "notes": "M1A catalog discovery only; no eligibility conclusion.",
        },
    }

    unresolved_gates = ["assembly_id"]
    if not sample_token:
        unresolved_gates.append("sample_id")
    for field, normalized in (
        ("technology_family_id", platform["technology_family"]),
        ("vendor_id", platform["vendor"]),
        ("instrument_family_id", platform["instrument_family"]),
        ("library_strategy", library["strategy"]),
        ("library_source", library["source"]),
    ):
        if normalized["value"] == "UNKNOWN":
            unresolved_gates.append(field)
    catalog_record = {
        "schema_version": SCHEMA_VERSION,
        "record_id": catalog_record_id,
        "record_version": 1,
        "record_kind": "SEQUENCING_RUN",
        "entity_ref": {"kind": "SEQUENCING_RUN", "id": run_id},
        "layer": "PUBLIC_DATA_CATALOG",
        "eligibility_state": "CATALOGUED",
        "state_history": [
            {
                "from_state": None,
                "to_state": "CATALOGUED",
                "at": retrieved_at,
                "actor": {"type": "SOURCE_SYNC", "id": "m1a-ena-catalog", "version": "0.1.0"},
                "reason": "Metadata discovered in bounded M1A ENA pilot; not evaluated for evidence eligibility.",
                "policy_version": "0.2.0",
            }
        ],
        "normalization_state": "PARTIAL" if unresolved_gates else "NORMALIZED",
        "normalization_confidence": {
            "minimum_hard_gate_confidence": 0,
            "ml_only_hard_gate_fields": [],
            "unresolved_hard_gate_fields": sorted(unresolved_gates),
        },
        "discovered_at": retrieved_at,
        "last_seen_at": retrieved_at,
        "source_record_ids": [source_record_id],
        "duplicate_cluster_id": f"insdc-run:{accession.lower()}",
        "canonical_in_cluster": True,
        "terms": source_record["terms"],
    }

    tax_raw = row.get("tax_id") or None
    tax_id = _integer(tax_raw)
    taxon = _value(tax_raw, tax_id, "SOURCE_CONTROLLED", 1.0) if tax_id else unresolved(tax_raw)
    source_sample_relationships = [
        {
            "run_accession": accession,
            "sample_accession": value,
            "accession_type": "BIOSAMPLE" if value in biosamples else "INSDC_SAMPLE",
            "relationship": "SOURCE_REPORTED_SAMPLE",
            "source": "ena",
        }
        for value in sample_values
    ]
    return {
        "run_accession": accession,
        "sequencing_run": run,
        "source_record": source_record,
        "catalog_record": catalog_record,
        "derived_artifacts": artifacts,
        "taxonomy": {
            "raw_source_taxon_value": tax_raw,
            "normalized_ncbi_taxonomy_id": taxon,
            "scientific_name": row.get("scientific_name") or None,
            "normalization_provenance": {
                "authority": "NCBI Taxonomy identifier reported by ENA",
                "source_record_id": source_record_id,
            },
        },
        "accessions": {
            "experiment_accession": row.get("experiment_accession") or None,
            "study_accession": study_accession,
            "bioproject_accession": bioproject,
            "sample_accession": sample_accession,
            "biosample_accession": biosample,
            "sample_accessions": insdc_samples,
            "biosample_accessions": biosamples,
            "study_accessions": insdc_studies,
            "bioproject_accessions": bioprojects,
        },
        "source_sample_relationships": source_sample_relationships,
        "source_sample_cardinality": {
            "biosample_accession_count": len(biosamples),
            "insdc_sample_accession_count": len(insdc_samples),
            "normalization_status": (
                "MULTIPLE_SOURCE_SAMPLES"
                if multiple_samples
                else "ONE_SOURCE_SAMPLE"
                if sample_token
                else "UNKNOWN"
            ),
        },
        "public_release_date": row.get("first_public") or None,
        "raw_source_values": dict(sorted(row.items())),
        "normalization_provenance": {
            "method": "rules_only",
            "normalizer": NORMALIZER,
            "ml_used": False,
        },
    }


def deduplicate_by_run_accession(records: Sequence[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], int]:
    """Collapse mirrors/source duplicates by canonical INSDC run accession."""

    unique: dict[str, Mapping[str, Any]] = {}
    duplicates = 0
    for record in records:
        accession = str(record["run_accession"])
        if accession in unique:
            duplicates += 1
            continue
        unique[accession] = record
    return [unique[key] for key in sorted(unique)], duplicates
