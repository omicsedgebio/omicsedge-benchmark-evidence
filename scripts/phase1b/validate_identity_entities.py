#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq
from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]

VARIANT_SCHEMA_PATH = (
    PROJECT_ROOT
    / "schemas/variant.phase1b.schema.json"
)

LINK_SCHEMA_PATH = (
    PROJECT_ROOT
    / "schemas/event_variant_link.phase1b.schema.json"
)

VARIANTS_PATH = (
    PROJECT_ROOT
    / "results/phase1b/variants.parquet"
)

LINKS_PATH = (
    PROJECT_ROOT
    / "results/phase1b/event_variant_links.parquet"
)

PHASE1A_EVENTS_PATH = (
    PROJECT_ROOT
    / "data/phase1a/omicsedge_phase1a_results/events.parquet"
)

PHASE1A_RUNS_PATH = (
    PROJECT_ROOT
    / "data/phase1a/omicsedge_phase1a_results/benchmark_runs.tsv"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "results/phase1b/entity_schema_validation.json"
)


EXPECTED_VARIANTS_SHA256 = (
    "c08939e19a71f140dd7c1901df0a7eafd528a4d35c4808701c3282cb4a008968"
)

EXPECTED_LINKS_SHA256 = (
    "bd695855e3e9fb6c80bd5d16d93f1a64bffc25da71754614f640e225bdb1e76e"
)

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


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def load_schema(
    path: Path,
) -> dict:
    schema = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    Draft202012Validator.check_schema(
        schema
    )

    return schema


def validate_rows(
    name: str,
    rows: list[dict],
    schema: dict,
) -> list[str]:

    validator = Draft202012Validator(
        schema
    )

    errors = []

    for row_number, row in enumerate(
        rows,
        start=1,
    ):
        for error in validator.iter_errors(
            row
        ):
            errors.append(
                (
                    f"{name}[{row_number}] "
                    f"{error.json_path}: "
                    f"{error.message}"
                )
            )

    return errors


def main() -> int:

    print("=" * 78)
    print(
        "PROJECT 003 — PHASE 1B "
        "ENTITY SCHEMA VALIDATION"
    )
    print("=" * 78)

    # --------------------------------------------------------
    # Verify frozen materialized entities.
    # --------------------------------------------------------

    observed_variants_sha = sha256_file(
        VARIANTS_PATH
    )

    observed_links_sha = sha256_file(
        LINKS_PATH
    )

    require(
        observed_variants_sha
        == EXPECTED_VARIANTS_SHA256,
        (
            "variants.parquet SHA-256 mismatch\n"
            f"expected: {EXPECTED_VARIANTS_SHA256}\n"
            f"observed: {observed_variants_sha}"
        ),
    )

    require(
        observed_links_sha
        == EXPECTED_LINKS_SHA256,
        (
            "event_variant_links.parquet "
            "SHA-256 mismatch\n"
            f"expected: {EXPECTED_LINKS_SHA256}\n"
            f"observed: {observed_links_sha}"
        ),
    )

    print(
        "PASS  materialized entity checksums"
    )

    # --------------------------------------------------------
    # Load schemas.
    # --------------------------------------------------------

    variant_schema = load_schema(
        VARIANT_SCHEMA_PATH
    )

    link_schema = load_schema(
        LINK_SCHEMA_PATH
    )

    print(
        "PASS  JSON Schemas are valid Draft 2020-12"
    )

    # --------------------------------------------------------
    # Load entity rows.
    # --------------------------------------------------------

    variants = (
        pq.read_table(
            VARIANTS_PATH
        )
        .to_pylist()
    )

    links = (
        pq.read_table(
            LINKS_PATH
        )
        .to_pylist()
    )

    require(
        len(variants)
        == EXPECTED_VARIANTS,
        (
            f"expected {EXPECTED_VARIANTS} variants, "
            f"observed {len(variants)}"
        ),
    )

    require(
        len(links)
        == EXPECTED_LINKS,
        (
            f"expected {EXPECTED_LINKS} links, "
            f"observed {len(links)}"
        ),
    )

    print(
        "PASS  expected entity row counts"
    )

    # --------------------------------------------------------
    # JSON Schema validation.
    # --------------------------------------------------------

    schema_errors = []

    schema_errors.extend(
        validate_rows(
            "VARIANT",
            variants,
            variant_schema,
        )
    )

    schema_errors.extend(
        validate_rows(
            "EVENT_VARIANT_LINK",
            links,
            link_schema,
        )
    )

    require(
        not schema_errors,
        (
            "JSON Schema validation failed:\n"
            + "\n".join(
                schema_errors[:50]
            )
        ),
    )

    print(
        "PASS  all 4,998 Phase 1B entity rows "
        "validate against versioned schemas"
    )

    # --------------------------------------------------------
    # Identifier uniqueness.
    # --------------------------------------------------------

    variant_ids = [
        row["variant_id"]
        for row in variants
    ]

    link_ids = [
        row["event_variant_link_id"]
        for row in links
    ]

    require(
        len(variant_ids)
        == len(set(variant_ids)),
        "duplicate variant_id detected",
    )

    require(
        len(link_ids)
        == len(set(link_ids)),
        (
            "duplicate event_variant_link_id "
            "detected"
        ),
    )

    print(
        "PASS  Phase 1B identifiers are unique"
    )

    # --------------------------------------------------------
    # Phase 1A endpoint resolution.
    # --------------------------------------------------------

    phase1a_events = (
        pq.read_table(
            PHASE1A_EVENTS_PATH
        )
        .to_pylist()
    )

    phase1a_event_index = {
        row["event_id"]:
            row
        for row in phase1a_events
    }

    require(
        len(phase1a_event_index)
        == len(phase1a_events),
        "duplicate Phase 1A event IDs",
    )

    variant_id_set = set(
        variant_ids
    )

    unresolved_events = []
    unresolved_variants = []
    run_mismatches = []

    for row in links:

        event_id = row[
            "event_id"
        ]

        variant_id_value = row[
            "variant_id"
        ]

        run_id = row[
            "benchmark_run_id"
        ]

        if event_id not in phase1a_event_index:
            unresolved_events.append(
                event_id
            )
            continue

        if variant_id_value not in variant_id_set:
            unresolved_variants.append(
                variant_id_value
            )

        if (
            phase1a_event_index[
                event_id
            ][
                "benchmark_run_id"
            ]
            != run_id
        ):
            run_mismatches.append(
                row[
                    "event_variant_link_id"
                ]
            )

    require(
        not unresolved_events,
        (
            "EVENT_VARIANT_LINK references "
            "unknown Phase 1A events"
        ),
    )

    require(
        not unresolved_variants,
        (
            "EVENT_VARIANT_LINK references "
            "unknown Phase 1B variants"
        ),
    )

    require(
        not run_mismatches,
        (
            "EVENT_VARIANT_LINK benchmark-run "
            "mismatch detected"
        ),
    )

    print(
        "PASS  all link endpoints resolve"
    )

    # --------------------------------------------------------
    # Semantic coordinate checks not expressible cleanly
    # through basic JSON Schema.
    # --------------------------------------------------------

    invalid_spans = [
        row["variant_id"]
        for row in variants
        if (
            row[
                "normalized_end_0based"
            ]
            <
            row[
                "normalized_start_0based"
            ]
        )
    ]

    require(
        not invalid_spans,
        "variant with end < start detected",
    )

    assemblies = {
        row["assembly"]
        for row in variants
    }

    require(
        assemblies == {"GRCh38"},
        (
            "unexpected Phase 1B assembly set: "
            f"{assemblies}"
        ),
    )

    print(
        "PASS  semantic coordinate/assembly checks"
    )

    # --------------------------------------------------------
    # Exact-identity link topology.
    #
    # Current observed Phase 1B graph requires each variant
    # to link to exactly two events from exactly two runs.
    # --------------------------------------------------------

    links_by_variant = defaultdict(
        list
    )

    event_link_counts = Counter()

    for row in links:

        links_by_variant[
            row["variant_id"]
        ].append(
            row
        )

        event_link_counts[
            row["event_id"]
        ] += 1

    require(
        all(
            count == 1
            for count
            in event_link_counts.values()
        ),
        (
            "one Phase 1A event is linked "
            "more than once"
        ),
    )

    invalid_variant_topology = []

    for variant_id_value, variant_links in (
        links_by_variant.items()
    ):

        event_count = len(
            {
                row["event_id"]
                for row
                in variant_links
            }
        )

        run_count = len(
            {
                row["benchmark_run_id"]
                for row
                in variant_links
            }
        )

        if (
            event_count != 2
            or run_count != 2
        ):
            invalid_variant_topology.append(
                variant_id_value
            )

    require(
        not invalid_variant_topology,
        (
            "unexpected exact-identity "
            "variant topology"
        ),
    )

    print(
        "PASS  every variant links exactly "
        "2 events from 2 runs"
    )

    # --------------------------------------------------------
    # Evidence/provenance JSON validation.
    # --------------------------------------------------------

    malformed_json = []

    for row in links:

        for field in (
            "evidence",
            "provenance",
        ):

            try:
                value = json.loads(
                    row[field]
                )
            except Exception:
                malformed_json.append(
                    (
                        row[
                            "event_variant_link_id"
                        ],
                        field,
                    )
                )
                continue

            if not isinstance(
                value,
                dict,
            ):
                malformed_json.append(
                    (
                        row[
                            "event_variant_link_id"
                        ],
                        field,
                    )
                )

    require(
        not malformed_json,
        (
            "malformed evidence/provenance "
            "JSON detected"
        ),
    )

    print(
        "PASS  evidence/provenance JSON parses"
    )

    # --------------------------------------------------------
    # Output validation record.
    # --------------------------------------------------------

    result = {
        "project":
            "Project 003",

        "phase":
            "1B",

        "operation":
            "ENTITY_SCHEMA_VALIDATION",

        "status":
            "PASS",

        "variant_schema":
            str(
                VARIANT_SCHEMA_PATH.relative_to(
                    PROJECT_ROOT
                )
            ),

        "variant_schema_sha256":
            sha256_file(
                VARIANT_SCHEMA_PATH
            ),

        "event_variant_link_schema":
            str(
                LINK_SCHEMA_PATH.relative_to(
                    PROJECT_ROOT
                )
            ),

        "event_variant_link_schema_sha256":
            sha256_file(
                LINK_SCHEMA_PATH
            ),

        "variants_parquet_sha256":
            observed_variants_sha,

        "event_variant_links_parquet_sha256":
            observed_links_sha,

        "variant_count":
            len(variants),

        "event_variant_link_count":
            len(links),

        "schema_validated_row_count":
            len(variants)
            + len(links),

        "unique_variant_ids":
            len(
                set(
                    variant_ids
                )
            ),

        "unique_event_variant_link_ids":
            len(
                set(
                    link_ids
                )
            ),

        "all_endpoints_resolve":
            True,

        "all_evidence_provenance_json_parses":
            True
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print()

    print(
        "variant schema SHA-256:",
        result[
            "variant_schema_sha256"
        ],
    )

    print(
        "EVENT_VARIANT_LINK schema SHA-256:",
        result[
            "event_variant_link_schema_sha256"
        ],
    )

    print(
        "validation result SHA-256:",
        sha256_file(
            OUTPUT_PATH
        ),
    )

    print()

    print(
        "PHASE1B_ENTITY_SCHEMA_VALIDATION_PASS"
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
            "PHASE1B_ENTITY_SCHEMA_VALIDATION_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
