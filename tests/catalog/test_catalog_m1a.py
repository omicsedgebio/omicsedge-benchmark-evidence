from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from evidence_atlas import protocol
from evidence_atlas.catalog.ena import EnaAdapter, EnaApiError, FixtureTransport, HttpResponse
from evidence_atlas.catalog.models import PilotTaxon
from evidence_atlas.catalog.normalize import (
    TechnologyNormalizer,
    deduplicate_by_run_accession,
    normalize_ena_record,
)
from evidence_atlas.catalog.pipeline import run_pilot
from evidence_atlas.catalog.provenance import canonical_json_bytes, parameters_sha256, sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "catalog" / "ena"
TECHNOLOGY = ROOT / "config" / "atlas" / "technology_taxonomy.json"
FIXED_TIME = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
DEVELOPMENT_PILOT_MULTI_SAMPLE_COUNTS = (184, 120, 672, 194, 96, 355, 157)


def fixture_adapter(**overrides) -> EnaAdapter:
    options = {
        "transport": FixtureTransport(FIXTURES),
        "sleeper": lambda _seconds: None,
        "min_interval_seconds": 0,
        "clock": lambda: FIXED_TIME,
    }
    options.update(overrides)
    return EnaAdapter(**options)


def first_fixture_row() -> dict[str, str]:
    return EnaAdapter._tsv_rows((FIXTURES / "search_9606_exact.tsv").read_bytes())[0]


def normalize_row(row: dict[str, str]) -> dict:
    body = canonical_json_bytes(row)
    return normalize_ena_record(
        row,
        technology=TechnologyNormalizer.from_path(TECHNOLOGY),
        retrieved_at="2026-10-02T12:00:00Z",
        endpoint="https://www.ebi.ac.uk/ena/portal/api/search",
        parameters={"result": "read_run", "query": "tax_eq(9606)", "limit": 2},
        response_sha256=sha256_bytes(body),
        raw_snapshot_uri="snapshots/human.tsv",
    )


def test_ena_introspection_count_and_bounded_page() -> None:
    result = fixture_adapter().discover(PilotTaxon(9606, "Homo sapiens"), limit=2)
    assert result.source_reported_count == 7_765_981
    assert len(result.records) == 2
    assert result.records[0]["run_accession"] == "ERR10006159"
    search = next(request for request in result.requests if request.endpoint.endswith("/search"))
    assert search.parameters["limit"] == 2
    assert search.pagination == {
        "kind": "bounded_single_page",
        "page": 1,
        "limit": 2,
        "continuation_supported": False,
        "reason": "M1A intentionally uses one bounded limit query; deterministic temporal partitioning is deferred to M1B",
    }


def test_schema_compatible_m0_entities_and_catalog_only_lifecycle() -> None:
    bundle = normalize_row(first_fixture_row())
    protocol.validate_schema("sequencing_run", bundle["sequencing_run"])
    protocol.validate_schema("source_record", bundle["source_record"])
    protocol.validate_catalog_record(bundle["catalog_record"])
    for artifact in bundle["derived_artifacts"]:
        protocol.validate_schema("derived_artifact", artifact)
    catalog = bundle["catalog_record"]
    assert catalog["eligibility_state"] == "CATALOGUED"
    assert catalog["layer"] == "PUBLIC_DATA_CATALOG"
    assert all(step["to_state"] not in {"ELIGIBLE", "VALIDATED", "RELEASED"} for step in catalog["state_history"])


def test_accession_and_taxon_normalization_preserve_raw_values() -> None:
    bundle = normalize_row(first_fixture_row())
    assert bundle["accessions"] == {
        "experiment_accession": "ERX9547123",
        "study_accession": "ERP127356",
        "bioproject_accession": "PRJEB43396",
        "sample_accession": "ERS12521212",
        "biosample_accession": "SAMEA110422842",
        "sample_accessions": ["ERS12521212"],
        "biosample_accessions": ["SAMEA110422842"],
        "study_accessions": ["ERP127356"],
        "bioproject_accessions": ["PRJEB43396"],
    }
    assert bundle["taxonomy"]["raw_source_taxon_value"] == "9606"
    normalized = bundle["taxonomy"]["normalized_ncbi_taxonomy_id"]
    assert normalized["value"] == 9606
    assert normalized["method"] == "SOURCE_CONTROLLED"
    assert bundle["taxonomy"]["scientific_name"] == "Homo sapiens"


def test_missing_metadata_stays_unknown_and_is_not_guessed() -> None:
    row = first_fixture_row()
    for field in (
        "study_accession",
        "secondary_study_accession",
        "sample_accession",
        "secondary_sample_accession",
        "tax_id",
        "scientific_name",
        "instrument_platform",
        "instrument_model",
    ):
        row[field] = ""
    bundle = normalize_row(row)
    assert bundle["accessions"]["biosample_accession"] is None
    assert bundle["taxonomy"]["normalized_ncbi_taxonomy_id"]["value"] == "UNKNOWN"
    assert bundle["sequencing_run"]["platform"]["technology_family"]["value"] == "UNKNOWN"
    unresolved = bundle["catalog_record"]["normalization_confidence"]["unresolved_hard_gate_fields"]
    assert {"sample_id", "technology_family_id", "instrument_family_id"} <= set(unresolved)


def test_multi_sample_run_preserves_all_accessions_and_abstains() -> None:
    row = first_fixture_row()
    row["sample_accession"] = "SAMEA100000001;SAMEA100000002"
    row["secondary_sample_accession"] = "ERS1000001;ERS1000002"
    bundle = normalize_row(row)
    assert bundle["accessions"]["biosample_accessions"] == ["SAMEA100000001", "SAMEA100000002"]
    assert bundle["accessions"]["sample_accessions"] == ["ERS1000001", "ERS1000002"]
    assert bundle["accessions"]["biosample_accession"] is None
    assert bundle["sequencing_run"]["sample_id"] == "sample:unknown:err10006159"
    assert "sample_id" in bundle["catalog_record"]["normalization_confidence"]["unresolved_hard_gate_fields"]
    assert bundle["source_sample_cardinality"]["normalization_status"] == "MULTIPLE_SOURCE_SAMPLES"
    assert [row["sample_accession"] for row in bundle["source_sample_relationships"]] == [
        "SAMEA100000001",
        "SAMEA100000002",
        "ERS1000001",
        "ERS1000002",
    ]
    assert bundle["catalog_record"]["eligibility_state"] == "CATALOGUED"


@pytest.mark.parametrize("sample_count", DEVELOPMENT_PILOT_MULTI_SAMPLE_COUNTS)
def test_seven_run_multi_sample_pattern_is_preserved_without_first_sample_selection(sample_count: int) -> None:
    row = first_fixture_row()
    biosamples = [f"SAMEA{111000000 + index}" for index in range(sample_count)]
    insdc_samples = [f"ERS{12000000 + index}" for index in range(sample_count)]
    row["sample_accession"] = ";".join(biosamples)
    row["secondary_sample_accession"] = ";".join(insdc_samples)

    bundle = normalize_row(row)

    assert bundle["accessions"]["biosample_accessions"] == biosamples
    assert bundle["accessions"]["sample_accessions"] == insdc_samples
    assert bundle["accessions"]["biosample_accession"] is None
    assert bundle["accessions"]["sample_accession"] is None
    assert bundle["sequencing_run"]["sample_id"] == "sample:unknown:err10006159"
    assert len(bundle["source_sample_relationships"]) == sample_count * 2
    assert bundle["source_sample_cardinality"] == {
        "biosample_accession_count": sample_count,
        "insdc_sample_accession_count": sample_count,
        "normalization_status": "MULTIPLE_SOURCE_SAMPLES",
    }
    assert bundle["catalog_record"]["eligibility_state"] == "CATALOGUED"


def test_rules_only_technology_normalization_and_unknown_instrument() -> None:
    normalizer = TechnologyNormalizer.from_path(TECHNOLOGY)
    known = normalizer.normalize("ILLUMINA", "Illumina NovaSeq 6000")
    assert known["technology_family"]["value"] == "short_read_sbs"
    assert known["vendor"]["value"] == "illumina"
    assert known["instrument_family"]["value"] == "illumina_novaseq"
    assert known["instrument_model"]["value"] == "illumina_novaseq_6000"
    assert all(value["method"] != "ML_PROPOSED" for value in known.values() if isinstance(value, dict))

    unknown = normalizer.normalize("ABI_SOLID", "Unlisted Sequencer 9000")
    assert unknown["technology_family"] == {
        "raw_value": "ABI_SOLID",
        "value": "UNKNOWN",
        "method": "UNRESOLVED",
        "confidence": 0,
    }
    assert unknown["instrument_model"]["value"] == "UNKNOWN"


@pytest.mark.parametrize("model", ["Illumina HiSeq 1500", "Illumina HiSeq 3000"])
def test_development_pilot_instrument_candidates_remain_unresolved(model: str) -> None:
    normalized = TechnologyNormalizer.from_path(TECHNOLOGY).normalize("ILLUMINA", model)
    assert normalized["technology_family"]["value"] == "short_read_sbs"
    assert normalized["vendor"]["value"] == "illumina"
    assert normalized["instrument_family"]["value"] == "UNKNOWN"
    assert normalized["instrument_model"]["value"] == "UNKNOWN"
    assert normalized["instrument_family"]["method"] == "UNRESOLVED"


def test_unknown_assembly_is_valid_only_at_catalog_stage() -> None:
    catalogued = normalize_row(first_fixture_row())["catalog_record"]
    assert "assembly_id" in catalogued["normalization_confidence"]["unresolved_hard_gate_fields"]
    protocol.validate_catalog_record(catalogued)

    promoted = copy.deepcopy(catalogued)
    promoted["layer"] = "EVIDENCE_CANDIDATE"
    promoted["eligibility_state"] = "ELIGIBLE"
    promoted["normalization_state"] = "NORMALIZED"
    promoted["terms"] = {
        "terms_id": "test-compatible",
        "compatibility": "COMPATIBLE",
        "snapshot_sha256": "0" * 64,
        "snapshot_retrieved_at": "2026-10-02T12:00:00Z",
    }
    promoted["state_history"].extend(
        [
            {
                "from_state": "CATALOGUED",
                "to_state": "ELIGIBILITY_PENDING",
                "at": "2026-10-02T12:00:01Z",
                "actor": {"type": "SOFTWARE", "id": "test"},
                "reason": "negative test",
                "policy_version": "0.2.0",
            },
            {
                "from_state": "ELIGIBILITY_PENDING",
                "to_state": "ELIGIBLE",
                "at": "2026-10-02T12:00:02Z",
                "actor": {"type": "SOFTWARE", "id": "test"},
                "reason": "negative test",
                "policy_version": "0.2.0",
                "assessment_id": "assessment:test",
            },
        ]
    )
    with pytest.raises(protocol.AtlasProtocolError, match="unresolved_hard_gate_fields"):
        protocol.validate_catalog_record(promoted)


def test_deduplication_collapses_mirrored_accession() -> None:
    ena = normalize_row(first_fixture_row())
    sra = json.loads(json.dumps(ena))
    sra["source_record"]["source_id"] = "ncbi_sra"
    unique, duplicates = deduplicate_by_run_accession([ena, sra])
    assert len(unique) == 1
    assert duplicates == 1
    assert unique[0]["run_accession"] == "ERR10006159"


def test_http_retry_then_success() -> None:
    responses = iter(
        [
            HttpResponse(503, b"temporary", {"content-type": "text/plain"}),
            HttpResponse(200, b"columnId\tdescription\ttype\ntax_id\ttaxon\ttaxonomy\n", {"content-type": "text/tab-separated-values"}),
        ]
    )
    sleeps: list[float] = []
    adapter = EnaAdapter(
        transport=lambda *_args: next(responses),
        sleeper=sleeps.append,
        min_interval_seconds=0,
        backoff_seconds=0,
        max_retries=1,
        clock=lambda: FIXED_TIME,
    )
    snapshot = adapter._request(
        "searchFields",
        {"result": "read_run"},
        record_count=adapter._tsv_count,
        pagination={"kind": "not_applicable"},
    )
    assert snapshot.http_status == 200
    assert snapshot.record_count == 1
    assert len(sleeps) == 1


def test_malformed_success_response_is_retried_and_then_rejected() -> None:
    calls = 0

    def malformed(*_args) -> HttpResponse:
        nonlocal calls
        calls += 1
        return HttpResponse(200, b"columnId\tdescription\nERROR only-one-column\n", {})

    adapter = EnaAdapter(
        transport=malformed,
        sleeper=lambda _seconds: None,
        min_interval_seconds=0,
        backoff_seconds=0,
        max_retries=2,
    )
    with pytest.raises(EnaApiError, match="malformed ENA response"):
        adapter._request(
            "searchFields",
            {"result": "read_run"},
            record_count=adapter._tsv_count,
            pagination={},
        )
    assert calls == 3


def test_non_retryable_http_failure() -> None:
    adapter = EnaAdapter(
        transport=lambda *_args: HttpResponse(400, b"bad query", {}),
        sleeper=lambda _seconds: None,
        min_interval_seconds=0,
    )
    with pytest.raises(EnaApiError, match="HTTP 400"):
        adapter._request("search", {}, record_count=adapter._tsv_count, pagination={})


def test_provenance_hashes_are_canonical() -> None:
    assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    left = parameters_sha256({"query": "tax_eq(9606)", "result": "read_run"})
    right = parameters_sha256({"result": "read_run", "query": "tax_eq(9606)"})
    assert left == right
    result = fixture_adapter().discover(PilotTaxon(9606, "Homo sapiens"), limit=2)
    for request in result.requests:
        assert request.response_sha256 == sha256_bytes(request.response_body)


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_pipeline_outputs_are_deterministic_and_never_promote(tmp_path: Path) -> None:
    taxa = (PilotTaxon(9606, "Homo sapiens"), PilotTaxon(4932, "Saccharomyces cerevisiae", "tree"))
    outputs = []
    for name in ("first", "second"):
        root = tmp_path / name
        times = iter([10.0, 12.5])
        summary = run_pilot(
            adapter=fixture_adapter(),
            taxa=taxa,
            limit=2,
            output_dir=root / "data" / "catalog" / "m1a",
            results_dir=root / "results" / "catalog",
            technology_taxonomy_path=TECHNOLOGY,
            clock=lambda: FIXED_TIME,
            monotonic=lambda: next(times),
        )
        assert summary["lifecycle_assertion"] == {
            "state": "CATALOGUED",
            "layer": "PUBLIC_DATA_CATALOG",
            "eligible_records": 0,
            "validated_records": 0,
            "released_records": 0,
        }
        catalog_rows = [
            json.loads(line)
            for line in (root / "data/catalog/m1a/normalized/catalog_records.jsonl").read_text().splitlines()
        ]
        assert {row["eligibility_state"] for row in catalog_rows} == {"CATALOGUED"}
        outputs.append(_tree_bytes(root))
    assert outputs[0] == outputs[1]


def test_failed_pipeline_leaves_previous_outputs_untouched(tmp_path: Path) -> None:
    output_dir = tmp_path / "data/catalog/m1a"
    results_dir = tmp_path / "results/catalog"
    output_dir.mkdir(parents=True)
    results_dir.mkdir(parents=True)
    (output_dir / "previous.txt").write_text("previous data\n")
    (results_dir / "previous.txt").write_text("previous result\n")

    class FailingAdapter:
        source_id = "ena"

        def discover(self, taxon, *, limit):
            raise EnaApiError("simulated source failure")

    with pytest.raises(EnaApiError, match="simulated source failure"):
        run_pilot(
            adapter=FailingAdapter(),
            taxa=(PilotTaxon(9606, "Homo sapiens"),),
            limit=1,
            output_dir=output_dir,
            results_dir=results_dir,
            technology_taxonomy_path=TECHNOLOGY,
        )
    assert (output_dir / "previous.txt").read_text() == "previous data\n"
    assert (results_dir / "previous.txt").read_text() == "previous result\n"


@pytest.mark.parametrize("limit", [0, 101])
def test_invalid_or_unbounded_limits_are_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 100"):
        fixture_adapter().discover(PilotTaxon(9606, "Homo sapiens"), limit=limit)


def test_malformed_tsv_and_invalid_run_accession_are_rejected() -> None:
    with pytest.raises(ValueError, match="columns"):
        EnaAdapter._tsv_rows(b"a\tb\nonly-one\n")
    row = first_fixture_row()
    row["run_accession"] = "NOT_A_RUN"
    with pytest.raises(ValueError, match="invalid INSDC run accession"):
        normalize_row(row)


def test_introspection_allows_documented_columns_with_empty_description() -> None:
    rows = EnaAdapter._introspection_rows(
        b"columnId\tdescription\ttype\naligned\tboolean\ntax_id\tNCBI taxonomy\ttaxonomy\n"
    )
    assert rows == [
        {"columnId": "aligned", "description": "", "type": "boolean"},
        {"columnId": "tax_id", "description": "NCBI taxonomy", "type": "taxonomy"},
    ]


def test_local_cloud_live_cli_is_rejected_before_transport() -> None:
    environment = dict(os.environ)
    environment.pop("GITHUB_ACTIONS", None)
    environment.pop("RUNNER_ENVIRONMENT", None)
    environment.pop("RUNNER_OS", None)
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/atlas/catalog_discover.py"),
            "--source",
            "ena",
            "--cloud-live",
            "--limit",
            "1",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "live catalog discovery is disabled" in result.stderr


def test_workflow_is_manual_cloud_live_and_uploads_only_compact_metadata() -> None:
    workflow = (ROOT / ".github/workflows/m1a_catalog_discovery.yml").read_text()
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "python -m pytest\n" in workflow
    assert "--cloud-live" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "data/catalog/m1a/normalized/" in workflow
    assert "data/catalog/m1a/manifests/" in workflow
    assert "results/catalog/unresolved_metadata.tsv" in workflow
    assert "25 * 1024 * 1024" in workflow
