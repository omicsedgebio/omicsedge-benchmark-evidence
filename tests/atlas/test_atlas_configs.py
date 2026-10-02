from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

import pytest

from evidence_atlas import protocol

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", protocol.CONFIG_NAMES)
def test_config_validates_and_is_internally_consistent(name: str) -> None:
    config = protocol.load_config(name)
    assert protocol.CONFIG_INTEGRITY_CHECKS[name](config) == []


# ---------------------------------------------------------------- taxonomy


def _by_id(items):
    return {item["id"]: item for item in items}


def test_instruments_are_not_technology_families(taxonomy: dict) -> None:
    families = _by_id(taxonomy["technology_families"])
    inst = {f["label"]: f for f in taxonomy["instrument_families"]}
    for name in ("NovaSeq", "Revio", "PromethION", "Sequel"):
        assert name in inst
        assert name.lower() not in {fid.lower() for fid in families}
        assert inst[name]["technology_family_id"] in families


def test_vendor_is_not_technology(taxonomy: dict) -> None:
    inst = _by_id(taxonomy["instrument_families"])
    # PacBio operates two technology families: SMRT and sequencing by binding.
    assert inst["pacbio_revio"]["technology_family_id"] == "smrt"
    assert inst["pacbio_onso"]["technology_family_id"] == "short_read_sbb"
    term = {t["term"]: t for t in taxonomy["insdc_platform_terms"]}["PACBIO_SMRT"]
    assert term["vendor_id"] == "pacbio" and term["technology_family_id"] is None


def test_hifi_is_a_read_mode_of_smrt_not_a_family(taxonomy: dict) -> None:
    modes = _by_id(taxonomy["read_modes"])
    assert modes["smrt_hifi"]["technology_family_ids"] == ["smrt"]
    assert "pacbio_hifi" not in _by_id(taxonomy["technology_families"])


def test_family_only_source_strings_never_name_a_model(taxonomy: dict) -> None:
    model_aliases = {
        a.casefold()
        for m in taxonomy["instrument_models"]
        for a in [m["label"], *m["source_aliases"]]
    }
    for fam in taxonomy["instrument_families"]:
        for alias in fam["family_level_aliases"]:
            assert alias.casefold() not in model_aliases


def test_v1_technologies_are_marked_released(taxonomy: dict) -> None:
    released = {f["id"] for f in taxonomy["technology_families"] if f["evidence_scope"] == "RELEASED_IN_V1"}
    assert released == {"short_read_sbs", "nanopore"}


@pytest.mark.parametrize(
    ("description", "mutate", "expected"),
    [
        ("instrument family named like a technology family",
         lambda t: t["instrument_families"].append(
             {"id": "nanopore", "label": "X", "vendor_id": "oxford_nanopore",
              "technology_family_id": "nanopore", "family_level_aliases": []}),
         "conflated with a technology family"),
        ("vendor named like a technology family",
         lambda t: t["vendors"].append({"id": "smrt", "label": "Fake"}),
         "conflated with a technology family"),
        ("alias claimed by two models",
         lambda t: t["instrument_models"][0]["source_aliases"].append("Illumina NovaSeq 6000"),
         "claimed by"),
        ("family alias colliding with a model",
         lambda t: t["instrument_families"][0]["family_level_aliases"].append("HiSeq 2500"),
         "claimed by"),
        ("model with unknown family",
         lambda t: t["instrument_models"].append(
             {"id": "ghost", "label": "Ghost", "instrument_family_id": "nope", "source_aliases": []}),
         "unknown family"),
        ("chemistry from a vendor/family pair nobody sells",
         lambda t: t["chemistries"].append(
             {"id": "bad", "label": "Bad", "vendor_id": "illumina", "technology_family_id": "nanopore",
              "kind": "pore_version"}),
         "no instrument family has"),
        ("multi-family vendor term forced to one family",
         lambda t: next(x for x in t["insdc_platform_terms"] if x["term"] == "PACBIO_SMRT")
         .update(technology_family_id="smrt"),
         "multi-family vendor"),
        ("duplicate model id",
         lambda t: t["instrument_models"].append(copy.deepcopy(t["instrument_models"][0])),
         "duplicate id"),
    ],
)
def test_taxonomy_integrity_detects(taxonomy: dict, description, mutate, expected) -> None:
    mutate(taxonomy)
    errors = protocol.taxonomy_errors(taxonomy)
    assert any(expected in e for e in errors), errors


# ------------------------------------------------------- organisms/assemblies


def test_seed_organisms_use_taxonomy_ids(organisms: dict) -> None:
    taxa = {o["scientific_name"]: o["ncbi_taxonomy_id"] for o in organisms["organisms"]}
    assert taxa["Homo sapiens"] == 9606
    assert taxa["Mus musculus"] == 10090
    assert taxa["Saccharomyces cerevisiae"] == 4932
    assert taxa["Danio rerio"] == 7955


def test_species_have_multiple_assemblies(organisms: dict) -> None:
    by_taxon: dict[int, set[str]] = {}
    for asm in organisms["assemblies"]:
        by_taxon.setdefault(asm["ncbi_taxonomy_id"], set()).add(asm["assembly_name"])
    assert {"GRCh37", "GRCh38"} <= by_taxon[9606]
    assert {"GRCm38", "GRCm39"} <= by_taxon[10090]


def test_v1_reference_accession_matches_v1_source_manifest(organisms: dict) -> None:
    grch38 = {a["assembly_id"]: a for a in organisms["assemblies"]}["grch38"]
    seq_set = organisms["reference_sequence_sets"][0]
    with (REPO / seq_set["source_artifact_manifest"]).open() as fh:
        rows = {r["source_artifact_id"]: r for r in csv.DictReader(fh, delimiter="\t")}
    artifact = rows[seq_set["source_artifact_ref"]]
    assert artifact["artifact_name"].startswith(grch38["insdc_accession"] + "_GRCh38_no_alt_analysis_set")


def test_every_registry_identifier_is_verified(organisms: dict) -> None:
    assert all(o["verification_status"] == "VERIFIED_AGAINST_NCBI" for o in organisms["organisms"])
    assert all(a["verification_status"] == "VERIFIED_AGAINST_NCBI" for a in organisms["assemblies"])
    verification = json.loads(protocol.ASSEMBLY_VERIFICATION_RECORD.read_text())
    assert verification["sequence_data_downloaded"] is False
    assert protocol.identifier_verification_errors(organisms, verification) == []


def test_config_schema_refuses_unverified_assemblies(organisms: dict) -> None:
    organisms["assemblies"][0]["verification_status"] = "SEED_UNVERIFIED"
    assert protocol.schema_errors("organisms_assemblies", organisms)


def test_suppressed_refseq_is_recorded_not_hidden(organisms: dict) -> None:
    grcz11 = {a["assembly_id"]: a for a in organisms["assemblies"]}["grcz11"]
    assert grcz11["insdc_ncbi_status_observed"] == "current"
    assert grcz11["refseq_ncbi_status_observed"] == "suppressed"


def _verification() -> dict:
    return json.loads(protocol.ASSEMBLY_VERIFICATION_RECORD.read_text())


@pytest.mark.parametrize(
    ("mutate_registry", "mutate_record", "expected"),
    [
        (lambda r: r["assemblies"].append(dict(r["assemblies"][1], assembly_id="grch38_p14",
                                               insdc_accession="GCA_000001405.29", ucsc_db="hg38p14")),
         None, "grch38_p14 has no VERIFIED lookup"),
        (lambda r: r["assemblies"][1].update(refseq_accession="GCF_000001405.40"),
         None, "GCF_000001405.40 is not verified"),
        (lambda r: r["assemblies"][1].update(insdc_ncbi_status_observed="current"),
         None, "NCBI status differs"),
        (lambda r: r["assemblies"][1].update(ucsc_db="hg19x"), None, "UCSC name hg19x is not verified"),
        (lambda r: r["organisms"].append({"ncbi_taxonomy_id": 10116, "scientific_name": "Rattus norvegicus",
                                          "rank": "species", "atlas_scope": "CATALOG_ONLY",
                                          "verification_status": "VERIFIED_AGAINST_NCBI"}),
         None, "organism 10116 has no VERIFIED lookup"),
        (None, lambda v: v["results"][0].update(verdict="FAILED"), "grch37 has no VERIFIED lookup"),
        (None, lambda v: v["results"][0]["checks"][0].update(response_sha256="0" * 64), "missing or altered"),
        (None, lambda v: v.update(sequence_data_downloaded=True), "sequence_data_downloaded"),
    ],
)
def test_identifier_verification_detects(organisms: dict, mutate_registry, mutate_record, expected) -> None:
    record = _verification()
    if mutate_registry:
        mutate_registry(organisms)
    if mutate_record:
        mutate_record(record)
    errors = protocol.identifier_verification_errors(organisms, record)
    assert any(expected in e for e in errors), errors


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda r: r["assemblies"].append(dict(r["assemblies"][0], assembly_id="x", ncbi_taxonomy_id=1,
                                               insdc_accession="GCA_999999999.1", ucsc_db="xx1",
                                               refseq_accession="GCF_999999999.1")),
         "unregistered organism"),
        (lambda r: r["assemblies"][0].update(refseq_accession="GCF_000001635.20"), "numeric cores differ"),
        (lambda r: r["assemblies"][1].update(ucsc_db="hg19"), "UCSC database name reused"),
        (lambda r: r["assemblies"][7].update(insdc_ncbi_status_observed="suppressed"), "canonical INSDC accession is suppressed"),
        (lambda r: r["organisms"].append({"ncbi_taxonomy_id": 9606, "scientific_name": "dup", "rank": "species",
                                          "atlas_scope": "CATALOG_ONLY"}), "duplicate taxonomy id"),
        (lambda r: r["organisms"][3].pop("parent_ncbi_taxonomy_id"), "lacks a parent taxon"),
        (lambda r: r["reference_sequence_sets"][0].update(assembly_id="ghost"), "unknown assembly"),
    ],
)
def test_organism_registry_integrity_detects(organisms: dict, mutate, expected) -> None:
    mutate(organisms)
    errors = protocol.organism_registry_errors(organisms)
    assert any(expected in e for e in errors), errors


# ------------------------------------------------------------------ sources


def test_insdc_mirrors_form_one_counting_group(sources: dict) -> None:
    group = {g["mirror_group_id"]: g for g in sources["mirror_groups"]}["insdc"]
    assert {"ncbi_sra", "ena", "ddbj_dra"} <= set(group["member_source_ids"])
    assert group["canonical_key"] == "run_accession"


def test_raw_read_archives_are_not_evidence_grade(sources: dict) -> None:
    by_id = {s["source_id"]: s for s in sources["sources"]}
    for sid in ("ncbi_sra", "ena", "ddbj_dra"):
        assert by_id[sid]["evidence_grade_capable"] is False


def test_sources_integrity_detects_broken_mirror(sources: dict) -> None:
    next(s for s in sources["sources"] if s["source_id"] == "ena")["mirror_group_id"] = None
    assert any("does not point back" in e for e in protocol.sources_errors(sources))


# ------------------------------------------------------------ eligibility


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda p: p["transitions"]["CATALOGUED"].append("RELEASED"), "RELEASED must be reachable only"),
        (lambda p: p["transitions"]["ELIGIBLE"].append("VALIDATED"), "VALIDATED must be reachable only"),
        (lambda p: p["transitions"]["CATALOGUED"].append("VALIDATION_PENDING"), "VALIDATION_PENDING must be entered"),
        (lambda p: p["transitions"]["WITHDRAWN"].append("CATALOGUED"), "WITHDRAWN must be terminal"),
        (lambda p: p["transitions"]["RELEASED"].append("ELIGIBILITY_PENDING"), "RELEASED may only"),
        (lambda p: p["layers"][1]["states"].append("CATALOGUED"), "more than one layer"),
        (lambda p: p["transitions"]["ELIGIBLE"].append("ELIGIBLE"), "self-transition"),
        (lambda p: [p["transitions"][k].remove("WITHDRAWN") for k in p["transitions"] if "WITHDRAWN" in p["transitions"][k]],
         "unreachable states"),
        (lambda p: p["hard_gate_accepted_methods"].append("ML_PROPOSED"), "may never back a hard-gate field"),
        (lambda p: next(c for c in p["criteria"] if c["id"] == "E13").update(hard=False), "E13"),
    ],
)
def test_policy_integrity_detects(policy: dict, mutate, expected) -> None:
    broken = copy.deepcopy(policy)
    mutate(broken)
    errors = protocol.eligibility_policy_errors(broken)
    assert any(expected in e for e in errors), errors


def test_policy_schema_refuses_ml_as_hard_gate_backing(policy: dict) -> None:
    broken = copy.deepcopy(policy)
    broken["hard_gate_accepted_methods"].append("ML_PROPOSED")
    assert protocol.schema_errors("eligibility_policy", broken)


def test_layers_cover_the_three_layer_architecture(policy: dict) -> None:
    assert [layer["layer_id"] for layer in policy["layers"]] == [
        "PUBLIC_DATA_CATALOG", "EVIDENCE_CANDIDATE", "VALIDATED_RELEASE"]
    assert protocol.layer_for_state(policy, "CATALOGUED") == "PUBLIC_DATA_CATALOG"
    assert protocol.layer_for_state(policy, "VALIDATED") == "EVIDENCE_CANDIDATE"
    assert protocol.layer_for_state(policy, "RELEASED") == "VALIDATED_RELEASE"


# --------------------------------------------------------------------- ML


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda m: m["thresholds"]["provisional_values"].update(review_threshold=0.99), "review_threshold must be below"),
        (lambda m: m["model_registry"]["active_models"].append({"model_id": "m", "model_version": "1"}),
         "requires activated, validated thresholds"),
    ] + [
        (lambda m, d=d: m.update(prohibited_decisions=[x for x in m["prohibited_decisions"] if x["decision"] != d]),
         "missing required prohibitions")
        for d in sorted(protocol.REQUIRED_ML_PROHIBITIONS)
    ] + [
        (lambda m: m["allowed_tasks"].append({"task": "caller_ranking", "output": "x"}), "both allowed and prohibited"),
        (lambda m: m["normalization_methods"][1].update(ml=True), "ML_PROPOSED"),
    ],
)
def test_ml_policy_integrity_detects(ml_policy: dict, mutate, expected) -> None:
    broken = copy.deepcopy(ml_policy)
    mutate(broken)
    errors = protocol.ml_policy_errors(broken)
    assert any(expected in e for e in errors), errors


def test_m0_activates_no_model_and_no_threshold(ml_policy: dict) -> None:
    thresholds = ml_policy["thresholds"]
    assert thresholds["active"] is False
    assert thresholds["validated"] is False
    assert thresholds["status"] == "PROVISIONAL"
    assert thresholds["activation_record"] is None
    assert ml_policy["model_registry"]["active_models"] == []


def _activation_record() -> dict:
    report = {"path": "reports/synthetic.json", "sha256": "0" * 64}
    return {
        "activated_in_policy_version": "9.9.9",
        "approved_by": "synthetic-curator",
        "approved_at": "2026-10-01T00:00:00Z",
        "reports": {k: report for k in ("evaluation_set", "class_performance", "calibration",
                                         "abstention", "error_analysis", "threshold_rationale")},
    }


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda t: t.update(active=True), "thresholds/status"),
        (lambda t: t.update(active=True, status="ACTIVE"), "thresholds/validated"),
        (lambda t: t.update(active=True, status="ACTIVE", validated=True), "thresholds/activation_record"),
        (lambda t: t.update(status="ACTIVE"), "thresholds/status"),
        (lambda t: t.update(activation_record=_activation_record()), "thresholds/activation_record"),
        (lambda t: t.update(active=True, status="ACTIVE", validated=True,
                            activation_record=dict(_activation_record(), reports={})),
         "thresholds/activation_record"),
    ],
)
def test_threshold_activation_requires_complete_m2_evidence(ml_policy: dict, mutate, expected) -> None:
    broken = copy.deepcopy(ml_policy)
    mutate(broken["thresholds"])
    errors = protocol.schema_errors("ml_policy", broken)
    assert any(e.startswith(expected) for e in errors), errors


def test_threshold_activation_mechanics_accept_a_complete_record(ml_policy: dict) -> None:
    activated = copy.deepcopy(ml_policy)
    activated["thresholds"].update(active=True, status="ACTIVE", validated=True,
                                   activation_record=_activation_record())
    assert protocol.schema_errors("ml_policy", activated) == []
