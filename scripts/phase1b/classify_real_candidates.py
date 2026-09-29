#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from benchmark_evidence.phase1b_identity import (
    ALLOWED_IDENTITY_STATES,
    EXACT_NORMALIZED_ALLELE,
    REPRESENTATION_EQUIVALENCE_SUPPORTED,
    classify_identity,
    variant_id,
)


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

STRUCTURE_AUDIT_PATH = (
    PROJECT_ROOT
    / "results/phase1b/candidate_structure_audit.tsv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "results/phase1b"
)

CLASSIFICATION_PATH = (
    OUTPUT_DIR
    / "candidate_identity_classification.tsv"
)

SUMMARY_PATH = (
    OUTPUT_DIR
    / "candidate_identity_summary.json"
)


EXPECTED_CANDIDATE_SHA256 = (
    "c9d0d50e8e96ce0fd98773ccf9fe306e9beac2186771fc89c76b959f91b7d758"
)

EXPECTED_STRUCTURE_AUDIT_SHA256 = (
    "557f8e7f29c145a1d2da840bc3f299058f1fd0199b99f9f62061c110bedac4c1"
)

EXPECTED_CANDIDATE_ROWS = 1666

EXPECTED_PHASE1A_STATUS = (
    "CROSS_RUN_EQUIVALENCE_UNRESOLVED"
)

IDENTITY_METHOD = (
    "PHASE1B_EXACT_NORMALIZED_ALLELE_V1"
)

IDENTITY_METHOD_VERSION = "1.0.0"


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


def allele_from(
    event: dict,
    observation: dict,
) -> dict[str, object]:

    return {
        "assembly":
            event["assembly"],

        "contig":
            event["contig"],

        "start":
            observation[
                "normalized_start_0based"
            ],

        "end":
            observation[
                "normalized_end_0based"
            ],

        "ref":
            observation[
                "normalized_ref"
            ],

        "alt":
            observation[
                "normalized_alt"
            ],
    }


def canonical_allele_text(
    allele: dict[str, object],
) -> str:

    return (
        f"{allele['assembly']}|"
        f"{allele['contig']}|"
        f"{allele['start']}|"
        f"{allele['end']}|"
        f"{allele['ref']}|"
        f"{allele['alt']}"
    )


def main() -> int:

    print("=" * 78)

    print(
        "PROJECT 003 — PHASE 1B "
        "REAL CANDIDATE IDENTITY CLASSIFICATION"
    )

    print("=" * 78)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    # --------------------------------------------------------
    # Verify frozen inputs and prerequisite structural audit.
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


    structure_audit_sha = sha256_file(
        STRUCTURE_AUDIT_PATH
    )

    require(
        structure_audit_sha
        == EXPECTED_STRUCTURE_AUDIT_SHA256,
        (
            "structure audit SHA-256 mismatch\n"
            f"expected: "
            f"{EXPECTED_STRUCTURE_AUDIT_SHA256}\n"
            f"observed: {structure_audit_sha}"
        ),
    )

    print(
        "PASS  frozen structure-audit SHA-256"
    )


    # --------------------------------------------------------
    # Read immutable Phase 1A data.
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
            "candidate count mismatch: "
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
    # Build indexes.
    # --------------------------------------------------------

    event_index = {
        event["event_id"]:
            event
        for event in events
    }


    require(
        len(event_index)
        == len(events),
        "duplicate Phase 1A event identifiers",
    )


    observations_by_event = defaultdict(
        list
    )


    for observation in observations:

        observations_by_event[
            observation["event_id"]
        ].append(
            observation
        )


    # --------------------------------------------------------
    # Classify every candidate exactly once.
    # --------------------------------------------------------

    classification_rows = []

    status_counts = Counter()

    same_variant_id_counts = Counter()


    for candidate_number, candidate in enumerate(
        candidates,
        start=1,
    ):

        require(
            candidate[
                "equivalence_status"
            ]
            == EXPECTED_PHASE1A_STATUS,
            (
                "unexpected Phase 1A candidate status "
                f"at row {candidate_number}: "
                f"{candidate['equivalence_status']}"
            ),
        )


        event_a_id = candidate[
            "event_a"
        ]

        event_b_id = candidate[
            "event_b"
        ]


        require(
            event_a_id in event_index,
            (
                f"candidate {candidate_number}: "
                f"missing event_a {event_a_id}"
            ),
        )

        require(
            event_b_id in event_index,
            (
                f"candidate {candidate_number}: "
                f"missing event_b {event_b_id}"
            ),
        )


        event_a = event_index[
            event_a_id
        ]

        event_b = event_index[
            event_b_id
        ]


        obs_a = observations_by_event[
            event_a_id
        ]

        obs_b = observations_by_event[
            event_b_id
        ]


        # ----------------------------------------------------
        # Structural audit established one normalized allele
        # per event. Re-enforce that invariant here rather than
        # trusting the previous output blindly.
        # ----------------------------------------------------

        allele_keys_a = {
            (
                obs[
                    "normalized_start_0based"
                ],
                obs[
                    "normalized_end_0based"
                ],
                obs[
                    "normalized_ref"
                ],
                obs[
                    "normalized_alt"
                ],
            )
            for obs in obs_a
        }

        allele_keys_b = {
            (
                obs[
                    "normalized_start_0based"
                ],
                obs[
                    "normalized_end_0based"
                ],
                obs[
                    "normalized_ref"
                ],
                obs[
                    "normalized_alt"
                ],
            )
            for obs in obs_b
        }


        require(
            len(allele_keys_a) == 1,
            (
                f"candidate {candidate_number}: "
                f"event_a no longer resolves to exactly "
                f"one normalized allele"
            ),
        )

        require(
            len(allele_keys_b) == 1,
            (
                f"candidate {candidate_number}: "
                f"event_b no longer resolves to exactly "
                f"one normalized allele"
            ),
        )


        observation_a = obs_a[0]
        observation_b = obs_b[0]


        allele_a = allele_from(
            event_a,
            observation_a,
        )

        allele_b = allele_from(
            event_b,
            observation_b,
        )


        status = classify_identity(
            allele_a,
            allele_b,
        )


        require(
            status
            in ALLOWED_IDENTITY_STATES,
            (
                "classifier emitted invalid state: "
                f"{status}"
            ),
        )


        # v1 is explicitly forbidden from claiming
        # representation-equivalence support.
        require(
            status
            != REPRESENTATION_EQUIVALENCE_SUPPORTED,
            (
                "v1 unexpectedly emitted "
                "REPRESENTATION_EQUIVALENCE_SUPPORTED"
            ),
        )


        variant_a = variant_id(
            allele_a
        )

        variant_b = variant_id(
            allele_b
        )

        same_variant_id = (
            variant_a
            == variant_b
        )


        if status == EXACT_NORMALIZED_ALLELE:

            require(
                same_variant_id,
                (
                    f"candidate {candidate_number}: "
                    "exact normalized identity produced "
                    "different deterministic variant IDs"
                ),
            )


        if status != EXACT_NORMALIZED_ALLELE:

            require(
                not same_variant_id,
                (
                    f"candidate {candidate_number}: "
                    "non-exact candidate unexpectedly "
                    "produced the same deterministic "
                    "variant ID"
                ),
            )


        status_counts[
            status
        ] += 1

        same_variant_id_counts[
            str(
                same_variant_id
            ).upper()
        ] += 1


        classification_rows.append(
            {
                "candidate_number":
                    candidate_number,

                "run_a":
                    candidate["run_a"],

                "event_a":
                    event_a_id,

                "run_b":
                    candidate["run_b"],

                "event_b":
                    event_b_id,

                "phase1a_candidate_status":
                    candidate[
                        "equivalence_status"
                    ],

                "phase1a_normalized_allele_lookup_key":
                    candidate[
                        "normalized_allele_lookup_key"
                    ],

                "allele_a":
                    canonical_allele_text(
                        allele_a
                    ),

                "allele_b":
                    canonical_allele_text(
                        allele_b
                    ),

                "variant_id_a":
                    variant_a,

                "variant_id_b":
                    variant_b,

                "same_variant_id":
                    same_variant_id,

                "phase1b_identity_status":
                    status,

                "identity_method":
                    IDENTITY_METHOD,

                "identity_method_version":
                    IDENTITY_METHOD_VERSION,

                "representation_equivalence_evaluated":
                    False,

                "phase1a_entities_modified":
                    False,
            }
        )


    # --------------------------------------------------------
    # Completeness.
    # --------------------------------------------------------

    require(
        len(classification_rows)
        == EXPECTED_CANDIDATE_ROWS,
        (
            "not every candidate was classified: "
            f"{len(classification_rows)}"
        ),
    )


    require(
        sum(
            status_counts.values()
        )
        == EXPECTED_CANDIDATE_ROWS,
        (
            "classification accounting "
            "does not reconcile"
        ),
    )


    # --------------------------------------------------------
    # Write deterministic classification output.
    # --------------------------------------------------------

    fieldnames = [
        "candidate_number",
        "run_a",
        "event_a",
        "run_b",
        "event_b",
        "phase1a_candidate_status",
        "phase1a_normalized_allele_lookup_key",
        "allele_a",
        "allele_b",
        "variant_id_a",
        "variant_id_b",
        "same_variant_id",
        "phase1b_identity_status",
        "identity_method",
        "identity_method_version",
        "representation_equivalence_evaluated",
        "phase1a_entities_modified",
    ]


    with CLASSIFICATION_PATH.open(
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
            classification_rows
        )


    classification_sha = sha256_file(
        CLASSIFICATION_PATH
    )


    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    summary = {
        "phase":
            "1B",

        "operation":
            "REAL_CANDIDATE_IDENTITY_CLASSIFICATION",

        "candidate_input_sha256":
            candidate_sha,

        "structure_audit_sha256":
            structure_audit_sha,

        "candidate_count":
            len(classification_rows),

        "identity_method":
            IDENTITY_METHOD,

        "identity_method_version":
            IDENTITY_METHOD_VERSION,

        "representation_equivalence_supported_in_v1":
            False,

        "identity_status_counts":
            dict(
                sorted(
                    status_counts.items()
                )
            ),

        "same_variant_id_counts":
            dict(
                sorted(
                    same_variant_id_counts.items()
                )
            ),

        "phase1a_entities_modified":
            False,

        "classification_output":
            str(
                CLASSIFICATION_PATH.relative_to(
                    PROJECT_ROOT
                )
            ),

        "classification_output_sha256":
            classification_sha,
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
        "Identity status counts:"
    )

    for status, count in sorted(
        status_counts.items()
    ):

        print(
            f"  {status}: {count}"
        )


    print()

    print(
        "Same deterministic variant ID:"
    )

    for status, count in sorted(
        same_variant_id_counts.items()
    ):

        print(
            f"  {status}: {count}"
        )


    print()

    print(
        "classified candidates:",
        len(classification_rows),
    )

    print(
        "classification SHA-256:",
        classification_sha,
    )

    print(
        "summary SHA-256:",
        sha256_file(
            SUMMARY_PATH
        ),
    )

    print()

    print(
        "PHASE1B_REAL_CANDIDATE_CLASSIFICATION_PASS"
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
            "PHASE1B_REAL_CANDIDATE_CLASSIFICATION_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
