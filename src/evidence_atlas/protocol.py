"""Executable form of the M0 Evidence Atlas Expansion Protocol.

This module loads the frozen M0 schemas and configuration, checks their
internal consistency, and implements the deterministic parts of the protocol
that later milestones must reuse rather than re-implement:

* the record lifecycle state machine and layer assignment;
* aggregation of eligibility-criterion decisions into an outcome;
* the ML confidence gate (accept / review / abstain);
* release-manifest invariants;
* verification that the released v1.0.0 artifacts are unchanged.

It performs no network access and ingests no data.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "atlas-0.1.0"
SCHEMA_DIR = REPO_ROOT / "schemas" / "atlas" / "0.1.0"
CONFIG_DIR = REPO_ROOT / "config" / "atlas"
V1_FREEZE_MANIFEST = REPO_ROOT / "releases" / "v1.0.0" / "frozen_artifacts.sha256"
V1_RELEASE_RECORD = REPO_ROOT / "releases" / "v1.0.0" / "release_record.json"
ASSEMBLY_VERIFICATION_RECORD = REPO_ROOT / "config" / "atlas" / "provenance" / "assembly_verification.json"

CONFIG_NAMES = (
    "technology_taxonomy",
    "organisms_assemblies",
    "sources",
    "eligibility_policy",
    "ml_policy",
)

ENTITY_SCHEMAS = (
    "organism",
    "reference_assembly",
    "reference_sequence_set",
    "study",
    "sample",
    "sequencing_run",
    "source_record",
    "publication",
    "truth_source",
    "derived_artifact",
    "provenance_activity",
    "catalog_record",
    "eligibility_assessment",
    "release_manifest",
)

# Decisions the ML policy must always prohibit.
REQUIRED_ML_PROHIBITIONS = frozenset(
    {
        "hard_eligibility_gate",
        "biological_truth",
        "benchmark_truth",
        "validation_outcome",
        "release_inclusion",
        "clinical_interpretation",
        "technology_ranking",
        "caller_ranking",
        "trust_score",
    }
)

# Methods that can never back a hard eligibility gate, whatever the policy says.
NON_AUTHORITATIVE_METHODS = frozenset({"ML_PROPOSED", "UNRESOLVED"})


class AtlasProtocolError(ValueError):
    """Raised when a record or configuration violates the M0 protocol."""


# --------------------------------------------------------------------------
# Loading and schema validation
# --------------------------------------------------------------------------


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def schema_paths() -> list[Path]:
    return sorted(SCHEMA_DIR.rglob("*.schema.json"))


@lru_cache(maxsize=1)
def schema_registry() -> Registry:
    resources = []
    for path in schema_paths():
        contents = _load_json(path)
        resources.append(
            (contents["$id"], Resource.from_contents(contents, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def _schema_path(name: str) -> Path:
    if name in CONFIG_NAMES:
        return SCHEMA_DIR / "config" / f"{name}.config.schema.json"
    return SCHEMA_DIR / f"{name}.schema.json"


@lru_cache(maxsize=None)
def validator(name: str) -> Draft202012Validator:
    schema = _load_json(_schema_path(name))
    return Draft202012Validator(schema, registry=schema_registry())


def schema_errors(name: str, instance: Any) -> list[str]:
    errors = sorted(validator(name).iter_errors(instance), key=lambda e: list(e.path))
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors]


def validate_schema(name: str, instance: Any) -> None:
    errors = schema_errors(name, instance)
    if errors:
        raise AtlasProtocolError(f"{name} schema violation: " + "; ".join(errors))


def load_config(name: str) -> dict:
    if name not in CONFIG_NAMES:
        raise KeyError(name)
    config = _load_json(CONFIG_DIR / f"{name}.json")
    validate_schema(name, config)
    return config


# --------------------------------------------------------------------------
# Configuration integrity (beyond what JSON Schema can express)
# --------------------------------------------------------------------------


def _duplicates(values: Iterable[Any]) -> set[Any]:
    seen: set[Any] = set()
    dups: set[Any] = set()
    for value in values:
        (dups if value in seen else seen).add(value)
    return dups


def taxonomy_errors(tax: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    families = {f["id"]: f for f in tax["technology_families"]}
    vendors = {v["id"] for v in tax["vendors"]}
    inst_families = {f["id"]: f for f in tax["instrument_families"]}

    for level in ("technology_families", "vendors", "instrument_families", "instrument_models",
                  "chemistries", "read_modes", "basecallers"):
        for dup in _duplicates(item["id"] for item in tax[level]):
            errors.append(f"duplicate id in {level}: {dup}")

    # Levels must not be conflated: no instrument or vendor may masquerade as
    # a technology family, by id or by label.
    family_tokens = {f["id"].lower() for f in families.values()} | {
        f["label"].lower() for f in families.values()
    }
    for level in ("vendors", "instrument_families", "instrument_models"):
        for item in tax[level]:
            if item["id"].lower() in family_tokens or item["label"].lower() in family_tokens:
                errors.append(f"{level} entry {item['id']} conflated with a technology family")

    for fam in inst_families.values():
        if fam["vendor_id"] not in vendors:
            errors.append(f"instrument family {fam['id']} has unknown vendor {fam['vendor_id']}")
        if fam["technology_family_id"] not in families:
            errors.append(
                f"instrument family {fam['id']} has unknown technology family "
                f"{fam['technology_family_id']}"
            )

    for model in tax["instrument_models"]:
        if model["instrument_family_id"] not in inst_families:
            errors.append(
                f"instrument model {model['id']} has unknown family {model['instrument_family_id']}"
            )

    # Every alias (model labels, model source aliases, family-level aliases)
    # must resolve to exactly one taxonomy node, case-insensitively.
    alias_owner: dict[str, str] = {}
    def claim(alias: str, owner: str) -> None:
        key = alias.casefold()
        if key in alias_owner and alias_owner[key] != owner:
            errors.append(f"alias {alias!r} claimed by {alias_owner[key]} and {owner}")
        alias_owner.setdefault(key, owner)

    for model in tax["instrument_models"]:
        claim(model["label"], f"model:{model['id']}")
        for alias in model["source_aliases"]:
            claim(alias, f"model:{model['id']}")
    for fam in inst_families.values():
        for alias in fam["family_level_aliases"]:
            claim(alias, f"family:{fam['id']}")

    vendor_families = {(f["vendor_id"], f["technology_family_id"]) for f in inst_families.values()}
    for level in ("chemistries", "basecallers"):
        for item in tax[level]:
            if (item["vendor_id"], item["technology_family_id"]) not in vendor_families:
                errors.append(
                    f"{level} entry {item['id']} pairs vendor {item['vendor_id']} with "
                    f"technology family {item['technology_family_id']} that no instrument family has"
                )

    for mode in tax["read_modes"]:
        for fid in mode["technology_family_ids"]:
            if fid not in families:
                errors.append(f"read mode {mode['id']} has unknown technology family {fid}")

    for term in tax["insdc_platform_terms"]:
        if term["vendor_id"] not in vendors:
            errors.append(f"platform term {term['term']} has unknown vendor {term['vendor_id']}")
        fid = term["technology_family_id"]
        vendor_fams = {f["technology_family_id"] for f in inst_families.values()
                       if f["vendor_id"] == term["vendor_id"]}
        if fid is None:
            if len(vendor_fams) < 2:
                errors.append(f"platform term {term['term']} is null but vendor is unambiguous")
        elif fid not in vendor_fams:
            errors.append(f"platform term {term['term']} maps to family {fid} its vendor lacks")
        elif len(vendor_fams) > 1:
            errors.append(
                f"platform term {term['term']} maps a multi-family vendor to a single family"
            )
    for dup in _duplicates(t["term"] for t in tax["insdc_platform_terms"]):
        errors.append(f"duplicate platform term {dup}")
    return errors


def organism_registry_errors(
    reg: Mapping[str, Any], verification: Mapping[str, Any] | None = None
) -> list[str]:
    errors: list[str] = []
    taxa = [o["ncbi_taxonomy_id"] for o in reg["organisms"]]
    for dup in _duplicates(taxa):
        errors.append(f"duplicate taxonomy id {dup}")
    taxa_set = set(taxa)
    for org in reg["organisms"]:
        parent = org.get("parent_ncbi_taxonomy_id")
        if parent is not None and parent not in taxa_set:
            errors.append(f"organism {org['ncbi_taxonomy_id']} has unregistered parent {parent}")
        if org["rank"] != "species" and parent is None:
            errors.append(f"sub-species organism {org['ncbi_taxonomy_id']} lacks a parent taxon")

    assembly_ids = [a["assembly_id"] for a in reg["assemblies"]]
    for dup in _duplicates(assembly_ids):
        errors.append(f"duplicate assembly id {dup}")
    accessions = [a["insdc_accession"] for a in reg["assemblies"]] + [
        a["refseq_accession"] for a in reg["assemblies"] if "refseq_accession" in a
    ]
    for dup in _duplicates(accessions):
        errors.append(f"assembly accession reused: {dup}")
    for dup in _duplicates(a["ucsc_db"].casefold() for a in reg["assemblies"] if "ucsc_db" in a):
        errors.append(f"UCSC database name reused across assemblies: {dup}")
    for asm in reg["assemblies"]:
        if asm["ncbi_taxonomy_id"] not in taxa_set:
            errors.append(f"assembly {asm['assembly_id']} references unregistered organism")
        if asm["assembly_id"].casefold() in {
            o["scientific_name"].casefold() for o in reg["organisms"]
        }:
            errors.append(f"assembly {asm['assembly_id']} conflated with an organism name")
        # GenBank and RefSeq accessions of one assembly share the numeric core.
        if "refseq_accession" in asm:
            if asm["insdc_accession"][4:13] != asm["refseq_accession"][4:13]:
                errors.append(f"assembly {asm['assembly_id']} GCA/GCF numeric cores differ")
        if asm["insdc_ncbi_status_observed"] == "suppressed":
            errors.append(f"assembly {asm['assembly_id']} canonical INSDC accession is suppressed")

    known = set(assembly_ids)
    for seq_set in reg["reference_sequence_sets"]:
        if seq_set["assembly_id"] not in known:
            errors.append(f"sequence set {seq_set['sequence_set_id']} references unknown assembly")

    if verification is None:
        verification = _load_json(ASSEMBLY_VERIFICATION_RECORD)
    errors += identifier_verification_errors(reg, verification)
    return errors


def identifier_verification_errors(
    reg: Mapping[str, Any], verification: Mapping[str, Any], root: Path = REPO_ROOT
) -> list[str]:
    """Every identifier in the registry must be backed by a VERIFIED lookup.

    The recorded raw responses must still hash to the recorded SHA-256, and
    the observed values (name, taxonomy ID, NCBI status, UCSC name) must match
    the registry. No identifier may be present but unverified.
    """
    errors: list[str] = []
    if verification.get("sequence_data_downloaded") is not False:
        errors.append("verification record must state sequence_data_downloaded: false")

    def snapshot_ok(entry: Mapping[str, Any]) -> bool:
        path = root / entry["response_snapshot"]
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == entry["response_sha256"]

    organisms = {r["ncbi_taxonomy_id"]: r for r in verification.get("organism_results", [])}
    for org in reg["organisms"]:
        taxid = org["ncbi_taxonomy_id"]
        result = organisms.get(taxid)
        if result is None or result["verdict"] != "VERIFIED" or result["failures"]:
            errors.append(f"organism {taxid} has no VERIFIED lookup")
            continue
        if not snapshot_ok(result):
            errors.append(f"organism {taxid} verification snapshot missing or altered")
        observed = result["observed"]
        if observed["organism_name"] != org["scientific_name"] or observed["rank"].lower() != org["rank"].lower():
            errors.append(f"organism {taxid} name/rank differ from verified lookup")
        if org.get("parent_ncbi_taxonomy_id") not in (None, observed["immediate_parent"]):
            errors.append(f"organism {taxid} parent differs from verified lineage")

    assemblies = {r["assembly_id"]: r for r in verification.get("results", [])}
    for asm in reg["assemblies"]:
        aid = asm["assembly_id"]
        result = assemblies.get(aid)
        if result is None or result["verdict"] != "VERIFIED":
            errors.append(f"assembly {aid} has no VERIFIED lookup")
            continue
        checks = {c["accession"]: c for c in result["checks"]}
        expected = {asm["insdc_accession"]: asm["insdc_ncbi_status_observed"]}
        if "refseq_accession" in asm:
            expected[asm["refseq_accession"]] = asm["refseq_ncbi_status_observed"]
        for accession, status in expected.items():
            check = checks.get(accession)
            if check is None or check["failures"]:
                errors.append(f"assembly {aid} accession {accession} is not verified")
                continue
            if not snapshot_ok(check):
                errors.append(f"assembly {aid} snapshot for {accession} missing or altered")
            observed = check["observed"]
            if observed["assembly_name"] != asm["assembly_name"] or observed["tax_id"] != asm["ncbi_taxonomy_id"]:
                errors.append(f"assembly {aid} accession {accession} name/taxon differ from lookup")
            if observed["ncbi_assembly_status"] != status:
                errors.append(f"assembly {aid} accession {accession} NCBI status differs from lookup")
        if "ucsc_db" in asm:
            ucsc = result.get("ucsc_check")
            if not ucsc or ucsc["failures"] or ucsc["ucsc_db"] != asm["ucsc_db"]:
                errors.append(f"assembly {aid} UCSC name {asm['ucsc_db']} is not verified")
    return errors


def sources_errors(src: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    ids = [s["source_id"] for s in src["sources"]]
    for dup in _duplicates(ids):
        errors.append(f"duplicate source id {dup}")
    by_id = {s["source_id"]: s for s in src["sources"]}
    groups = {g["mirror_group_id"]: g for g in src["mirror_groups"]}
    for group in groups.values():
        for member in group["member_source_ids"]:
            if member not in by_id:
                errors.append(f"mirror group {group['mirror_group_id']} lists unknown source {member}")
            elif by_id[member]["mirror_group_id"] != group["mirror_group_id"]:
                errors.append(f"source {member} does not point back to {group['mirror_group_id']}")
    for source in src["sources"]:
        gid = source["mirror_group_id"]
        if gid is not None and gid not in groups:
            errors.append(f"source {source['source_id']} references unknown mirror group {gid}")
    return errors


def eligibility_policy_errors(policy: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    declared = [s["state"] for s in policy["states"]]
    for dup in _duplicates(declared):
        errors.append(f"duplicate state {dup}")
    declared_set = set(declared)
    layered = [s for layer in policy["layers"] for s in layer["states"]]
    for dup in _duplicates(layered):
        errors.append(f"state {dup} assigned to more than one layer")
    if set(layered) != declared_set:
        errors.append("layers do not partition the declared states")
    if set(policy["transitions"]) != declared_set:
        errors.append("transition table keys differ from declared states")
    for src_state, targets in policy["transitions"].items():
        for target in targets:
            if target not in declared_set:
                errors.append(f"transition {src_state}->{target} targets undeclared state")
            if target == src_state:
                errors.append(f"self-transition {src_state}")

    predecessors: dict[str, set[str]] = {s: set() for s in declared_set}
    for src_state, targets in policy["transitions"].items():
        for target in targets:
            predecessors.setdefault(target, set()).add(src_state)
    if predecessors.get("RELEASED") != {"VALIDATED"}:
        errors.append("RELEASED must be reachable only from VALIDATED")
    if predecessors.get("VALIDATED") != {"VALIDATION_PENDING"}:
        errors.append("VALIDATED must be reachable only from VALIDATION_PENDING")
    if predecessors.get("VALIDATION_PENDING", set()) - {"ELIGIBLE", "VALIDATION_FAILED"}:
        errors.append("VALIDATION_PENDING must be entered only from ELIGIBLE or VALIDATION_FAILED")
    if policy["transitions"].get("WITHDRAWN"):
        errors.append("WITHDRAWN must be terminal")
    if set(policy["transitions"].get("RELEASED", [])) - {"WITHDRAWN"}:
        errors.append("RELEASED may only transition to WITHDRAWN")

    # Every non-terminal state must be able to reach a terminal decision.
    reachable = _reachable(policy["transitions"], policy["initial_state"])
    if reachable != declared_set:
        errors.append(f"unreachable states: {sorted(declared_set - reachable)}")

    crit_ids = [c["id"] for c in policy["criteria"]]
    for dup in _duplicates(crit_ids):
        errors.append(f"duplicate criterion {dup}")
    if not any(c["hard"] for c in policy["criteria"]):
        errors.append("policy has no hard criteria")
    e13 = next((c for c in policy["criteria"] if c["id"] == "E13"), None)
    if e13 is None or not e13["hard"]:
        errors.append("E13 (authoritatively backed hard-gate fields) must exist and be hard")
    if set(policy["hard_gate_accepted_methods"]) & NON_AUTHORITATIVE_METHODS:
        errors.append("ML_PROPOSED/UNRESOLVED may never back a hard-gate field")
    return errors


def _reachable(transitions: Mapping[str, list[str]], start: str) -> set[str]:
    seen = {start}
    frontier = [start]
    while frontier:
        for target in transitions.get(frontier.pop(), []):
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    return seen


def ml_policy_errors(ml: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    thresholds = ml["thresholds"]
    values = thresholds["provisional_values"]
    if not values["review_threshold"] < values["accept_threshold"]:
        errors.append("review_threshold must be below accept_threshold")
    if ml["model_registry"]["active_models"] and not thresholds["active"]:
        errors.append("an active model requires activated, validated thresholds")
    prohibited = {d["decision"] for d in ml["prohibited_decisions"]}
    missing = REQUIRED_ML_PROHIBITIONS - prohibited
    if missing:
        errors.append(f"ML policy is missing required prohibitions: {sorted(missing)}")
    allowed = {t["task"] for t in ml["allowed_tasks"]}
    if allowed & prohibited:
        errors.append(f"tasks both allowed and prohibited: {sorted(allowed & prohibited)}")
    ml_methods = {m["method"] for m in ml["normalization_methods"] if m["ml"]}
    if ml_methods != {"ML_PROPOSED"}:
        errors.append("exactly one normalization method (ML_PROPOSED) may be ML-derived")
    return errors


CONFIG_INTEGRITY_CHECKS = {
    "technology_taxonomy": taxonomy_errors,
    "organisms_assemblies": organism_registry_errors,
    "sources": sources_errors,
    "eligibility_policy": eligibility_policy_errors,
    "ml_policy": ml_policy_errors,
}


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


def layer_for_state(policy: Mapping[str, Any], state: str) -> str:
    for layer in policy["layers"]:
        if state in layer["states"]:
            return layer["layer_id"]
    raise AtlasProtocolError(f"unknown state {state}")


def is_transition_allowed(policy: Mapping[str, Any], from_state: str, to_state: str) -> bool:
    return to_state in policy["transitions"].get(from_state, [])


def state_history_errors(policy: Mapping[str, Any], record: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    history = record["state_history"]
    first = history[0]
    if first["from_state"] is not None or first["to_state"] != policy["initial_state"]:
        errors.append(f"history must start with null -> {policy['initial_state']}")
    for prev, step in zip(history, history[1:]):
        if step["from_state"] != prev["to_state"]:
            errors.append(f"history discontinuity at {step['at']}")
        if step["at"] < prev["at"]:
            errors.append(f"history not chronological at {step['at']}")
    for step in history[1:]:
        if not is_transition_allowed(policy, step["from_state"], step["to_state"]):
            errors.append(f"forbidden transition {step['from_state']} -> {step['to_state']}")
        if step["from_state"] == "NEEDS_REVIEW" and step["to_state"] in {"ELIGIBLE", "INELIGIBLE"}:
            if step["actor"]["type"] != "HUMAN":
                errors.append("leaving NEEDS_REVIEW for a decision requires a HUMAN actor")
        if step["to_state"] in {"ELIGIBLE", "INELIGIBLE", "NEEDS_REVIEW"} and step["from_state"] == "ELIGIBILITY_PENDING":
            if "assessment_id" not in step:
                errors.append(f"eligibility decision at {step['at']} lacks assessment_id")
        if step["to_state"] == "RELEASED":
            if step["actor"]["type"] != "RELEASE_BUILD" or "release_version" not in step:
                errors.append("RELEASED requires a RELEASE_BUILD actor and a release_version")
    if history[-1]["to_state"] != record["eligibility_state"]:
        errors.append("eligibility_state does not match the last history entry")
    released_in = {s["release_version"] for s in history if s["to_state"] == "RELEASED"}
    if released_in and not released_in <= set(record.get("release_memberships", [])):
        errors.append("release_memberships omits a release recorded in state_history")
    return errors


def validate_catalog_record(record: Mapping[str, Any], policy: Mapping[str, Any] | None = None) -> None:
    policy = policy or load_config("eligibility_policy")
    validate_schema("catalog_record", record)
    errors = []
    expected_layer = layer_for_state(policy, record["eligibility_state"])
    if record["layer"] != expected_layer:
        errors.append(f"layer {record['layer']} != {expected_layer} for {record['eligibility_state']}")
    errors += state_history_errors(policy, record)
    if record["last_seen_at"] < record["discovered_at"]:
        errors.append("last_seen_at precedes discovered_at")
    if errors:
        raise AtlasProtocolError("catalog record violation: " + "; ".join(errors))


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------


def aggregate_eligibility(policy: Mapping[str, Any], decisions: Mapping[str, str]) -> str:
    """Deterministically combine criterion decisions into an outcome.

    FAIL on any hard criterion dominates (INELIGIBLE); otherwise UNKNOWN on any
    hard criterion abstains (NEEDS_REVIEW); otherwise ELIGIBLE.
    """
    criteria = {c["id"]: c for c in policy["criteria"]}
    unknown_ids = set(decisions) - set(criteria)
    if unknown_ids:
        raise AtlasProtocolError(f"unknown criteria: {sorted(unknown_ids)}")
    missing = set(criteria) - set(decisions)
    if missing:
        raise AtlasProtocolError(f"criteria not evaluated: {sorted(missing)}")
    allowed = set(policy["decision_values"])
    for cid, decision in decisions.items():
        if decision not in allowed:
            raise AtlasProtocolError(f"{cid}: invalid decision {decision!r}")
        if decision == "NOT_APPLICABLE" and criteria[cid]["applicability"] != "CONDITIONAL":
            raise AtlasProtocolError(f"{cid} is always applicable; NOT_APPLICABLE is not allowed")

    hard = [decisions[cid] for cid, c in criteria.items() if c["hard"]]
    if "FAIL" in hard:
        return "INELIGIBLE"
    if "UNKNOWN" in hard:
        return "NEEDS_REVIEW"
    return "ELIGIBLE"


def validate_eligibility_assessment(
    assessment: Mapping[str, Any], policy: Mapping[str, Any] | None = None
) -> None:
    policy = policy or load_config("eligibility_policy")
    validate_schema("eligibility_assessment", assessment)
    if assessment["policy_version"] != policy["policy_version"]:
        raise AtlasProtocolError("assessment policy_version does not match the loaded policy")
    ids = [c["criterion_id"] for c in assessment["criteria"]]
    if _duplicates(ids):
        raise AtlasProtocolError(f"criterion evaluated twice: {sorted(_duplicates(ids))}")
    fields = [f["field"] for f in assessment["hard_gate_fields"]]
    if _duplicates(fields) or set(fields) != set(policy["hard_gate_fields"]):
        raise AtlasProtocolError("hard_gate_fields must list every policy hard-gate field exactly once")
    backed = all(f["method"] in policy["hard_gate_accepted_methods"] for f in assessment["hard_gate_fields"])
    for f in assessment["hard_gate_fields"]:
        if f["method"] == "CURATED" and "curation_ref" not in f:
            raise AtlasProtocolError(f"curated hard-gate field {f['field']} lacks curation_ref")
    decisions = {c["criterion_id"]: c["decision"] for c in assessment["criteria"]}
    if decisions.get("E13") == "PASS" and not backed:
        raise AtlasProtocolError("E13 PASS but a hard-gate field is not authoritatively backed (ML-only or unresolved)")
    expected = aggregate_eligibility(policy, decisions)
    if assessment["outcome"] != expected:
        raise AtlasProtocolError(f"outcome {assessment['outcome']} != aggregated {expected}")


# --------------------------------------------------------------------------
# ML gate
# --------------------------------------------------------------------------


def ml_gate(ml_policy: Mapping[str, Any], confidence: float) -> str:
    """Route an ML proposal by confidence: ACCEPT_NON_GATE, REVIEW or ABSTAIN.

    While thresholds are inactive (all of M0), every proposal goes to REVIEW.
    Even when active, ACCEPT_NON_GATE only lets ML populate a field that is NOT
    a hard eligibility gate; see ``hard_gate_decision``.
    """
    if not 0.0 <= confidence <= 1.0:
        raise AtlasProtocolError(f"confidence out of range: {confidence}")
    thresholds = ml_policy["thresholds"]
    if not thresholds["active"]:
        return "REVIEW"
    values = thresholds["provisional_values"]
    if confidence >= values["accept_threshold"]:
        return "ACCEPT_NON_GATE"
    if confidence >= values["review_threshold"]:
        return "REVIEW"
    return "ABSTAIN"


def ml_may_decide(ml_policy: Mapping[str, Any], decision: str) -> bool:
    """True only for tasks the ML policy explicitly allows."""
    prohibited = {d["decision"] for d in ml_policy["prohibited_decisions"]}
    allowed = {t["task"] for t in ml_policy["allowed_tasks"]}
    return decision in allowed and decision not in prohibited


def hard_gate_decision(policy: Mapping[str, Any], value: Mapping[str, Any]) -> str:
    """PASS only if a hard-gate field is authoritatively backed, else UNKNOWN.

    Authoritative backing is source metadata, deterministic normalization of
    it, or curator confirmation. An ML proposal is UNKNOWN at any confidence,
    so it can route a record to NEEDS_REVIEW but never promote it.
    """
    method = value["method"]
    if value["value"] == "UNKNOWN" or method in NON_AUTHORITATIVE_METHODS:
        return "UNKNOWN"
    if method in policy["hard_gate_accepted_methods"]:
        return "PASS"
    return "UNKNOWN"


def evaluate_e13(policy: Mapping[str, Any], hard_gate_values: Mapping[str, Mapping[str, Any]]) -> str:
    """Derive criterion E13 from the normalized values of every hard-gate field."""
    unknown_fields = set(hard_gate_values) - set(policy["hard_gate_fields"])
    if unknown_fields:
        raise AtlasProtocolError(f"not hard-gate fields: {sorted(unknown_fields)}")
    decisions = [
        hard_gate_decision(policy, hard_gate_values[f]) if f in hard_gate_values else "UNKNOWN"
        for f in policy["hard_gate_fields"]
    ]
    return "PASS" if all(d == "PASS" for d in decisions) else "UNKNOWN"


def evaluate_eligibility(
    policy: Mapping[str, Any],
    other_decisions: Mapping[str, str],
    hard_gate_values: Mapping[str, Mapping[str, Any]],
) -> str:
    """Eligibility outcome with E13 always derived from hard-gate provenance.

    Callers may not assert E13 themselves; it is computed from the values.
    """
    if "E13" in other_decisions:
        raise AtlasProtocolError("E13 is derived from hard-gate values and cannot be supplied")
    return aggregate_eligibility(policy, {**other_decisions, "E13": evaluate_e13(policy, hard_gate_values)})


# --------------------------------------------------------------------------
# Releases
# --------------------------------------------------------------------------


def _semver(text: str) -> tuple[int, int, int]:
    major, minor, patch = (int(p) for p in text.split("."))
    return major, minor, patch


def expected_release_kind(previous: str, current: str) -> str:
    prev, cur = _semver(previous), _semver(current)
    if cur <= prev:
        raise AtlasProtocolError(f"release {current} does not advance past {previous}")
    if cur[0] != prev[0]:
        if cur[1:] != (0, 0):
            raise AtlasProtocolError(f"major release {current} must reset minor and patch")
        return "MAJOR"
    if cur[1] != prev[1]:
        if cur[2] != 0:
            raise AtlasProtocolError(f"minor release {current} must reset patch")
        return "MINOR"
    return "PATCH"


def validate_release_manifest(manifest: Mapping[str, Any]) -> None:
    validate_schema("release_manifest", manifest)
    errors = []
    version = manifest["release_version"]
    if manifest["git"]["tag"] != f"v{version}":
        errors.append("git tag must equal 'v' + release_version")
    report = manifest["validation_report"]
    if report["gates_passed"] != report["gates_total"]:
        errors.append("a release requires every validation gate to pass")
    previous = manifest["previous_release"]
    if previous is not None:
        try:
            kind = expected_release_kind(previous, version)
        except AtlasProtocolError as exc:
            errors.append(str(exc))
        else:
            if manifest["release_kind"] != kind:
                errors.append(f"release_kind {manifest['release_kind']} != {kind}")
    keys = [(r["record_id"], r["record_version"]) for r in manifest["records"]]
    if _duplicates(r["record_id"] for r in manifest["records"]):
        errors.append("a release may contain only one version of each record")
    if _duplicates(keys):
        errors.append("duplicate record entries")
    if _duplicates(a["path"] for a in manifest["artifacts"]):
        errors.append("duplicate artifact paths")
    if errors:
        raise AtlasProtocolError("release manifest violation: " + "; ".join(errors))


# --------------------------------------------------------------------------
# v1.0.0 immutability
# --------------------------------------------------------------------------


def read_sha256_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text().splitlines():
        digest, _, rel = line.partition("  ")
        if len(digest) != 64 or not rel:
            raise AtlasProtocolError(f"malformed manifest line: {line!r}")
        entries[rel] = digest
    return entries


def v1_freeze_violations(root: Path = REPO_ROOT) -> list[str]:
    """Return every frozen v1.0.0 artifact that is missing or changed."""
    violations = []
    for rel, digest in read_sha256_manifest(root / V1_FREEZE_MANIFEST.relative_to(REPO_ROOT)).items():
        path = root / rel
        if not path.is_file():
            violations.append(f"MISSING {rel}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            violations.append(f"CHANGED {rel}")
    return violations


# --------------------------------------------------------------------------
# M0 protocol lock
# --------------------------------------------------------------------------

M0_LOCK = REPO_ROOT / "docs" / "atlas" / "m0_expansion_protocol.lock"
M0_LOCK_STATUS = "FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION"


def parse_lock(path: Path) -> dict[str, str]:
    """Parse a repository ``.lock`` file (``key=value`` rows, ``#`` comments).

    Same semantics as ``parse_lock`` in ``scripts/phase2/run_phase2e_validation.py``,
    plus rejection of duplicate keys.
    """
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise AtlasProtocolError(f"invalid lock row: {path}: {line}")
        key, value = line.split("=", 1)
        if key in result:
            raise AtlasProtocolError(f"duplicate lock key: {path}: {key}")
        result[key] = value
    return result


def lock_file_entries(lock: Mapping[str, str]) -> dict[str, str]:
    """Locked artifact paths mapped to their SHA-256 (``<path>_sha256=`` rows)."""
    return {
        key[: -len("_sha256")]: value
        for key, value in lock.items()
        if key.endswith("_sha256") and "/" in key
    }


def m0_lock_violations(root: Path = REPO_ROOT) -> list[str]:
    """Return every M0-locked artifact that is missing or changed, plus lock defects."""
    lock_path = root / M0_LOCK.relative_to(REPO_ROOT)
    lock = parse_lock(lock_path)
    violations = []
    if lock.get("status") != M0_LOCK_STATUS:
        violations.append(f"STATUS {lock.get('status')}")
    entries = lock_file_entries(lock)
    if str(len(entries)) != lock.get("locked_file_count"):
        violations.append("COUNT locked_file_count does not match locked entries")
    protocol = lock.get("protocol")
    if protocol is None or entries.get(protocol) != lock.get("protocol_sha256"):
        violations.append("PROTOCOL protocol_sha256 does not match its locked entry")
    for rel, digest in sorted(entries.items()):
        path = root / rel
        if not path.is_file():
            violations.append(f"MISSING {rel}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            violations.append(f"CHANGED {rel}")
    return violations
