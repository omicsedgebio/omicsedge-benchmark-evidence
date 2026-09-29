#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PHASE1A_RESULTS = (
    PROJECT_ROOT
    / "data/phase1a/omicsedge_phase1a_results"
)

CANDIDATES_PATH = (
    PHASE1A_RESULTS
    / "cross_run_candidates.tsv"
)

EVENTS_PATH = (
    PHASE1A_RESULTS
    / "events.parquet"
)

OBSERVATIONS_PATH = (
    PHASE1A_RESULTS
    / "observations.parquet"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "results/phase1b"
)

AUDIT_PATH = (
    OUTPUT_DIR
    / "candidate_structure_audit.tsv"
)

SUMMARY_PATH = (
    OUTPUT_DIR
    / "candidate_structure_summary.json"
)


EXPECTED_CANDIDATE_SHA256 = (
    "c9d0d50e8e96ce0fd98773ccf9fe306e9beac2186771fc89c76b959f91b7d758"
)

EXPECTED_CANDIDATE_ROWS = 1666

EXPECTED_PHASE1A_STATUS = (
    "CROSS_RUN_EQUIVALENCE_UNRESOLVED"
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


def normalized_allele_tuple(
    event: dict,
    observation: dict,
) -> tuple:
    """
    Structural allele tuple only.

    Uses assembly/contig from the run-scoped EVENT and the
    normalized coordinate/REF/ALT fields from OBSERVATION.

    This function does not claim cross-run biological identity.
    """

    return (
        event["assembly"],
        event["contig"],
        observation[
            "normalized_start_0based"
        ],
        observation[
            "normalized_end_0based"
        ],
        observation[
            "normalized_ref"
        ],
        observation[
            "normalized_alt"
        ],
    )


def structural_class(
    allele_count: int,
) -> str:

    if allele_count == 0:
        return "NO_NORMALIZED_ALLELE"

    if allele_count == 1:
        return "SINGLE_NORMALIZED_ALLELE"

    return "MULTIPLE_NORMALIZED_ALLELES"


def main() -> int:

    print("=" * 78)
    print(
        "PROJECT 003 — PHASE 1B "
        "REAL CANDIDATE STRUCTURE AUDIT"
    )
    print("=" * 78)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Frozen candidate input identity
    # --------------------------------------------------------

    candidate_sha = sha256_file(
        CANDIDATES_PATH
    )

    require(
        candidate_sha
        == EXPECTED_CANDIDATE_SHA256,
        (
            "candidate input SHA-256 mismatch\n"
            f"expected: "
            f"{EXPECTED_CANDIDATE_SHA256}\n"
            f"observed: {candidate_sha}"
        ),
    )

    print(
        "PASS  frozen candidate SHA-256"
    )


    # --------------------------------------------------------
    # Read Phase 1A entities
    # --------------------------------------------------------

    events = (
        pq.read_table(
            EVENTS_PATH
        )
        .to_pylist()
    )

    observations = (
        pq.read_table(
            OBSERVATIONS_PATH
        )
        .to_pylist()
    )

    with CANDIDATES_PATH.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:

        candidates = list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


    require(
        len(candidates)
        == EXPECTED_CANDIDATE_ROWS,
        (
            "candidate row count mismatch: "
            f"expected "
            f"{EXPECTED_CANDIDATE_ROWS}, "
            f"observed {len(candidates)}"
        ),
    )

    print(
        "PASS  candidate rows:",
        len(candidates),
    )


    # --------------------------------------------------------
    # Build immutable Phase 1A indexes
    # --------------------------------------------------------

    event_index = {}

    for event in events:

        event_id = event[
            "event_id"
        ]

        require(
            event_id
            not in event_index,
            (
                "duplicate Phase 1A event_id: "
                f"{event_id}"
            ),
        )

        event_index[
            event_id
        ] = event


    observations_by_event = defaultdict(
        list
    )

    for observation in observations:

        observations_by_event[
            observation["event_id"]
        ].append(
            observation
        )


    print(
        "PASS  Phase 1A events indexed:",
        len(event_index),
    )

    print(
        "PASS  Phase 1A observations indexed:",
        len(observations),
    )


    # --------------------------------------------------------
    # Structural audit
    # --------------------------------------------------------

    audit_rows = []

    failure_messages = []

    event_structure_counter = Counter()

    candidate_structure_counter = Counter()

    phase1a_status_counter = Counter()


    for candidate_number, candidate in enumerate(
        candidates,
        start=1,
    ):

        run_a = candidate[
            "run_a"
        ]

        run_b = candidate[
            "run_b"
        ]

        event_a_id = candidate[
            "event_a"
        ]

        event_b_id = candidate[
            "event_b"
        ]

        candidate_key = candidate[
            "normalized_allele_lookup_key"
        ]

        phase1a_status = candidate[
            "equivalence_status"
        ]

        phase1a_status_counter[
            phase1a_status
        ] += 1


        # ----------------------------------------------------
        # Resolve both events
        # ----------------------------------------------------

        event_a = event_index.get(
            event_a_id
        )

        event_b = event_index.get(
            event_b_id
        )


        if event_a is None:
            failure_messages.append(
                (
                    f"candidate {candidate_number}: "
                    f"event_a missing: {event_a_id}"
                )
            )
            continue


        if event_b is None:
            failure_messages.append(
                (
                    f"candidate {candidate_number}: "
                    f"event_b missing: {event_b_id}"
                )
            )
            continue


        # ----------------------------------------------------
        # Run IDs must resolve exactly
        # ----------------------------------------------------

        run_a_matches = (
            event_a[
                "benchmark_run_id"
            ]
            == run_a
        )

        run_b_matches = (
            event_b[
                "benchmark_run_id"
            ]
            == run_b
        )


        if not run_a_matches:
            failure_messages.append(
                (
                    f"candidate {candidate_number}: "
                    f"run_a mismatch for "
                    f"{event_a_id}"
                )
            )


        if not run_b_matches:
            failure_messages.append(
                (
                    f"candidate {candidate_number}: "
                    f"run_b mismatch for "
                    f"{event_b_id}"
                )
            )


        # ----------------------------------------------------
        # Phase 1A lookup-key consistency
        # ----------------------------------------------------

        event_a_key_matches = (
            event_a[
                "normalized_allele_lookup_key"
            ]
            == candidate_key
        )

        event_b_key_matches = (
            event_b[
                "normalized_allele_lookup_key"
            ]
            == candidate_key
        )


        if not event_a_key_matches:
            failure_messages.append(
                (
                    f"candidate {candidate_number}: "
                    "candidate lookup key does not "
                    f"match event_a {event_a_id}"
                )
            )


        if not event_b_key_matches:
            failure_messages.append(
                (
                    f"candidate {candidate_number}: "
                    "candidate lookup key does not "
                    f"match event_b {event_b_id}"
                )
            )


        # ----------------------------------------------------
        # Resolve normalized alleles represented by each event
        # ----------------------------------------------------

        obs_a = observations_by_event.get(
            event_a_id,
            [],
        )

        obs_b = observations_by_event.get(
            event_b_id,
            [],
        )


        alleles_a = {
            normalized_allele_tuple(
                event_a,
                obs,
            )
            for obs in obs_a
        }

        alleles_b = {
            normalized_allele_tuple(
                event_b,
                obs,
            )
            for obs in obs_b
        }


        structure_a = structural_class(
            len(alleles_a)
        )

        structure_b = structural_class(
            len(alleles_b)
        )


        event_structure_counter[
            structure_a
        ] += 1

        event_structure_counter[
            structure_b
        ] += 1


        pair_structure = (
            f"{structure_a}__{structure_b}"
        )

        candidate_structure_counter[
            pair_structure
        ] += 1


        # ----------------------------------------------------
        # Important:
        # No Phase 1B identity status is assigned here.
        # ----------------------------------------------------

        audit_rows.append(
            {
                "candidate_number":
                    candidate_number,

                "run_a":
                    run_a,

                "event_a":
                    event_a_id,

                "run_b":
                    run_b,

                "event_b":
                    event_b_id,

                "phase1a_candidate_status":
                    phase1a_status,

                "candidate_lookup_key_matches_event_a":
                    event_a_key_matches,

                "candidate_lookup_key_matches_event_b":
                    event_b_key_matches,

                "run_a_matches_event_a":
                    run_a_matches,

                "run_b_matches_event_b":
                    run_b_matches,

                "event_a_observation_count":
                    len(obs_a),

                "event_b_observation_count":
                    len(obs_b),

                "event_a_unique_normalized_alleles":
                    len(alleles_a),

                "event_b_unique_normalized_alleles":
                    len(alleles_b),

                "event_a_structure":
                    structure_a,

                "event_b_structure":
                    structure_b,

                "candidate_structure":
                    pair_structure,

                "phase1b_identity_status":
                    "NOT_ASSIGNED_IN_STRUCTURE_AUDIT",
            }
        )


    # --------------------------------------------------------
    # Frozen Phase 1A candidate status must remain unresolved.
    # --------------------------------------------------------

    require(
        set(
            phase1a_status_counter
        )
        == {
            EXPECTED_PHASE1A_STATUS
        },
        (
            "unexpected Phase 1A candidate status set: "
            f"{dict(phase1a_status_counter)}"
        ),
    )


    # --------------------------------------------------------
    # Structural integrity failures are fatal.
    # --------------------------------------------------------

    require(
        not failure_messages,
        (
            "candidate structural integrity "
            "audit failed:\n"
            + "\n".join(
                failure_messages[:50]
            )
        ),
    )


    require(
        len(audit_rows)
        == EXPECTED_CANDIDATE_ROWS,
        (
            "not every candidate was audited: "
            f"expected "
            f"{EXPECTED_CANDIDATE_ROWS}, "
            f"observed {len(audit_rows)}"
        ),
    )


    # --------------------------------------------------------
    # Write structural audit
    # --------------------------------------------------------

    fieldnames = [
        "candidate_number",
        "run_a",
        "event_a",
        "run_b",
        "event_b",
        "phase1a_candidate_status",
        "candidate_lookup_key_matches_event_a",
        "candidate_lookup_key_matches_event_b",
        "run_a_matches_event_a",
        "run_b_matches_event_b",
        "event_a_observation_count",
        "event_b_observation_count",
        "event_a_unique_normalized_alleles",
        "event_b_unique_normalized_alleles",
        "event_a_structure",
        "event_b_structure",
        "candidate_structure",
        "phase1b_identity_status",
    ]


    with AUDIT_PATH.open(
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
            audit_rows
        )


    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = {
        "phase":
            "1B",

        "purpose":
            "STRUCTURAL_AUDIT_ONLY",

        "candidate_input_sha256":
            candidate_sha,

        "candidate_count":
            len(candidates),

        "phase1a_candidate_status_counts":
            dict(
                sorted(
                    phase1a_status_counter.items()
                )
            ),

        "event_structure_counts":
            dict(
                sorted(
                    event_structure_counter.items()
                )
            ),

        "candidate_structure_counts":
            dict(
                sorted(
                    candidate_structure_counter.items()
                )
            ),

        "identity_classification_performed":
            False,

        "phase1a_entities_modified":
            False,

        "audit_output":
            str(
                AUDIT_PATH.relative_to(
                    PROJECT_ROOT
                )
            ),

        "audit_output_sha256":
            sha256_file(
                AUDIT_PATH
            ),
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
    # Human-readable summary
    # --------------------------------------------------------

    print()

    print(
        "Phase 1A candidate status counts:"
    )

    for key, value in sorted(
        phase1a_status_counter.items()
    ):
        print(
            f"  {key}: {value}"
        )


    print()

    print(
        "Event structural classes "
        "(candidate endpoints):"
    )

    for key, value in sorted(
        event_structure_counter.items()
    ):
        print(
            f"  {key}: {value}"
        )


    print()

    print(
        "Candidate pair structures:"
    )

    for key, value in sorted(
        candidate_structure_counter.items()
    ):
        print(
            f"  {key}: {value}"
        )


    print()

    print(
        "audit rows:",
        len(audit_rows),
    )

    print(
        "audit SHA-256:",
        sha256_file(
            AUDIT_PATH
        ),
    )

    print(
        "summary SHA-256:",
        sha256_file(
            SUMMARY_PATH
        ),
    )

    print()

    print(
        "PHASE1B_CANDIDATE_STRUCTURE_AUDIT_PASS"
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
            "PHASE1B_CANDIDATE_STRUCTURE_AUDIT_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
