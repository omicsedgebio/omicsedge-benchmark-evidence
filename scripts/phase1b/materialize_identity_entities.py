#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from benchmark_evidence.phase1b_identity import (
    EXACT_NORMALIZED_ALLELE,
    IDENTITY_SCHEMA_VERSION,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PHASE1A_RESULTS = (
    PROJECT_ROOT
    / "data/phase1a/omicsedge_phase1a_results"
)

EVENTS_PATH = (
    PHASE1A_RESULTS
    / "events.parquet"
)

OBSERVATIONS_PATH = (
    PHASE1A_RESULTS
    / "observations.parquet"
)

CANDIDATES_PATH = (
    PHASE1A_RESULTS
    / "cross_run_candidates.tsv"
)

PHASE1A_CHECKSUMS_PATH = (
    PHASE1A_RESULTS
    / "checksums.sha256"
)

CLASSIFICATION_PATH = (
    PROJECT_ROOT
    / "results/phase1b/candidate_identity_classification.tsv"
)

GRAPH_AUDIT_PATH = (
    PROJECT_ROOT
    / "results/phase1b/identity_graph_audit.tsv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "results/phase1b"
)

VARIANTS_TSV = (
    OUTPUT_DIR
    / "variants.tsv"
)

VARIANTS_PARQUET = (
    OUTPUT_DIR
    / "variants.parquet"
)

LINKS_TSV = (
    OUTPUT_DIR
    / "event_variant_links.tsv"
)

LINKS_PARQUET = (
    OUTPUT_DIR
    / "event_variant_links.parquet"
)

SUMMARY_PATH = (
    OUTPUT_DIR
    / "entity_materialization_summary.json"
)


EXPECTED_PHASE1A_ARCHIVE_SHA256 = (
    "6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202"
)

EXPECTED_CANDIDATE_SHA256 = (
    "c9d0d50e8e96ce0fd98773ccf9fe306e9beac2186771fc89c76b959f91b7d758"
)

EXPECTED_CLASSIFICATION_SHA256 = (
    "b06f0c8a12b9f782a1ca73076906ce085cdff8191c09f7e00add7d028fa0f8fd"
)

EXPECTED_GRAPH_AUDIT_SHA256 = (
    "1cda3425d70e896c703ee37b37f688058628ed16ac756aa70bf305eef67617d2"
)

EXPECTED_CANDIDATES = 1666
EXPECTED_VARIANTS = 1666
EXPECTED_EVENT_VARIANT_LINKS = 3332

VARIANT_SCHEMA_VERSION = "1.0.0"
EVENT_VARIANT_LINK_SCHEMA_VERSION = "1.0.0"

IDENTITY_METHOD = (
    "PHASE1B_EXACT_NORMALIZED_ALLELE_V1"
)

IDENTITY_METHOD_VERSION = "1.0.0"

PHASE1A_CANDIDATE_STATUS = (
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


def canonical_json(
    value,
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def deterministic_id(
    prefix: str,
    payload: dict,
) -> str:

    encoded = canonical_json(
        payload
    ).encode("utf-8")

    digest = hashlib.sha256(
        encoded
    ).hexdigest()

    return (
        f"{prefix}:sha256:{digest}"
    )


def read_phase1a_detached_checksums() -> dict[str, str]:

    checksums = {}

    for raw in PHASE1A_CHECKSUMS_PATH.read_text(
        encoding="utf-8"
    ).splitlines():

        if not raw.strip():
            continue

        sha256, relative_path = raw.split(
            "  ",
            1,
        )

        checksums[
            relative_path
        ] = sha256

    return checksums


def verify_phase1a_file(
    path: Path,
    relative_path: str,
    detached_checksums: dict[str, str],
) -> str:

    require(
        relative_path
        in detached_checksums,
        (
            "Phase 1A detached checksum "
            f"missing for {relative_path}"
        ),
    )

    observed = sha256_file(
        path
    )

    expected = detached_checksums[
        relative_path
    ]

    require(
        observed == expected,
        (
            "Phase 1A file checksum mismatch\n"
            f"file: {relative_path}\n"
            f"expected: {expected}\n"
            f"observed: {observed}"
        ),
    )

    return observed


def candidate_id(
    candidate: dict,
) -> str:

    payload = {
        "run_a":
            candidate["run_a"],

        "event_a":
            candidate["event_a"],

        "run_b":
            candidate["run_b"],

        "event_b":
            candidate["event_b"],

        "normalized_allele_lookup_key":
            candidate[
                "normalized_allele_lookup_key"
            ],

        "equivalence_status":
            candidate[
                "equivalence_status"
            ],
    }

    return deterministic_id(
        "candidate",
        payload,
    )


def event_variant_link_id(
    event_id: str,
    variant_id: str,
    benchmark_run_id: str,
) -> str:

    payload = {
        "schema_version":
            EVENT_VARIANT_LINK_SCHEMA_VERSION,

        "event_id":
            event_id,

        "variant_id":
            variant_id,

        "benchmark_run_id":
            benchmark_run_id,

        "identity_status":
            EXACT_NORMALIZED_ALLELE,

        "identity_method":
            IDENTITY_METHOD,

        "identity_method_version":
            IDENTITY_METHOD_VERSION,
    }

    return deterministic_id(
        "event-variant-link",
        payload,
    )


def write_tsv(
    path: Path,
    rows: list[dict],
    fieldnames: list[str],
) -> None:

    with path.open(
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
            rows
        )


def main() -> int:

    print("=" * 78)

    print(
        "PROJECT 003 — PHASE 1B "
        "IDENTITY ENTITY MATERIALIZATION"
    )

    print("=" * 78)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    # --------------------------------------------------------
    # Verify prerequisite Phase 1B artifacts.
    # --------------------------------------------------------

    require(
        sha256_file(
            CANDIDATES_PATH
        )
        == EXPECTED_CANDIDATE_SHA256,
        "frozen candidate input changed",
    )

    print(
        "PASS  candidate input SHA-256"
    )


    require(
        sha256_file(
            CLASSIFICATION_PATH
        )
        == EXPECTED_CLASSIFICATION_SHA256,
        "candidate classification changed",
    )

    print(
        "PASS  classification SHA-256"
    )


    require(
        sha256_file(
            GRAPH_AUDIT_PATH
        )
        == EXPECTED_GRAPH_AUDIT_SHA256,
        "identity graph audit changed",
    )

    print(
        "PASS  identity graph audit SHA-256"
    )


    # --------------------------------------------------------
    # Verify immutable Phase 1A files before processing.
    # --------------------------------------------------------

    detached_checksums = (
        read_phase1a_detached_checksums()
    )

    events_sha_before = verify_phase1a_file(
        EVENTS_PATH,
        "events.parquet",
        detached_checksums,
    )

    observations_sha_before = verify_phase1a_file(
        OBSERVATIONS_PATH,
        "observations.parquet",
        detached_checksums,
    )

    print(
        "PASS  immutable Phase 1A event/observation inputs"
    )


    # --------------------------------------------------------
    # Load Phase 1A entities.
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


    event_index = {
        event["event_id"]:
            event
        for event in events
    }

    require(
        len(event_index)
        == len(events),
        "duplicate Phase 1A event IDs",
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
    # Load frozen candidate and classification tables.
    # --------------------------------------------------------

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


    with CLASSIFICATION_PATH.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:

        classifications = list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


    require(
        len(candidates)
        == EXPECTED_CANDIDATES,
        (
            f"expected {EXPECTED_CANDIDATES} candidates, "
            f"observed {len(candidates)}"
        ),
    )

    require(
        len(classifications)
        == EXPECTED_CANDIDATES,
        (
            "classification row count "
            "does not match candidate count"
        ),
    )


    # --------------------------------------------------------
    # Align candidates and classifications by frozen row.
    # --------------------------------------------------------

    classification_by_number = {
        int(
            row["candidate_number"]
        ):
            row
        for row in classifications
    }


    require(
        len(
            classification_by_number
        )
        == EXPECTED_CANDIDATES,
        "duplicate candidate_number in classifications",
    )


    variants_by_id = {}

    links_by_id = {}


    # --------------------------------------------------------
    # Materialize biological VARIANT records and
    # EVENT_VARIANT_LINK records.
    # --------------------------------------------------------

    for candidate_number, candidate in enumerate(
        candidates,
        start=1,
    ):

        classification = (
            classification_by_number[
                candidate_number
            ]
        )


        # ----------------------------------------------------
        # Frozen candidate/classification alignment.
        # ----------------------------------------------------

        for field in (
            "run_a",
            "event_a",
            "run_b",
            "event_b",
        ):

            require(
                candidate[field]
                == classification[field],
                (
                    f"candidate {candidate_number}: "
                    f"{field} mismatch between "
                    "candidate input and classification"
                ),
            )


        require(
            candidate[
                "equivalence_status"
            ]
            == PHASE1A_CANDIDATE_STATUS,
            (
                f"candidate {candidate_number}: "
                "unexpected Phase 1A status"
            ),
        )


        require(
            classification[
                "phase1b_identity_status"
            ]
            == EXACT_NORMALIZED_ALLELE,
            (
                f"candidate {candidate_number}: "
                "materialization currently requires "
                "EXACT_NORMALIZED_ALLELE"
            ),
        )


        require(
            classification[
                "variant_id_a"
            ]
            == classification[
                "variant_id_b"
            ],
            (
                f"candidate {candidate_number}: "
                "exact identity has different "
                "variant IDs"
            ),
        )


        shared_variant_id = (
            classification[
                "variant_id_a"
            ]
        )


        candidate_record_id = (
            candidate_id(
                candidate
            )
        )


        endpoint_data = []


        for side in (
            "a",
            "b",
        ):

            event_id = candidate[
                f"event_{side}"
            ]

            run_id = candidate[
                f"run_{side}"
            ]


            require(
                event_id
                in event_index,
                (
                    f"candidate {candidate_number}: "
                    f"missing event {event_id}"
                ),
            )


            event = event_index[
                event_id
            ]


            require(
                event[
                    "benchmark_run_id"
                ]
                == run_id,
                (
                    f"candidate {candidate_number}: "
                    f"run mismatch for {event_id}"
                ),
            )


            event_observations = (
                observations_by_event[
                    event_id
                ]
            )


            require(
                event_observations,
                (
                    f"candidate {candidate_number}: "
                    f"event has no observations: "
                    f"{event_id}"
                ),
            )


            normalized_alleles = {
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
                for obs
                in event_observations
            }


            require(
                len(
                    normalized_alleles
                )
                == 1,
                (
                    f"candidate {candidate_number}: "
                    f"event {event_id} does not "
                    "resolve to exactly one "
                    "normalized allele"
                ),
            )


            (
                start_0based,
                end_0based,
                normalized_ref,
                normalized_alt,
            ) = next(
                iter(
                    normalized_alleles
                )
            )


            normalization_methods = sorted(
                {
                    obs[
                        "normalization_method"
                    ]
                    for obs
                    in event_observations
                }
            )

            normalization_versions = sorted(
                {
                    obs[
                        "normalization_version"
                    ]
                    for obs
                    in event_observations
                }
            )


            require(
                len(
                    normalization_methods
                )
                == 1,
                (
                    f"candidate {candidate_number}: "
                    f"event {event_id} has multiple "
                    "normalization methods"
                ),
            )


            require(
                len(
                    normalization_versions
                )
                == 1,
                (
                    f"candidate {candidate_number}: "
                    f"event {event_id} has multiple "
                    "normalization versions"
                ),
            )


            endpoint_data.append(
                {
                    "event_id":
                        event_id,

                    "benchmark_run_id":
                        run_id,

                    "assembly":
                        event[
                            "assembly"
                        ],

                    "contig":
                        event[
                            "contig"
                        ],

                    "start_0based":
                        start_0based,

                    "end_0based":
                        end_0based,

                    "normalized_ref":
                        normalized_ref,

                    "normalized_alt":
                        normalized_alt,

                    "normalization_method":
                        normalization_methods[
                            0
                        ],

                    "normalization_version":
                        normalization_versions[
                            0
                        ],

                    "reference_artifact_id":
                        event[
                            "reference_artifact_id"
                        ],
                }
            )


        endpoint_a = endpoint_data[0]
        endpoint_b = endpoint_data[1]


        # ----------------------------------------------------
        # EXACT_NORMALIZED_ALLELE must mean actual equality
        # of every locked identity field.
        # ----------------------------------------------------

        exact_fields = (
            "assembly",
            "contig",
            "start_0based",
            "end_0based",
            "normalized_ref",
            "normalized_alt",
        )


        for field in exact_fields:

            require(
                endpoint_a[field]
                == endpoint_b[field],
                (
                    f"candidate {candidate_number}: "
                    "EXACT_NORMALIZED_ALLELE "
                    f"but {field} differs"
                ),
            )


        require(
            endpoint_a[
                "reference_artifact_id"
            ]
            ==
            endpoint_b[
                "reference_artifact_id"
            ],
            (
                f"candidate {candidate_number}: "
                "reference provenance differs "
                "between exact identity endpoints"
            ),
        )


        # ----------------------------------------------------
        # Create one shared biological VARIANT.
        # ----------------------------------------------------

        normalization_method = (
            "UPSTREAM_PHASE1A_NORMALIZED_FIELDS"
        )


        source_normalization_methods = sorted(
            {
                endpoint_a[
                    "normalization_method"
                ],
                endpoint_b[
                    "normalization_method"
                ],
            }
        )


        source_normalization_versions = sorted(
            {
                endpoint_a[
                    "normalization_version"
                ],
                endpoint_b[
                    "normalization_version"
                ],
            }
        )


        variant_row = {
            "schema_version":
                VARIANT_SCHEMA_VERSION,

            "variant_id":
                shared_variant_id,

            "assembly":
                endpoint_a[
                    "assembly"
                ],

            "contig":
                endpoint_a[
                    "contig"
                ],

            "normalized_start_0based":
                endpoint_a[
                    "start_0based"
                ],

            "normalized_end_0based":
                endpoint_a[
                    "end_0based"
                ],

            "normalized_ref":
                endpoint_a[
                    "normalized_ref"
                ],

            "normalized_alt":
                endpoint_a[
                    "normalized_alt"
                ],

            "normalization_method":
                normalization_method,

            "source_normalization_methods":
                ";".join(
                    source_normalization_methods
                ),

            "source_normalization_versions":
                ";".join(
                    source_normalization_versions
                ),

            "reference_artifact_id":
                endpoint_a[
                    "reference_artifact_id"
                ],

            "identity_schema_version":
                IDENTITY_SCHEMA_VERSION,

            "phase1b_origin":
                "GENERATED_FROM_EXACT_NORMALIZED_ALLELE",
        }


        if shared_variant_id in variants_by_id:

            require(
                variants_by_id[
                    shared_variant_id
                ]
                == variant_row,
                (
                    f"variant content conflict for "
                    f"{shared_variant_id}"
                ),
            )

        else:

            variants_by_id[
                shared_variant_id
            ] = variant_row


        # ----------------------------------------------------
        # Create one EVENT_VARIANT_LINK per endpoint.
        # ----------------------------------------------------

        for endpoint in endpoint_data:

            link_id = (
                event_variant_link_id(
                    endpoint[
                        "event_id"
                    ],
                    shared_variant_id,
                    endpoint[
                        "benchmark_run_id"
                    ],
                )
            )


            evidence = {
                "candidate_number":
                    candidate_number,

                "candidate_id":
                    candidate_record_id,

                "phase1a_normalized_allele_lookup_key":
                    candidate[
                        "normalized_allele_lookup_key"
                    ],

                "assembly":
                    endpoint[
                        "assembly"
                    ],

                "contig":
                    endpoint[
                        "contig"
                    ],

                "normalized_start_0based":
                    endpoint[
                        "start_0based"
                    ],

                "normalized_end_0based":
                    endpoint[
                        "end_0based"
                    ],

                "normalized_ref":
                    endpoint[
                        "normalized_ref"
                    ],

                "normalized_alt":
                    endpoint[
                        "normalized_alt"
                    ],
            }


            provenance = {
                "phase1a_archive_sha256":
                    EXPECTED_PHASE1A_ARCHIVE_SHA256,

                "phase1a_candidate_input_sha256":
                    EXPECTED_CANDIDATE_SHA256,

                "phase1b_classification_sha256":
                    EXPECTED_CLASSIFICATION_SHA256,

                "phase1b_graph_audit_sha256":
                    EXPECTED_GRAPH_AUDIT_SHA256,

                "source_event_id":
                    endpoint[
                        "event_id"
                    ],

                "source_benchmark_run_id":
                    endpoint[
                        "benchmark_run_id"
                    ],

                "reference_artifact_id":
                    endpoint[
                        "reference_artifact_id"
                    ],
            }


            link_row = {
                "schema_version":
                    EVENT_VARIANT_LINK_SCHEMA_VERSION,

                "event_variant_link_id":
                    link_id,

                "event_id":
                    endpoint[
                        "event_id"
                    ],

                "variant_id":
                    shared_variant_id,

                "benchmark_run_id":
                    endpoint[
                        "benchmark_run_id"
                    ],

                "identity_status":
                    EXACT_NORMALIZED_ALLELE,

                "identity_method":
                    IDENTITY_METHOD,

                "identity_method_version":
                    IDENTITY_METHOD_VERSION,

                "evidence":
                    canonical_json(
                        evidence
                    ),

                "provenance":
                    canonical_json(
                        provenance
                    ),

                "created_from_candidate":
                    True,

                "candidate_id":
                    candidate_record_id,

                "candidate_number":
                    candidate_number,

                "phase1a_candidate_status":
                    candidate[
                        "equivalence_status"
                    ],
            }


            if link_id in links_by_id:

                require(
                    links_by_id[
                        link_id
                    ]
                    == link_row,
                    (
                        "EVENT_VARIANT_LINK content "
                        f"conflict for {link_id}"
                    ),
                )

            else:

                links_by_id[
                    link_id
                ] = link_row


    # --------------------------------------------------------
    # Deterministic sorting.
    # --------------------------------------------------------

    variant_rows = sorted(
        variants_by_id.values(),
        key=lambda row: row[
            "variant_id"
        ],
    )


    link_rows = sorted(
        links_by_id.values(),
        key=lambda row: row[
            "event_variant_link_id"
        ],
    )


    # --------------------------------------------------------
    # Locked observed-graph expectations.
    # --------------------------------------------------------

    require(
        len(
            variant_rows
        )
        == EXPECTED_VARIANTS,
        (
            f"expected {EXPECTED_VARIANTS} VARIANTs, "
            f"observed {len(variant_rows)}"
        ),
    )


    require(
        len(
            link_rows
        )
        == EXPECTED_EVENT_VARIANT_LINKS,
        (
            "expected "
            f"{EXPECTED_EVENT_VARIANT_LINKS} "
            "EVENT_VARIANT_LINKs, "
            f"observed {len(link_rows)}"
        ),
    )


    linked_event_ids = {
        row[
            "event_id"
        ]
        for row
        in link_rows
    }


    require(
        len(
            linked_event_ids
        )
        == EXPECTED_EVENT_VARIANT_LINKS,
        (
            "an event appears in more than one "
            "EVENT_VARIANT_LINK"
        ),
    )


    # --------------------------------------------------------
    # Every materialized VARIANT must have exactly 2 linked
    # events and exactly 2 benchmark runs in this Phase 1B
    # candidate graph.
    # --------------------------------------------------------

    links_by_variant = defaultdict(
        list
    )


    for row in link_rows:

        links_by_variant[
            row["variant_id"]
        ].append(
            row
        )


    for variant_id_value, variant_links in (
        links_by_variant.items()
    ):

        require(
            len(
                variant_links
            )
            == 2,
            (
                f"{variant_id_value} has "
                f"{len(variant_links)} links; "
                "expected 2"
            ),
        )


        require(
            len(
                {
                    row[
                        "benchmark_run_id"
                    ]
                    for row
                    in variant_links
                }
            )
            == 2,
            (
                f"{variant_id_value} does not "
                "span exactly two benchmark runs"
            ),
        )


    # --------------------------------------------------------
    # Write TSV entities.
    # --------------------------------------------------------

    variant_fields = [
        "schema_version",
        "variant_id",
        "assembly",
        "contig",
        "normalized_start_0based",
        "normalized_end_0based",
        "normalized_ref",
        "normalized_alt",
        "normalization_method",
        "source_normalization_methods",
        "source_normalization_versions",
        "reference_artifact_id",
        "identity_schema_version",
        "phase1b_origin",
    ]


    link_fields = [
        "schema_version",
        "event_variant_link_id",
        "event_id",
        "variant_id",
        "benchmark_run_id",
        "identity_status",
        "identity_method",
        "identity_method_version",
        "evidence",
        "provenance",
        "created_from_candidate",
        "candidate_id",
        "candidate_number",
        "phase1a_candidate_status",
    ]


    write_tsv(
        VARIANTS_TSV,
        variant_rows,
        variant_fields,
    )


    write_tsv(
        LINKS_TSV,
        link_rows,
        link_fields,
    )


    # --------------------------------------------------------
    # Write Parquet entities.
    # --------------------------------------------------------

    pq.write_table(
        pa.Table.from_pylist(
            variant_rows
        ),
        VARIANTS_PARQUET,
        compression="zstd",
    )


    pq.write_table(
        pa.Table.from_pylist(
            link_rows
        ),
        LINKS_PARQUET,
        compression="zstd",
    )


    # --------------------------------------------------------
    # Round-trip validation.
    # --------------------------------------------------------

    returned_variants = (
        pq.read_table(
            VARIANTS_PARQUET
        )
        .to_pylist()
    )


    returned_links = (
        pq.read_table(
            LINKS_PARQUET
        )
        .to_pylist()
    )


    require(
        len(
            returned_variants
        )
        == len(
            variant_rows
        ),
        "VARIANT Parquet row-count mismatch",
    )


    require(
        len(
            returned_links
        )
        == len(
            link_rows
        ),
        (
            "EVENT_VARIANT_LINK Parquet "
            "row-count mismatch"
        ),
    )


    require(
        {
            row[
                "variant_id"
            ]
            for row
            in returned_variants
        }
        ==
        {
            row[
                "variant_id"
            ]
            for row
            in variant_rows
        },
        "VARIANT Parquet ID mismatch",
    )


    require(
        {
            row[
                "event_variant_link_id"
            ]
            for row
            in returned_links
        }
        ==
        {
            row[
                "event_variant_link_id"
            ]
            for row
            in link_rows
        },
        (
            "EVENT_VARIANT_LINK "
            "Parquet ID mismatch"
        ),
    )


    # --------------------------------------------------------
    # Verify Phase 1A immutable inputs did not change.
    # --------------------------------------------------------

    events_sha_after = sha256_file(
        EVENTS_PATH
    )

    observations_sha_after = sha256_file(
        OBSERVATIONS_PATH
    )


    require(
        events_sha_after
        == events_sha_before,
        (
            "Phase 1A events.parquet changed "
            "during Phase 1B materialization"
        ),
    )


    require(
        observations_sha_after
        == observations_sha_before,
        (
            "Phase 1A observations.parquet changed "
            "during Phase 1B materialization"
        ),
    )


    print(
        "PASS  Phase 1A EVENT records unchanged"
    )

    print(
        "PASS  Phase 1A OBSERVATION records unchanged"
    )


    # --------------------------------------------------------
    # Output identities.
    # --------------------------------------------------------

    output_checksums = {
        "variants.tsv":
            sha256_file(
                VARIANTS_TSV
            ),

        "variants.parquet":
            sha256_file(
                VARIANTS_PARQUET
            ),

        "event_variant_links.tsv":
            sha256_file(
                LINKS_TSV
            ),

        "event_variant_links.parquet":
            sha256_file(
                LINKS_PARQUET
            ),
    }


    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    summary = {
        "project":
            "Project 003",

        "phase":
            "1B",

        "operation":
            "IDENTITY_ENTITY_MATERIALIZATION",

        "phase1a_archive_sha256":
            EXPECTED_PHASE1A_ARCHIVE_SHA256,

        "candidate_input_sha256":
            EXPECTED_CANDIDATE_SHA256,

        "classification_sha256":
            EXPECTED_CLASSIFICATION_SHA256,

        "identity_graph_audit_sha256":
            EXPECTED_GRAPH_AUDIT_SHA256,

        "variant_count":
            len(
                variant_rows
            ),

        "event_variant_link_count":
            len(
                link_rows
            ),

        "unique_linked_event_count":
            len(
                linked_event_ids
            ),

        "identity_status":
            EXACT_NORMALIZED_ALLELE,

        "identity_method":
            IDENTITY_METHOD,

        "identity_method_version":
            IDENTITY_METHOD_VERSION,

        "identity_schema_version":
            IDENTITY_SCHEMA_VERSION,

        "representation_equivalence_evaluated":
            False,

        "phase1a_entities_modified":
            False,

        "phase1a_events_sha256_before":
            events_sha_before,

        "phase1a_events_sha256_after":
            events_sha_after,

        "phase1a_observations_sha256_before":
            observations_sha_before,

        "phase1a_observations_sha256_after":
            observations_sha_after,

        "output_checksums":
            output_checksums,
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
    # Human-readable result.
    # --------------------------------------------------------

    print()

    print(
        "VARIANT rows:",
        len(
            variant_rows
        ),
    )

    print(
        "EVENT_VARIANT_LINK rows:",
        len(
            link_rows
        ),
    )

    print(
        "unique linked Phase 1A events:",
        len(
            linked_event_ids
        ),
    )

    print()

    print(
        "Output SHA-256:"
    )

    for name, digest in sorted(
        output_checksums.items()
    ):

        print(
            f"  {name}: {digest}"
        )


    print(
        "  entity_materialization_summary.json:",
        sha256_file(
            SUMMARY_PATH
        ),
    )


    print()

    print(
        "PHASE1B_IDENTITY_ENTITY_MATERIALIZATION_PASS"
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
            "PHASE1B_IDENTITY_ENTITY_MATERIALIZATION_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
