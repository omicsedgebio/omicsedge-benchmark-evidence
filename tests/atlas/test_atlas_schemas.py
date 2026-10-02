from __future__ import annotations

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from atlas_synthetic import make_entities, ml, rule, terms
from evidence_atlas import protocol


def test_every_schema_is_valid_draft_2020_12() -> None:
    paths = protocol.schema_paths()
    assert len(paths) == 1 + len(protocol.ENTITY_SCHEMAS) + len(protocol.CONFIG_NAMES)
    ids = set()
    for path in paths:
        schema = json.loads(path.read_text())
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"].endswith(str(path.relative_to(protocol.SCHEMA_DIR)))
        ids.add(schema["$id"])
    assert len(ids) == len(paths)


@pytest.mark.parametrize("name", protocol.ENTITY_SCHEMAS)
def test_entity_schema_pins_atlas_schema_version(name: str) -> None:
    schema = json.loads(protocol._schema_path(name).read_text())
    assert "schema_version" in schema["required"]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("name", protocol.ENTITY_SCHEMAS)
def test_synthetic_entity_validates(name: str, entities: dict) -> None:
    assert protocol.schema_errors(name, entities[name]) == []


def test_v1_registry_schema_version_is_rejected(entities: dict) -> None:
    entities["organism"]["schema_version"] = "1.0.0"
    assert protocol.schema_errors("organism", entities["organism"])


def _mutations():
    """(schema, description, mutate) cases that the schema MUST reject."""

    def drop(*path):
        def f(r):
            target = r
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
        return f

    def put(value, *path):
        def f(r):
            target = r
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
        return f

    return [
        # Species identity is the taxonomy ID, not a name.
        ("organism", "organism without taxonomy id", drop("ncbi_taxonomy_id")),
        # Assemblies are separate from, but bound to, an organism.
        ("reference_assembly", "assembly without organism", drop("ncbi_taxonomy_id")),
        ("reference_assembly", "RefSeq accession in INSDC slot", put("GCF_000001405.26", "insdc_accession")),
        ("reference_assembly", "verified without timestamp", put("VERIFIED_AGAINST_NCBI", "verification_status")),
        # Technology, vendor and instrument are separate required facets.
        ("sequencing_run", "platform without vendor", drop("platform", "vendor")),
        ("sequencing_run", "platform without instrument model", drop("platform", "instrument_model")),
        ("sequencing_run", "platform given as one string", put("Illumina NovaSeq 6000", "platform")),
        # Sample and run are distinct entities linked by id.
        ("sequencing_run", "run without sample link", drop("sample_id")),
        ("sequencing_run", "run accession that is a sample accession", put("SAMN00000001", "run_accession")),
        ("sequencing_run", "unknown coverage with a number", put({"status": "UNKNOWN", "value": 30}, "coverage")),
        ("sequencing_run", "computed coverage without genome size", put({"status": "COMPUTED_FROM_BASES", "value": 30}, "coverage")),
        ("sequencing_run", "ML value without model provenance",
         put({"raw_value": "x", "value": "y", "method": "ML_PROPOSED", "confidence": 0.99}, "platform", "instrument_model")),
        ("sequencing_run", "unresolved value pretending to be known",
         put({"raw_value": "x", "value": "illumina", "method": "UNRESOLVED", "confidence": 0}, "platform", "vendor")),
        ("sequencing_run", "confidence above one", put(dict(rule("x", "y"), confidence=1.5), "platform", "read_mode")),
        ("sample", "sample without access class", drop("access_class")),
        ("source_record", "source record without raw snapshot hash", drop("raw_snapshot_sha256")),
        ("source_record", "terms marked compatible without snapshot",
         put({"terms_id": "t", "compatibility": "COMPATIBLE"}, "terms")),
        ("truth_source", "truth source without assembly", drop("assembly_id")),
        ("derived_artifact", "Atlas-derived artifact with md5 checksum",
         put({"algorithm": "md5", "value": "0" * 32, "source": "ATLAS_BUILD"}, "checksum")),
        ("derived_artifact", "Atlas-derived artifact with unknown checksum", put("UNKNOWN", "checksum")),
        ("derived_artifact", "VCF without assembly", drop("assembly_id")),
        ("provenance_activity", "activity that generates nothing", put([], "generated")),
        # Catalog != evidence: layer and state must agree.
        ("catalog_record", "CATALOGUED record in release layer", put("CATALOGUED", "eligibility_state")),
        ("catalog_record", "RELEASED record outside release layer", put("EVIDENCE_CANDIDATE", "layer")),
        ("catalog_record", "RELEASED record without memberships", drop("release_memberships")),
        ("catalog_record", "RELEASED record with unreviewed terms", put(terms("UNREVIEWED"), "terms")),
        ("catalog_record", "RELEASED record that is a duplicate", put(False, "canonical_in_cluster")),
        ("catalog_record", "RELEASED record with ML-only hard-gate field",
         put(["technology_family_id"], "normalization_confidence", "ml_only_hard_gate_fields")),
        ("eligibility_assessment", "assessment without hard-gate provenance", drop("hard_gate_fields")),
        ("eligibility_assessment", "assessment with non-protocol outcome", put("VALIDATED", "outcome")),
        ("release_manifest", "release built on failed validation", put("FAIL", "validation_report", "verdict")),
        ("release_manifest", "release without checksums manifest", drop("checksums_manifest")),
        ("release_manifest", "release without source snapshot", drop("source_snapshot")),
        ("release_manifest", "deposited release without DOI", put({"deposit_status": "DEPOSITED"}, "zenodo")),
    ]


@pytest.mark.parametrize(
    ("name", "mutate"),
    [(n, m) for n, _, m in _mutations()],
    ids=[d for _, d, _ in _mutations()],
)
def test_schema_rejects_protocol_violation(name: str, mutate, request) -> None:
    record = make_entities()[name]
    mutate(record)
    errors = protocol.schema_errors(name, record)
    assert errors, "violation was accepted"
    # Guard against a mutation being rejected for an unrelated reason.
    expected = EXPECTED_ERROR[request.node.callspec.id]
    assert any(expected in e for e in errors), errors


EXPECTED_ERROR = {
    "organism without taxonomy id": "'ncbi_taxonomy_id' is a required",
    "assembly without organism": "'ncbi_taxonomy_id' is a required",
    "RefSeq accession in INSDC slot": "insdc_accession:",
    "verified without timestamp": "'verified_at' is a required",
    "platform without vendor": "platform: 'vendor' is a required",
    "platform without instrument model": "platform: 'instrument_model' is a required",
    "platform given as one string": "platform: 'Illumina NovaSeq 6000' is not of type 'object'",
    "run without sample link": "'sample_id' is a required",
    "run accession that is a sample accession": "run_accession:",
    "unknown coverage with a number": "coverage/value:",
    "computed coverage without genome size": "'genome_size_assembly_id' is a required",
    "ML value without model provenance": "platform/instrument_model: 'ml' is a required",
    "unresolved value pretending to be known": "platform/vendor/value:",
    "confidence above one": "platform/read_mode/confidence:",
    "sample without access class": "'access_class' is a required",
    "source record without raw snapshot hash": "'raw_snapshot_sha256' is a required",
    "terms marked compatible without snapshot": "terms: 'snapshot_sha256' is a required",
    "truth source without assembly": "'assembly_id' is a required",
    "Atlas-derived artifact with md5 checksum": "checksum/algorithm:",
    "Atlas-derived artifact with unknown checksum": "checksum: 'UNKNOWN' is not of type 'object'",
    "VCF without assembly": "'assembly_id' is a required",
    "activity that generates nothing": "generated:",
    "CATALOGUED record in release layer": "layer: 'PUBLIC_DATA_CATALOG' was expected",
    "RELEASED record outside release layer": "layer: 'VALIDATED_RELEASE' was expected",
    "RELEASED record without memberships": "'release_memberships' is a required",
    "RELEASED record with unreviewed terms": "terms/compatibility:",
    "RELEASED record that is a duplicate": "canonical_in_cluster:",
    "RELEASED record with ML-only hard-gate field": "ml_only_hard_gate_fields:",
    "assessment without hard-gate provenance": "'hard_gate_fields' is a required",
    "assessment with non-protocol outcome": "outcome:",
    "release built on failed validation": "validation_report/verdict:",
    "release without checksums manifest": "'checksums_manifest' is a required",
    "release without source snapshot": "'source_snapshot' is a required",
    "deposited release without DOI": "zenodo: 'version_doi' is a required",
}


def test_every_mutation_has_an_expected_error() -> None:
    assert set(EXPECTED_ERROR) == {d for _, d, _ in _mutations()}


@pytest.mark.parametrize(
    "state", ["ELIGIBLE", "VALIDATION_PENDING", "VALIDATION_FAILED", "VALIDATED"]
)
def test_candidate_states_require_candidate_layer_and_clean_normalization(state: str, entities: dict) -> None:
    record = entities["catalog_record"]
    record["eligibility_state"] = state
    record.pop("release_memberships")
    record["layer"] = "EVIDENCE_CANDIDATE"
    assert protocol.schema_errors("catalog_record", record) == []

    for mutate, expected in (
        (lambda r: r.update(layer="PUBLIC_DATA_CATALOG"), "layer:"),
        (lambda r: r.update(normalization_state="PARTIAL"), "normalization_state:"),
        (lambda r: r["normalization_confidence"].update(unresolved_hard_gate_fields=["assembly_id"]),
         "unresolved_hard_gate_fields:"),
        (lambda r: r["normalization_confidence"].update(ml_only_hard_gate_fields=["instrument_family_id"]),
         "ml_only_hard_gate_fields:"),
        (lambda r: r.update(terms=terms("UNREVIEWED")), "terms/compatibility:"),
        (lambda r: r.update(canonical_in_cluster=False), "canonical_in_cluster:"),
    ):
        broken = copy.deepcopy(record)
        mutate(broken)
        errors = protocol.schema_errors("catalog_record", broken)
        assert any(expected in e for e in errors), (state, errors)


@pytest.mark.parametrize("state", ["CATALOGUED", "ELIGIBILITY_PENDING", "NEEDS_REVIEW"])
def test_ml_only_hard_gate_values_may_exist_only_in_the_catalog_layer(state: str, entities: dict) -> None:
    record = entities["catalog_record"]
    record.pop("release_memberships")
    record.update(eligibility_state=state, layer="PUBLIC_DATA_CATALOG", normalization_state="PARTIAL")
    record["normalization_confidence"]["ml_only_hard_gate_fields"] = ["instrument_family_id"]
    assert protocol.schema_errors("catalog_record", record) == []


def test_ml_proposal_with_provenance_is_a_valid_normalized_value(entities: dict) -> None:
    entities["sequencing_run"]["platform"]["instrument_family"] = ml("Promethion-ish", "ont_promethion", 0.97)
    assert protocol.schema_errors("sequencing_run", entities["sequencing_run"]) == []
