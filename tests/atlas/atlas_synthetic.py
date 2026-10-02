"""SYNTHETIC fixtures for the M0 Evidence Atlas protocol tests.

Every record here is invented to exercise schema and lifecycle rules. URIs use
example.invalid and hashes are derived from fixed strings; none of these
records describe a real dataset or carry scientific meaning.
"""

from __future__ import annotations

import copy
import hashlib

from evidence_atlas import protocol

SV = protocol.SCHEMA_VERSION
T0 = "2026-10-01T00:00:00Z"


def fake_sha(label: str) -> str:
    return hashlib.sha256(f"SYNTHETIC:{label}".encode()).hexdigest()


def rule(raw, value, method="RULE_EXACT"):
    return {
        "raw_value": raw,
        "value": value,
        "method": method,
        "confidence": 1.0,
        "normalizer": {"id": "synthetic-rules", "version": "0.0.0"},
    }


def ml(raw, value, confidence):
    return {
        "raw_value": raw,
        "value": value,
        "method": "ML_PROPOSED",
        "confidence": confidence,
        "ml": {"model_id": "synthetic-model", "model_version": "0.0.0", "input_sha256": fake_sha(raw)},
    }


def unresolved(raw=None):
    return {"raw_value": raw, "value": "UNKNOWN", "method": "UNRESOLVED", "confidence": 0}


def terms(compatibility="COMPATIBLE"):
    out = {"terms_id": "synthetic-terms", "compatibility": compatibility}
    if compatibility != "UNREVIEWED":
        out["snapshot_sha256"] = fake_sha("terms")
        out["snapshot_retrieved_at"] = T0
    return out


def step(from_state, to_state, at, actor_type="SOFTWARE", **extra):
    entry = {
        "from_state": from_state,
        "to_state": to_state,
        "at": at,
        "actor": {"type": actor_type, "id": "synthetic-actor"},
        "reason": "synthetic transition",
        "policy_version": "0.2.0",
    }
    entry.update(extra)
    return entry


HARD_GATE_FIELDS = (
    "ncbi_taxonomy_id",
    "technology_family_id",
    "vendor_id",
    "instrument_family_id",
    "library_strategy",
    "library_source",
    "assembly_id",
    "sample_id",
    "access_class",
)


def authoritative_hard_gate_values() -> dict[str, dict]:
    """Every hard-gate field backed by source metadata or a deterministic rule."""
    return {f: rule(f"raw-{f}", f"value-{f}", "SOURCE_CONTROLLED") for f in HARD_GATE_FIELDS}


RELEASED_HISTORY = [
    step(None, "CATALOGUED", "2026-10-01T00:00:00Z", "SOURCE_SYNC"),
    step("CATALOGUED", "ELIGIBILITY_PENDING", "2026-10-01T01:00:00Z"),
    step("ELIGIBILITY_PENDING", "ELIGIBLE", "2026-10-01T02:00:00Z", assessment_id="assess-1"),
    step("ELIGIBLE", "VALIDATION_PENDING", "2026-10-01T03:00:00Z", "WORKFLOW"),
    step("VALIDATION_PENDING", "VALIDATED", "2026-10-01T04:00:00Z", "WORKFLOW"),
    step("VALIDATED", "RELEASED", "2026-10-01T05:00:00Z", "RELEASE_BUILD", release_version="1.1.0"),
]


def make_entities() -> dict[str, dict]:
    return {
        "organism": {
            "schema_version": SV,
            "organism_id": "taxon:9606",
            "ncbi_taxonomy_id": 9606,
            "scientific_name": "Homo sapiens",
            "rank": "species",
            "taxonomy_snapshot": {"source_id": "ncbi_taxonomy", "retrieved_at": T0},
        },
        "reference_assembly": {
            "schema_version": SV,
            "assembly_id": "grch38",
            "ncbi_taxonomy_id": 9606,
            "assembly_name": "GRCh38",
            "insdc_accession": "GCA_000001405.15",
            "refseq_accession": "GCF_000001405.26",
            "aliases": ["hg38"],
            "verification_status": "SOURCE_REPORTED_UNVERIFIED",
        },
        "reference_sequence_set": {
            "schema_version": SV,
            "sequence_set_id": "synthetic-seqset",
            "assembly_id": "grch38",
            "label": "SYNTHETIC sequence set",
            "includes_alt_contigs": False,
            "includes_decoys": None,
            "contig_naming": "UCSC_chr_prefix",
        },
        "study": {
            "schema_version": SV,
            "study_id": "study-synthetic",
            "accessions": {"bioproject": "PRJNA0000001"},
            "title": "SYNTHETIC study",
            "source_record_ids": ["src-1"],
        },
        "sample": {
            "schema_version": SV,
            "sample_id": "sample-synthetic",
            "biosample_accession": "SAMN00000001",
            "organism": rule("Homo sapiens", 9606, "SOURCE_CONTROLLED"),
            "aliases": [{"namespace": "synthetic", "value": "S1", "source_record_id": "src-1"}],
            "access_class": "OPEN",
            "source_record_ids": ["src-1"],
        },
        "sequencing_run": {
            "schema_version": SV,
            "run_id": "run-synthetic",
            "run_accession": "SRR0000001",
            "experiment_accession": "SRX0000001",
            "sample_id": "sample-synthetic",
            "study_id": "study-synthetic",
            "library": {
                "strategy": rule("WGS", "WGS", "SOURCE_CONTROLLED"),
                "source": rule("GENOMIC", "GENOMIC", "SOURCE_CONTROLLED"),
                "selection": rule("RANDOM", "RANDOM", "SOURCE_CONTROLLED"),
                "layout": rule("SINGLE", "SINGLE", "SOURCE_CONTROLLED"),
            },
            "assay": rule("WGS", "germline_wgs"),
            "platform": {
                "technology_family": rule("OXFORD_NANOPORE", "nanopore"),
                "vendor": rule("OXFORD_NANOPORE", "oxford_nanopore"),
                "instrument_family": rule("PromethION", "ont_promethion"),
                "instrument_model": rule("PromethION", "UNSPECIFIED"),
                "chemistry": [rule("R10.4.1", "ont_r10_4_1")],
                "read_mode": unresolved(),
            },
            "read_type": rule("SINGLE", "LONG_SINGLE_MOLECULE"),
            "basecaller": {"name": rule("dorado", "ont_dorado"), "version": "UNKNOWN", "model": "UNKNOWN"},
            "total_bases": 1000,
            "read_count": 10,
            "coverage": {"status": "UNKNOWN", "value": None},
            "public_file_artifact_ids": ["artifact-fastq"],
            "source_record_ids": ["src-1"],
        },
        "source_record": {
            "schema_version": SV,
            "source_record_id": "src-1",
            "source_id": "ena",
            "source_accession": "SRR0000001",
            "canonical_accession": "SRR0000001",
            "mirror_group_id": "insdc",
            "retrieved_at": T0,
            "query": {"endpoint": "https://example.invalid/api", "parameters_sha256": fake_sha("q")},
            "raw_snapshot_sha256": fake_sha("raw"),
            "raw_snapshot_uri": "urn:synthetic:raw-1",
            "terms": terms(),
        },
        "publication": {
            "schema_version": SV,
            "publication_id": "pub-synthetic",
            "title": "SYNTHETIC publication",
            "identifiers": {"doi": "10.0000/synthetic"},
        },
        "truth_source": {
            "schema_version": SV,
            "truth_source_id": "truth-synthetic",
            "provider": "SYNTHETIC",
            "release_version": "0.0",
            "sample_id": "sample-synthetic",
            "assembly_id": "grch38",
            "sequence_set_id": "synthetic-seqset",
            "evidence_domain": "GERMLINE_SMALL_VARIANT",
            "truth_artifact_id": "artifact-truth",
            "confident_regions_artifact_id": "artifact-bed",
            "terms": terms(),
        },
        "derived_artifact": {
            "schema_version": SV,
            "artifact_id": "artifact-vcf",
            "artifact_kind": "VCF",
            "origin": "ATLAS_DERIVED",
            "uri": "https://example.invalid/synthetic.vcf.gz",
            "size_bytes": 100,
            "checksum": {"algorithm": "sha256", "value": fake_sha("vcf"), "source": "ATLAS_BUILD"},
            "assembly_id": "grch38",
            "produced_by": {"pipeline": "synthetic", "software": "synthetic", "version": "0"},
            "derived_from": [{"kind": "SEQUENCING_RUN", "id": "run-synthetic"}],
            "availability": "PUBLIC",
        },
        "provenance_activity": {
            "schema_version": SV,
            "activity_id": "activity-1",
            "activity_type": "NORMALIZATION",
            "started_at": T0,
            "ended_at": T0,
            "agent": {"type": "SOFTWARE", "id": "synthetic", "version": "0", "commit": "abcdef1"},
            "used": [{"kind": "SOURCE_RECORD", "id": "src-1", "sha256": fake_sha("raw")}],
            "generated": [{"kind": "SEQUENCING_RUN", "id": "run-synthetic"}],
        },
        "catalog_record": {
            "schema_version": SV,
            "record_id": "rec-1",
            "record_version": 1,
            "record_kind": "SEQUENCING_RUN",
            "entity_ref": {"kind": "SEQUENCING_RUN", "id": "run-synthetic"},
            "layer": "VALIDATED_RELEASE",
            "eligibility_state": "RELEASED",
            "state_history": copy.deepcopy(RELEASED_HISTORY),
            "normalization_state": "NORMALIZED",
            "normalization_confidence": {
                "minimum_hard_gate_confidence": 1.0,
                "ml_only_hard_gate_fields": [],
                "unresolved_hard_gate_fields": [],
            },
            "discovered_at": T0,
            "last_seen_at": "2026-10-01T05:00:00Z",
            "source_record_ids": ["src-1"],
            "duplicate_cluster_id": "cluster-1",
            "canonical_in_cluster": True,
            "terms": terms(),
            "release_memberships": ["1.1.0"],
        },
        "eligibility_assessment": {
            "schema_version": SV,
            "assessment_id": "assess-1",
            "record_id": "rec-1",
            "record_version": 1,
            "policy_version": "0.2.0",
            "evaluated_at": T0,
            "evaluator": {"type": "SOFTWARE", "id": "synthetic"},
            "hard_gate_fields": [{"field": f, "method": "SOURCE_CONTROLLED"} for f in HARD_GATE_FIELDS],
            "criteria": [
                {"criterion_id": f"E{i:02d}", "decision": "PASS", "basis": "synthetic"}
                for i in range(1, 14)
            ],
            "outcome": "ELIGIBLE",
        },
        "release_manifest": {
            "schema_version": SV,
            "release_version": "1.1.0",
            "release_kind": "MINOR",
            "previous_release": "1.0.0",
            "created_at": T0,
            "entity_schema_version": SV,
            "policy_versions": {
                "eligibility_policy": "0.1.0",
                "ml_policy": "0.1.0",
                "technology_taxonomy": "0.1.0",
                "organisms_assemblies": "0.1.0",
                "sources": "0.1.0",
            },
            "git": {"tag": "v1.1.0", "commit": "0" * 40},
            "source_snapshot": {
                "snapshot_id": "snap-1",
                "taken_at": T0,
                "sources": [{"source_id": "ena", "retrieved_at": T0, "raw_snapshot_sha256": fake_sha("snap")}],
            },
            "records": [{"record_id": "rec-1", "record_version": 1, "content_sha256": fake_sha("rec")}],
            "artifacts": [{"path": "release/records.json", "sha256": fake_sha("art"), "size_bytes": 1}],
            "checksums_manifest": {"path": "release/checksums.sha256", "sha256": fake_sha("sums")},
            "validation_report": {"path": "release/validation.json", "sha256": fake_sha("val"),
                                  "verdict": "PASS", "gates_passed": 3, "gates_total": 3},
            "provenance": {"build_activity_id": "activity-release", "workflow": "synthetic"},
            "zenodo": {"deposit_status": "NOT_DEPOSITED"},
            "website": {"release_path": "/atlas/releases/1.1.0", "is_latest_at_publication": True},
        },
    }
