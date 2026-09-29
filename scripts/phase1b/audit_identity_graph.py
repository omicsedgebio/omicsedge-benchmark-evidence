#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CLASSIFICATION_PATH = (
    PROJECT_ROOT
    / "results/phase1b/candidate_identity_classification.tsv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "results/phase1b"
)

GRAPH_AUDIT_PATH = (
    OUTPUT_DIR
    / "identity_graph_audit.tsv"
)

SUMMARY_PATH = (
    OUTPUT_DIR
    / "identity_graph_summary.json"
)


EXPECTED_CLASSIFICATION_SHA256 = (
    "b06f0c8a12b9f782a1ca73076906ce085cdff8191c09f7e00add7d028fa0f8fd"
)

EXPECTED_ROWS = 1666

EXPECTED_STATUS = (
    "EXACT_NORMALIZED_ALLELE"
)


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


def parse_bool(value: str) -> bool:
    value = str(value).strip().lower()

    if value == "true":
        return True

    if value == "false":
        return False

    raise ValueError(
        f"invalid boolean value: {value}"
    )


def main() -> int:

    print("=" * 78)
    print(
        "PROJECT 003 — PHASE 1B "
        "IDENTITY GRAPH AUDIT"
    )
    print("=" * 78)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Verify classification input.
    # --------------------------------------------------------

    observed_sha = sha256_file(
        CLASSIFICATION_PATH
    )

    require(
        observed_sha
        == EXPECTED_CLASSIFICATION_SHA256,
        (
            "classification SHA-256 mismatch\n"
            f"expected: "
            f"{EXPECTED_CLASSIFICATION_SHA256}\n"
            f"observed: {observed_sha}"
        ),
    )

    print(
        "PASS  classification SHA-256"
    )


    with CLASSIFICATION_PATH.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:

        rows = list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


    require(
        len(rows) == EXPECTED_ROWS,
        (
            "classification row count mismatch: "
            f"expected {EXPECTED_ROWS}, "
            f"observed {len(rows)}"
        ),
    )

    print(
        "PASS  classification rows:",
        len(rows),
    )


    # --------------------------------------------------------
    # Candidate numbering must be complete and unique.
    # --------------------------------------------------------

    candidate_numbers = [
        int(
            row["candidate_number"]
        )
        for row in rows
    ]

    require(
        candidate_numbers
        == list(
            range(
                1,
                EXPECTED_ROWS + 1,
            )
        ),
        (
            "candidate numbering is not exactly "
            f"1..{EXPECTED_ROWS}"
        ),
    )

    print(
        "PASS  candidate numbering"
    )


    # --------------------------------------------------------
    # Build graph structures.
    # --------------------------------------------------------

    pair_counter = Counter()

    event_to_variants = defaultdict(
        set
    )

    event_to_runs = defaultdict(
        set
    )

    event_occurrence_count = Counter()

    variant_to_events = defaultdict(
        set
    )

    variant_to_runs = defaultdict(
        set
    )

    variant_candidate_count = Counter()

    run_event_sets = defaultdict(
        set
    )

    run_variant_sets = defaultdict(
        set
    )

    unique_event_variant_links = set()


    for row in rows:

        status = row[
            "phase1b_identity_status"
        ]

        require(
            status == EXPECTED_STATUS,
            (
                "unexpected Phase 1B identity state: "
                f"{status}"
            ),
        )


        same_variant = parse_bool(
            row["same_variant_id"]
        )

        require(
            same_variant,
            (
                "exact normalized identity row has "
                "same_variant_id != TRUE"
            ),
        )


        variant_a = row[
            "variant_id_a"
        ]

        variant_b = row[
            "variant_id_b"
        ]

        require(
            variant_a == variant_b,
            (
                "exact normalized identity row has "
                "different deterministic variant IDs"
            ),
        )


        variant = variant_a

        run_a = row[
            "run_a"
        ]

        run_b = row[
            "run_b"
        ]

        event_a = row[
            "event_a"
        ]

        event_b = row[
            "event_b"
        ]


        require(
            run_a != run_b,
            (
                "cross-run candidate unexpectedly "
                "contains the same benchmark run"
            ),
        )


        require(
            event_a != event_b,
            (
                "cross-run candidate unexpectedly "
                "contains the same event on both sides"
            ),
        )


        pair = (
            run_a,
            event_a,
            run_b,
            event_b,
        )

        pair_counter[
            pair
        ] += 1


        for run_id, event_id in (
            (
                run_a,
                event_a,
            ),
            (
                run_b,
                event_b,
            ),
        ):

            event_to_variants[
                event_id
            ].add(
                variant
            )

            event_to_runs[
                event_id
            ].add(
                run_id
            )

            event_occurrence_count[
                event_id
            ] += 1

            variant_to_events[
                variant
            ].add(
                event_id
            )

            variant_to_runs[
                variant
            ].add(
                run_id
            )

            run_event_sets[
                run_id
            ].add(
                event_id
            )

            run_variant_sets[
                run_id
            ].add(
                variant
            )

            unique_event_variant_links.add(
                (
                    variant,
                    event_id,
                    run_id,
                )
            )


        variant_candidate_count[
            variant
        ] += 1


    # --------------------------------------------------------
    # Candidate-pair duplicates.
    # --------------------------------------------------------

    duplicate_pairs = {
        pair: count
        for pair, count
        in pair_counter.items()
        if count > 1
    }

    require(
        not duplicate_pairs,
        (
            "duplicate candidate pairs found: "
            f"{len(duplicate_pairs)}"
        ),
    )

    print(
        "PASS  duplicate candidate pairs: 0"
    )


    # --------------------------------------------------------
    # One event must never map to multiple biological VARIANT
    # IDs under the exact normalized identity layer.
    # --------------------------------------------------------

    multi_variant_events = {
        event_id: sorted(
            variants
        )
        for event_id, variants
        in event_to_variants.items()
        if len(variants) > 1
    }

    require(
        not multi_variant_events,
        (
            "one or more Phase 1A events map to "
            "multiple Phase 1B variant IDs: "
            f"{len(multi_variant_events)}"
        ),
    )

    print(
        "PASS  events mapping to multiple variants: 0"
    )


    # --------------------------------------------------------
    # Each Phase 1A event belongs to exactly one benchmark run.
    # --------------------------------------------------------

    multi_run_events = {
        event_id: sorted(
            runs
        )
        for event_id, runs
        in event_to_runs.items()
        if len(runs) > 1
    }

    require(
        not multi_run_events,
        (
            "one or more event IDs occur under "
            "multiple benchmark runs: "
            f"{len(multi_run_events)}"
        ),
    )

    print(
        "PASS  events mapping to multiple runs: 0"
    )


    # --------------------------------------------------------
    # Build one graph-audit row per biological VARIANT.
    # --------------------------------------------------------

    graph_rows = []

    degree_counter = Counter()

    candidate_multiplicity_counter = Counter()

    run_count_counter = Counter()


    for variant in sorted(
        variant_to_events
    ):

        events = sorted(
            variant_to_events[
                variant
            ]
        )

        runs = sorted(
            variant_to_runs[
                variant
            ]
        )

        candidate_count = (
            variant_candidate_count[
                variant
            ]
        )

        event_degree = len(
            events
        )

        run_count = len(
            runs
        )


        degree_counter[
            event_degree
        ] += 1

        candidate_multiplicity_counter[
            candidate_count
        ] += 1

        run_count_counter[
            run_count
        ] += 1


        graph_rows.append(
            {
                "variant_id":
                    variant,

                "unique_event_count":
                    event_degree,

                "unique_run_count":
                    run_count,

                "candidate_relationship_count":
                    candidate_count,

                "event_ids":
                    ";".join(
                        events
                    ),

                "benchmark_run_ids":
                    ";".join(
                        runs
                    ),
            }
        )


    # --------------------------------------------------------
    # Write deterministic audit table.
    # --------------------------------------------------------

    fieldnames = [
        "variant_id",
        "unique_event_count",
        "unique_run_count",
        "candidate_relationship_count",
        "event_ids",
        "benchmark_run_ids",
    ]


    with GRAPH_AUDIT_PATH.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )

        writer.writeheader()

        writer.writerows(
            graph_rows
        )


    graph_sha = sha256_file(
        GRAPH_AUDIT_PATH
    )


    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    repeated_candidate_events = sum(
        1
        for count
        in event_occurrence_count.values()
        if count > 1
    )


    summary = {
        "phase":
            "1B",

        "operation":
            "IDENTITY_GRAPH_AUDIT",

        "classification_input_sha256":
            observed_sha,

        "candidate_relationship_count":
            len(rows),

        "unique_candidate_pair_count":
            len(pair_counter),

        "duplicate_candidate_pair_count":
            len(duplicate_pairs),

        "unique_variant_count":
            len(variant_to_events),

        "unique_candidate_event_count":
            len(event_to_variants),

        "unique_event_variant_link_count":
            len(
                unique_event_variant_links
            ),

        "events_seen_in_multiple_candidate_rows":
            repeated_candidate_events,

        "events_mapping_to_multiple_variants":
            len(
                multi_variant_events
            ),

        "events_mapping_to_multiple_runs":
            len(
                multi_run_events
            ),

        "variant_event_degree_distribution":
            {
                str(k): v
                for k, v
                in sorted(
                    degree_counter.items()
                )
            },

        "variant_candidate_relationship_distribution":
            {
                str(k): v
                for k, v
                in sorted(
                    candidate_multiplicity_counter.items()
                )
            },

        "variant_run_count_distribution":
            {
                str(k): v
                for k, v
                in sorted(
                    run_count_counter.items()
                )
            },

        "per_run_unique_events":
            {
                run_id:
                    len(events)
                for run_id, events
                in sorted(
                    run_event_sets.items()
                )
            },

        "per_run_unique_variants":
            {
                run_id:
                    len(variants)
                for run_id, variants
                in sorted(
                    run_variant_sets.items()
                )
            },

        "phase1a_entities_modified":
            False,

        "graph_audit_output":
            str(
                GRAPH_AUDIT_PATH.relative_to(
                    PROJECT_ROOT
                )
            ),

        "graph_audit_sha256":
            graph_sha,
    }


    SUMMARY_PATH.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


    # --------------------------------------------------------
    # Human-readable output.
    # --------------------------------------------------------

    print()

    print(
        "candidate relationships:",
        len(rows),
    )

    print(
        "unique biological variant IDs:",
        len(
            variant_to_events
        ),
    )

    print(
        "unique candidate events:",
        len(
            event_to_variants
        ),
    )

    print(
        "unique EVENT_VARIANT links:",
        len(
            unique_event_variant_links
        ),
    )

    print(
        "events seen in >1 candidate row:",
        repeated_candidate_events,
    )


    print()

    print(
        "Variant event-degree distribution:"
    )

    for degree, count in sorted(
        degree_counter.items()
    ):

        print(
            f"  {degree} event(s): "
            f"{count} variant(s)"
        )


    print()

    print(
        "Variant run-count distribution:"
    )

    for run_count, count in sorted(
        run_count_counter.items()
    ):

        print(
            f"  {run_count} run(s): "
            f"{count} variant(s)"
        )


    print()

    print(
        "Variant candidate-relationship distribution:"
    )

    for multiplicity, count in sorted(
        candidate_multiplicity_counter.items()
    ):

        print(
            f"  {multiplicity} relationship(s): "
            f"{count} variant(s)"
        )


    print()

    print(
        "graph audit SHA-256:",
        graph_sha,
    )

    print(
        "summary SHA-256:",
        sha256_file(
            SUMMARY_PATH
        ),
    )

    print()

    print(
        "PHASE1B_IDENTITY_GRAPH_AUDIT_PASS"
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
            "PHASE1B_IDENTITY_GRAPH_AUDIT_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
