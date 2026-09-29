#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

OUTPUT = (
    ROOT
    / "results/phase1b/phase1b_release_manifest.json"
)


FILES = [
    # Frozen protocol/input definitions
    "docs/phase1b/phase1b_protocol.md",
    "docs/phase1b/phase1b_protocol.lock",
    "data/phase1b/input_manifest.tsv",
    "data/phase1b/phase1b_freeze_manifest.tsv",
    "tests/phase1b/synthetic_identity_cases.tsv",

    # Identity implementation
    "src/benchmark_evidence/phase1b_identity.py",

    # Schemas
    "schemas/variant.phase1b.schema.json",
    "schemas/event_variant_link.phase1b.schema.json",

    # Query
    "sql/phase1b/variant_evidence.sql",

    # Main Phase 1B results
    "results/phase1b/candidate_identity_classification.tsv",
    "results/phase1b/candidate_identity_summary.json",
    "results/phase1b/identity_graph_audit.tsv",
    "results/phase1b/identity_graph_summary.json",

    "results/phase1b/variants.tsv",
    "results/phase1b/variants.parquet",
    "results/phase1b/event_variant_links.tsv",
    "results/phase1b/event_variant_links.parquet",

    "results/phase1b/entity_materialization_summary.json",
    "results/phase1b/entity_schema_validation.json",

    "results/phase1b/example_variant_evidence_query.tsv",
    "results/phase1b/variant_query_summary.json",

    # Final frozen validation
    "results/phase1b/phase1b_validation.tsv",
    "results/phase1b/phase1b_validation.json",
    "results/phase1b/phase1b_gate_report.md",

    # Reproduction / audit scripts
    "scripts/phase1b/verify_frozen_inputs.py",
    "scripts/phase1b/verify_identity_primitive.py",
    "scripts/phase1b/audit_candidate_structure.py",
    "scripts/phase1b/classify_real_candidates.py",
    "scripts/phase1b/audit_identity_graph.py",
    "scripts/phase1b/materialize_identity_entities.py",
    "scripts/phase1b/validate_identity_entities.py",
    "scripts/phase1b/build_variant_query.py",
    "scripts/phase1b/verify_reproducibility.py",
    "scripts/phase1b/evaluate_phase1b_gate.py",
]


EXPECTED_PHASE1A_ARCHIVE_SHA256 = (
    "6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202"
)

EXPECTED_PROTOCOL_SHA256 = (
    "ec1833c55877b25c37be24483f8598ff89efb18850f4d733a08b492e55ef5c45"
)

EXPECTED_GATE_VERDICT = "PASS"

EXPECTED_VARIANTS = 1666
EXPECTED_LINKS = 3332


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:

    print("=" * 78)
    print(
        "PROJECT 003 — PHASE 1B "
        "RELEASE MANIFEST"
    )
    print("=" * 78)

    # --------------------------------------------------------
    # Verify final gate result.
    # --------------------------------------------------------

    gate_path = (
        ROOT
        / "results/phase1b/phase1b_validation.json"
    )

    gate = json.loads(
        gate_path.read_text(
            encoding="utf-8"
        )
    )

    require(
        gate["verdict"]
        == EXPECTED_GATE_VERDICT,
        (
            "Phase 1B cannot be released: "
            f"gate verdict is {gate['verdict']}"
        ),
    )

    require(
        gate["criteria_passed"] == 15,
        "Phase 1B does not have 15/15 PASS",
    )

    require(
        gate["criteria_failed"] == 0,
        "Phase 1B has failed criteria",
    )

    require(
        gate["variant_count"]
        == EXPECTED_VARIANTS,
        "unexpected VARIANT count",
    )

    require(
        gate["event_variant_link_count"]
        == EXPECTED_LINKS,
        "unexpected EVENT_VARIANT_LINK count",
    )

    print(
        "PASS  final Phase 1B gate = 15/15 PASS"
    )

    # --------------------------------------------------------
    # Verify frozen protocol.
    # --------------------------------------------------------

    protocol_path = (
        ROOT
        / "docs/phase1b/phase1b_protocol.md"
    )

    protocol_sha = sha256_file(
        protocol_path
    )

    require(
        protocol_sha
        == EXPECTED_PROTOCOL_SHA256,
        "frozen Phase 1B protocol changed",
    )

    print(
        "PASS  frozen protocol SHA-256"
    )

    # --------------------------------------------------------
    # Verify referenced Phase 1A authority archive.
    # --------------------------------------------------------

    phase1a_archive = (
        ROOT
        / "data/phase1a/omicsedge_phase1a_results.tar.gz"
    )

    phase1a_sha = sha256_file(
        phase1a_archive
    )

    require(
        phase1a_sha
        == EXPECTED_PHASE1A_ARCHIVE_SHA256,
        "Phase 1A authority archive changed",
    )

    print(
        "PASS  Phase 1A authority archive SHA-256"
    )

    # --------------------------------------------------------
    # Collect authoritative Phase 1B files.
    # --------------------------------------------------------

    artifacts = []

    for relative in FILES:

        path = (
            ROOT
            / relative
        )

        require(
            path.is_file(),
            f"missing release artifact: {relative}",
        )

        artifacts.append(
            {
                "path":
                    relative,

                "size_bytes":
                    path.stat().st_size,

                "sha256":
                    sha256_file(
                        path
                    ),
            }
        )

    artifacts.sort(
        key=lambda row: row["path"]
    )

    print(
        "PASS  authoritative artifacts:",
        len(artifacts),
    )

    # --------------------------------------------------------
    # Build release manifest.
    # --------------------------------------------------------

    manifest = {
        "project":
            "Project 003",

        "phase":
            "1B",

        "release_status":
            "FROZEN",

        "scientific_gate":
            "PASS",

        "validation_criteria":
            "15/15 PASS",

        "scope":
            (
                "Cross-run biological variant identity "
                "layer for the frozen Phase 1A "
                "candidate set."
            ),

        "candidate_relationship_count":
            1666,

        "variant_count":
            1666,

        "event_variant_link_count":
            3332,

        "identity_method":
            "PHASE1B_EXACT_NORMALIZED_ALLELE_V1",

        "representation_equivalence_enabled":
            False,

        "reliability_scoring_enabled":
            False,

        "forced_cross_technology_consensus":
            False,

        "phase1a_authority_archive": {
            "path":
                "data/phase1a/omicsedge_phase1a_results.tar.gz",

            "sha256":
                phase1a_sha,
        },

        "phase1b_protocol": {
            "path":
                "docs/phase1b/phase1b_protocol.md",

            "sha256":
                protocol_sha,
        },

        "artifacts":
            artifacts,
    }

    OUTPUT.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print()

    print(
        "release manifest:",
        OUTPUT.relative_to(
            ROOT
        ),
    )

    print(
        "release manifest SHA-256:",
        sha256_file(
            OUTPUT
        ),
    )

    print()

    print(
        "PHASE1B_RELEASE_MANIFEST_PASS"
    )

    print("=" * 78)

    return 0


if __name__ == "__main__":

    try:
        sys.exit(
            main()
        )

    except Exception as exc:

        print()
        print(
            "PHASE1B_RELEASE_MANIFEST_FAIL"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        sys.exit(1)
