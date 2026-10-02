from __future__ import annotations

import copy

import pytest

from atlas_synthetic import HARD_GATE_FIELDS, authoritative_hard_gate_values, ml, rule, step, unresolved
from evidence_atlas import protocol
from evidence_atlas.protocol import AtlasProtocolError


def _all(policy, decision="PASS"):
    return {c["id"]: decision for c in policy["criteria"]}


# ------------------------------------------------------------ aggregation


def test_all_pass_is_eligible(policy) -> None:
    assert protocol.aggregate_eligibility(policy, _all(policy)) == "ELIGIBLE"


def test_unknown_abstains(policy) -> None:
    decisions = _all(policy) | {"E06": "UNKNOWN"}
    assert protocol.aggregate_eligibility(policy, decisions) == "NEEDS_REVIEW"


def test_fail_dominates_unknown(policy) -> None:
    decisions = _all(policy) | {"E03": "FAIL", "E06": "UNKNOWN"}
    assert protocol.aggregate_eligibility(policy, decisions) == "INELIGIBLE"


def test_conditional_criterion_may_be_not_applicable(policy) -> None:
    assert protocol.aggregate_eligibility(policy, _all(policy) | {"E09": "NOT_APPLICABLE"}) == "ELIGIBLE"


def test_always_applicable_criterion_cannot_be_skipped(policy) -> None:
    with pytest.raises(AtlasProtocolError, match="always applicable"):
        protocol.aggregate_eligibility(policy, _all(policy) | {"E01": "NOT_APPLICABLE"})


def test_missing_and_unknown_criteria_are_rejected(policy) -> None:
    decisions = _all(policy)
    del decisions["E10"]
    with pytest.raises(AtlasProtocolError, match="not evaluated"):
        protocol.aggregate_eligibility(policy, decisions)
    with pytest.raises(AtlasProtocolError, match="unknown criteria"):
        protocol.aggregate_eligibility(policy, _all(policy) | {"E99": "PASS"})
    with pytest.raises(AtlasProtocolError, match="invalid decision"):
        protocol.aggregate_eligibility(policy, _all(policy) | {"E01": "MAYBE"})


def test_assessment_outcome_must_match_aggregation(policy, entities) -> None:
    assessment = entities["eligibility_assessment"]
    protocol.validate_eligibility_assessment(assessment, policy)
    assessment["criteria"][2]["decision"] = "FAIL"
    with pytest.raises(AtlasProtocolError, match="aggregated INELIGIBLE"):
        protocol.validate_eligibility_assessment(assessment, policy)


def test_assessment_cannot_evaluate_a_criterion_twice(policy, entities) -> None:
    assessment = entities["eligibility_assessment"]
    assessment["criteria"].append(dict(assessment["criteria"][0]))
    with pytest.raises(AtlasProtocolError, match="evaluated twice"):
        protocol.validate_eligibility_assessment(assessment, policy)


# -------------------------------------------------------------- lifecycle


def test_released_record_with_full_history_is_valid(policy, entities) -> None:
    protocol.validate_catalog_record(entities["catalog_record"], policy)


def test_catalogued_record_is_valid(policy, entities) -> None:
    record = entities["catalog_record"]
    record.update(eligibility_state="CATALOGUED", layer="PUBLIC_DATA_CATALOG",
                  normalization_state="RAW", state_history=record["state_history"][:1])
    record.pop("release_memberships")
    protocol.validate_catalog_record(record, policy)


def test_catalogued_cannot_jump_to_validated(policy, entities) -> None:
    assert not protocol.is_transition_allowed(policy, "CATALOGUED", "VALIDATED")
    assert not protocol.is_transition_allowed(policy, "CATALOGUED", "ELIGIBLE")
    assert not protocol.is_transition_allowed(policy, "ELIGIBLE", "RELEASED")
    record = entities["catalog_record"]
    record["state_history"] = [record["state_history"][0],
                               step("CATALOGUED", "VALIDATED", "2026-10-01T01:00:00Z"),
                               step("VALIDATED", "RELEASED", "2026-10-01T02:00:00Z", "RELEASE_BUILD",
                                    release_version="1.1.0")]
    with pytest.raises(AtlasProtocolError, match="forbidden transition CATALOGUED -> VALIDATED"):
        protocol.validate_catalog_record(record, policy)


def test_needs_review_requires_a_human_decision(policy, entities) -> None:
    record = entities["catalog_record"]
    record["state_history"][2] = step("ELIGIBILITY_PENDING", "NEEDS_REVIEW", "2026-10-01T02:00:00Z",
                                      assessment_id="assess-1")
    record["state_history"].insert(3, step("NEEDS_REVIEW", "ELIGIBLE", "2026-10-01T02:30:00Z", "SOFTWARE"))
    with pytest.raises(AtlasProtocolError, match="HUMAN actor"):
        protocol.validate_catalog_record(record, policy)
    record["state_history"][3]["actor"]["type"] = "HUMAN"
    protocol.validate_catalog_record(record, policy)


def test_release_requires_release_build(policy, entities) -> None:
    record = entities["catalog_record"]
    record["state_history"][-1]["actor"]["type"] = "WORKFLOW"
    with pytest.raises(AtlasProtocolError, match="RELEASE_BUILD"):
        protocol.validate_catalog_record(record, policy)


def test_eligibility_decision_requires_assessment(policy, entities) -> None:
    record = entities["catalog_record"]
    del record["state_history"][2]["assessment_id"]
    with pytest.raises(AtlasProtocolError, match="lacks assessment_id"):
        protocol.validate_catalog_record(record, policy)


def test_state_must_match_history(policy, entities) -> None:
    record = entities["catalog_record"]
    record["state_history"] = record["state_history"][:-1]
    with pytest.raises(AtlasProtocolError, match="does not match the last history entry"):
        protocol.validate_catalog_record(record, policy)


def test_history_must_be_continuous_and_chronological(policy, entities) -> None:
    broken = copy.deepcopy(entities["catalog_record"])
    broken["state_history"][3]["from_state"] = "INELIGIBLE"
    with pytest.raises(AtlasProtocolError, match="discontinuity"):
        protocol.validate_catalog_record(broken, policy)
    broken = copy.deepcopy(entities["catalog_record"])
    broken["state_history"][4]["at"] = "2026-09-30T00:00:00Z"
    with pytest.raises(AtlasProtocolError, match="not chronological"):
        protocol.validate_catalog_record(broken, policy)


def test_withdrawal_never_rewrites_release_membership(policy, entities) -> None:
    record = entities["catalog_record"]
    record["state_history"].append(step("RELEASED", "WITHDRAWN", "2026-10-02T00:00:00Z", "SOURCE_SYNC"))
    record["eligibility_state"] = "WITHDRAWN"
    record["layer"] = "PUBLIC_DATA_CATALOG"
    protocol.validate_catalog_record(record, policy)
    record["release_memberships"] = []
    with pytest.raises(AtlasProtocolError, match="release_memberships omits"):
        protocol.validate_catalog_record(record, policy)


# --------------------------------------------------------------------- ML


def _with_thresholds(ml_policy, *, accept, review):
    """Synthetic activated copy: tests the gate mechanics, not the M0 numbers."""
    activated = copy.deepcopy(ml_policy)
    activated["thresholds"]["active"] = True
    activated["thresholds"]["provisional_values"].update(accept_threshold=accept, review_threshold=review)
    return activated


@pytest.mark.parametrize("confidence", [0.0, 0.5, 0.999, 1.0])
def test_inactive_thresholds_route_every_proposal_to_review(ml_policy, confidence) -> None:
    assert ml_policy["thresholds"]["active"] is False
    assert protocol.ml_gate(ml_policy, confidence) == "REVIEW"


def test_ml_gate_reads_thresholds_from_configuration(ml_policy) -> None:
    for accept, review in ((0.8, 0.4), (0.6, 0.3)):
        configured = _with_thresholds(ml_policy, accept=accept, review=review)
        assert protocol.ml_gate(configured, accept) == "ACCEPT_NON_GATE"
        assert protocol.ml_gate(configured, accept - 1e-9) == "REVIEW"
        assert protocol.ml_gate(configured, review) == "REVIEW"
        assert protocol.ml_gate(configured, review - 1e-9) == "ABSTAIN"
    with pytest.raises(AtlasProtocolError):
        protocol.ml_gate(ml_policy, 1.01)


@pytest.mark.parametrize(
    "decision",
    ["hard_eligibility_gate", "biological_truth", "benchmark_truth", "validation_outcome",
     "release_inclusion", "clinical_interpretation", "technology_ranking", "caller_ranking",
     "trust_score", "anything_unlisted"],
)
def test_ml_may_not_decide_truth_rankings_or_unlisted(ml_policy, decision) -> None:
    assert protocol.ml_may_decide(ml_policy, decision) is False


def test_ml_may_assist_listed_tasks(ml_policy) -> None:
    for task in ml_policy["allowed_tasks"]:
        assert protocol.ml_may_decide(ml_policy, task["task"]) is True


# ------------------------------------------------------- hard-gate rule


@pytest.mark.parametrize("method", ["SOURCE_CONTROLLED", "RULE_EXACT", "RULE_PATTERN"])
def test_authoritative_or_deterministic_values_pass_a_hard_gate(policy, method) -> None:
    assert protocol.hard_gate_decision(policy, rule("raw", "v", method)) == "PASS"


def test_curated_value_passes_a_hard_gate(policy) -> None:
    curated = {"raw_value": "novaseq6k", "value": "illumina_novaseq", "method": "CURATED", "confidence": 1.0,
               "curation": {"curator": "c", "decided_at": "2026-10-01T00:00:00Z", "rationale": "confirmed"}}
    assert protocol.hard_gate_decision(policy, curated) == "PASS"


@pytest.mark.parametrize("confidence", [0.5, 0.95, 0.999, 1.0])
def test_ml_only_value_never_passes_a_hard_gate(policy, confidence) -> None:
    assert protocol.hard_gate_decision(policy, ml("x", "illumina_novaseq", confidence)) == "UNKNOWN"
    assert protocol.hard_gate_decision(policy, unresolved("x")) == "UNKNOWN"


def _others_pass(policy) -> dict:
    return {c["id"]: "PASS" for c in policy["criteria"] if c["id"] != "E13"}


def test_otherwise_eligible_record_with_authoritative_gates_is_eligible(policy) -> None:
    assert protocol.evaluate_eligibility(policy, _others_pass(policy), authoritative_hard_gate_values()) == "ELIGIBLE"


@pytest.mark.parametrize("field", HARD_GATE_FIELDS)
def test_ml_only_hard_gate_value_blocks_eligible(policy, ml_policy, field) -> None:
    values = authoritative_hard_gate_values()
    values[field] = ml(f"raw-{field}", f"value-{field}", 1.0)
    # Even with a (synthetic) activated threshold the model would clear, the
    # record must abstain to NEEDS_REVIEW rather than become ELIGIBLE.
    activated = _with_thresholds(ml_policy, accept=0.5, review=0.1)
    assert protocol.ml_gate(activated, 1.0) == "ACCEPT_NON_GATE"
    assert protocol.evaluate_eligibility(policy, _others_pass(policy), values) == "NEEDS_REVIEW"


def test_missing_hard_gate_field_abstains(policy) -> None:
    values = authoritative_hard_gate_values()
    del values["assembly_id"]
    assert protocol.evaluate_eligibility(policy, _others_pass(policy), values) == "NEEDS_REVIEW"


def test_curator_confirmation_of_ml_proposal_restores_eligibility(policy) -> None:
    values = authoritative_hard_gate_values()
    values["instrument_family_id"] = dict(
        ml("raw", "ont_promethion", 0.99), method="CURATED",
        curation={"curator": "c", "decided_at": "2026-10-01T00:00:00Z", "rationale": "confirmed from submitter docs"})
    del values["instrument_family_id"]["ml"]
    assert protocol.evaluate_eligibility(policy, _others_pass(policy), values) == "ELIGIBLE"


def test_e13_cannot_be_asserted_by_the_caller(policy) -> None:
    with pytest.raises(AtlasProtocolError, match="E13 is derived"):
        protocol.evaluate_eligibility(policy, _others_pass(policy) | {"E13": "PASS"}, authoritative_hard_gate_values())


def test_unknown_hard_gate_field_is_rejected(policy) -> None:
    with pytest.raises(AtlasProtocolError, match="not hard-gate fields"):
        protocol.evaluate_e13(policy, authoritative_hard_gate_values() | {"chemistry": rule("x", "y")})


def test_assessment_with_ml_only_gate_cannot_claim_e13_pass(policy, entities) -> None:
    assessment = entities["eligibility_assessment"]
    protocol.validate_eligibility_assessment(assessment, policy)
    assessment["hard_gate_fields"][1]["method"] = "ML_PROPOSED"
    with pytest.raises(AtlasProtocolError, match="not authoritatively backed"):
        protocol.validate_eligibility_assessment(assessment, policy)
    # The honest form of the same assessment abstains.
    next(c for c in assessment["criteria"] if c["criterion_id"] == "E13")["decision"] = "UNKNOWN"
    assessment["outcome"] = "NEEDS_REVIEW"
    protocol.validate_eligibility_assessment(assessment, policy)


def test_assessment_must_cover_every_hard_gate_field(policy, entities) -> None:
    assessment = entities["eligibility_assessment"]
    assessment["hard_gate_fields"].pop()
    with pytest.raises(AtlasProtocolError, match="every policy hard-gate field"):
        protocol.validate_eligibility_assessment(assessment, policy)


def test_curated_gate_field_needs_a_curation_reference(policy, entities) -> None:
    assessment = entities["eligibility_assessment"]
    assessment["hard_gate_fields"][0]["method"] = "CURATED"
    with pytest.raises(AtlasProtocolError, match="lacks curation_ref"):
        protocol.validate_eligibility_assessment(assessment, policy)
    assessment["hard_gate_fields"][0]["curation_ref"] = "curation-1"
    protocol.validate_eligibility_assessment(assessment, policy)


def test_policy_hard_gate_fields_match_fixture(policy) -> None:
    assert tuple(policy["hard_gate_fields"]) == HARD_GATE_FIELDS


# --------------------------------------------------------------- releases


def test_valid_release_manifest(entities) -> None:
    protocol.validate_release_manifest(entities["release_manifest"])


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda m: m["git"].update(tag="v1.2.0"), "git tag must equal"),
        (lambda m: m["validation_report"].update(gates_passed=2), "every validation gate"),
        (lambda m: m.update(release_kind="PATCH"), "release_kind PATCH != MINOR"),
        (lambda m: m.update(previous_release="1.1.0"), "does not advance"),
        (lambda m: m.update(release_version="1.1.1", git={"tag": "v1.1.1", "commit": "0" * 40},
                            previous_release="1.0.0"), "must reset patch"),
        (lambda m: m["records"].append({"record_id": "rec-1", "record_version": 2,
                                        "content_sha256": "1" * 64}), "only one version of each record"),
        (lambda m: m["artifacts"].append(dict(m["artifacts"][0])), "duplicate artifact paths"),
    ],
)
def test_release_manifest_invariants(entities, mutate, expected) -> None:
    manifest = entities["release_manifest"]
    mutate(manifest)
    with pytest.raises(AtlasProtocolError, match=expected):
        protocol.validate_release_manifest(manifest)


@pytest.mark.parametrize(
    ("previous", "current", "kind"),
    [("1.0.0", "1.1.0", "MINOR"), ("1.1.0", "1.2.0", "MINOR"), ("1.2.0", "2.0.0", "MAJOR"),
     ("1.0.0", "1.0.1", "PATCH")],
)
def test_expected_release_kind(previous, current, kind) -> None:
    assert protocol.expected_release_kind(previous, current) == kind
