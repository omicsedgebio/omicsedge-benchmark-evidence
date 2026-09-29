#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from benchmark_evidence.phase1b_identity import (
    EXACT_NORMALIZED_ALLELE,
    IDENTITY_SCHEMA_VERSION,
    classify_identity,
    variant_id,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PHASE1A = (
    PROJECT_ROOT
    / "data/phase1a/omicsedge_phase1a_results"
)

PHASE1B = (
    PROJECT_ROOT
    / "results/phase1b"
)

CANDIDATES_PATH = (
    PHASE1A
    / "cross_run_candidates.tsv"
)

EVENTS_PATH = (
    PHASE1A
    / "events.parquet"
)

OBSERVATIONS_PATH = (
    PHASE1A
    / "observations.parquet"
)

CANONICAL_CLASSIFICATION = (
    PHASE1B
    / "candidate_identity_classification.tsv"
)

CANONICAL_VARIANTS_TSV = (
    PHASE1B
    / "variants.tsv"
)

CANONICAL_VARIANTS_PARQUET = (
    PHASE1B
    / "variants.parquet"
)

CANONICAL_LINKS_TSV = (
    PHASE1B
    / "event_variant_links.tsv"
)

CANONICAL_LINKS_PARQUET = (
    PHASE1B
    / "event_variant_links.parquet"
)


EXPECTED = {
    "candidate_sha256":
        "c9d0d50e8e96ce0fd98773ccf9fe306e9beac2186771fc89c76b959f91b7d758",

    "classification_sha256":
        "b06f0c8a12b9f782a1ca73076906ce085cdff8191c09f7e00add7d028fa0f8fd",

    "variants_tsv_sha256":
        "4d1f4111a4d6190bf9b0a5a7d44b21abf451cd8c5aaa2ad9470e73a7548d8896",

    "variants_parquet_sha256":
        "c08939e19a71f140dd7c1901df0a7eafd528a4d35c4808701c3282cb4a008968",

    "links_tsv_sha256":
        "2d8f81de2009bfb05d1871299815bd32d636df1d70096f592db82829db9a46a2",

    "links_parquet_sha256":
        "bd695855e3e9fb6c80bd5d16d93f1a64bffc25da71754614f640e225bdb1e76e",

    "candidate_count":
        1666,

    "variant_count":
        1666,

    "link_count":
        3332,
}


PHASE1A_ARCHIVE_SHA256 = (
    "6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202"
)

GRAPH_AUDIT_SHA256 = (
    "1cda3425d70e896c703ee37b37f688058628ed16ac756aa70bf305eef67617d2"
)

IDENTITY_METHOD = (
    "PHASE1B_EXACT_NORMALIZED_ALLELE_V1"
)

IDENTITY_METHOD_VERSION = "1.0.0"

VARIANT_SCHEMA_VERSION = "1.0.0"

EVENT_VARIANT_LINK_SCHEMA_VERSION = "1.0.0"

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


def canonical_json(value) -> str:

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

    digest = hashlib.sha256(
        canonical_json(
            payload
        ).encode("utf-8")
    ).hexdigest()

    return (
        f"{prefix}:sha256:{digest}"
    )


def make_candidate_id(
    candidate: dict,
) -> str:

    return deterministic_id(
        "candidate",
        {
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
        },
    )


def make_link_id(
    event_id: str,
    variant_id_value: str,
    benchmark_run_id: str,
) -> str:

    return deterministic_id(
        "event-variant-link",
        {
            "schema_version":
                EVENT_VARIANT_LINK_SCHEMA_VERSION,

            "event_id":
                event_id,

            "variant_id":
                variant_id_value,

            "benchmark_run_id":
                benchmark_run_id,

            "identity_status":
                EXACT_NORMALIZED_ALLELE,

            "identity_method":
                IDENTITY_METHOD,

            "identity_method_version":
                IDENTITY_METHOD_VERSION,
        },
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
        writer.writerows(rows)


def allele_from(
    event: dict,
    observation: dict,
) -> dict:

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


def allele_text(
    allele: dict,
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
        "DETERMINISTIC REPRODUCIBILITY"
    )

    print("=" * 78)

    # --------------------------------------------------------
    # Verify canonical inputs and outputs first.
    # --------------------------------------------------------

    require(
        sha256_file(
            CANDIDATES_PATH
        )
        == EXPECTED[
            "candidate_sha256"
        ],
        "frozen candidate input changed",
    )

    require(
        sha256_file(
            CANONICAL_CLASSIFICATION
        )
        == EXPECTED[
            "classification_sha256"
        ],
        "canonical classification changed",
    )

    require(
        sha256_file(
            CANONICAL_VARIANTS_TSV
        )
        == EXPECTED[
            "variants_tsv_sha256"
        ],
        "canonical variants.tsv changed",
    )

    require(
        sha256_file(
            CANONICAL_VARIANTS_PARQUET
        )
        == EXPECTED[
            "variants_parquet_sha256"
        ],
        "canonical variants.parquet changed",
    )

    require(
        sha256_file(
            CANONICAL_LINKS_TSV
        )
        == EXPECTED[
            "links_tsv_sha256"
        ],
        "canonical event_variant_links.tsv changed",
    )

    require(
        sha256_file(
            CANONICAL_LINKS_PARQUET
        )
        == EXPECTED[
            "links_parquet_sha256"
        ],
        "canonical event_variant_links.parquet changed",
    )

    print(
        "PASS  canonical artifact checksums"
    )


    # --------------------------------------------------------
    # Load immutable Phase 1A inputs.
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
        == EXPECTED[
            "candidate_count"
        ],
        "candidate count changed",
    )


    event_index = {
        row["event_id"]:
            row
        for row in events
    }

    observations_by_event = defaultdict(
        list
    )

    for row in observations:

        observations_by_event[
            row["event_id"]
        ].append(
            row
        )


    # --------------------------------------------------------
    # Independent classification rebuild.
    # --------------------------------------------------------

    classification_rows = []


    for candidate_number, candidate in enumerate(
        candidates,
        start=1,
    ):

        require(
            candidate[
                "equivalence_status"
            ]
            == PHASE1A_CANDIDATE_STATUS,
            (
                "unexpected Phase 1A "
                "candidate status"
            ),
        )


        event_a = event_index[
            candidate["event_a"]
        ]

        event_b = event_index[
            candidate["event_b"]
        ]


        obs_a = observations_by_event[
            candidate["event_a"]
        ]

        obs_b = observations_by_event[
            candidate["event_b"]
        ]


        require(
            obs_a and obs_b,
            "candidate event missing observation",
        )


        allele_set_a = {
            (
                row[
                    "normalized_start_0based"
                ],
                row[
                    "normalized_end_0based"
                ],
                row[
                    "normalized_ref"
                ],
                row[
                    "normalized_alt"
                ],
            )
            for row in obs_a
        }

        allele_set_b = {
            (
                row[
                    "normalized_start_0based"
                ],
                row[
                    "normalized_end_0based"
                ],
                row[
                    "normalized_ref"
                ],
                row[
                    "normalized_alt"
                ],
            )
            for row in obs_b
        }


        require(
            len(allele_set_a) == 1,
            "event_a has multiple normalized alleles",
        )

        require(
            len(allele_set_b) == 1,
            "event_b has multiple normalized alleles",
        )


        allele_a = allele_from(
            event_a,
            obs_a[0],
        )

        allele_b = allele_from(
            event_b,
            obs_b[0],
        )


        status = classify_identity(
            allele_a,
            allele_b,
        )


        variant_a = variant_id(
            allele_a
        )

        variant_b = variant_id(
            allele_b
        )


        require(
            status
            == EXACT_NORMALIZED_ALLELE,
            (
                "independent rebuild produced "
                f"unexpected status: {status}"
            ),
        )

        require(
            variant_a == variant_b,
            (
                "independent exact identity "
                "produced different variant IDs"
            ),
        )


        classification_rows.append(
            {
                "candidate_number":
                    candidate_number,

                "run_a":
                    candidate["run_a"],

                "event_a":
                    candidate["event_a"],

                "run_b":
                    candidate["run_b"],

                "event_b":
                    candidate["event_b"],

                "phase1a_candidate_status":
                    candidate[
                        "equivalence_status"
                    ],

                "phase1a_normalized_allele_lookup_key":
                    candidate[
                        "normalized_allele_lookup_key"
                    ],

                "allele_a":
                    allele_text(
                        allele_a
                    ),

                "allele_b":
                    allele_text(
                        allele_b
                    ),

                "variant_id_a":
                    variant_a,

                "variant_id_b":
                    variant_b,

                "same_variant_id":
                    True,

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
    # Independently rebuild VARIANT and EVENT_VARIANT_LINK.
    # --------------------------------------------------------

    variants_by_id = {}
    links_by_id = {}


    for row in classification_rows:

        candidate_number = int(
            row["candidate_number"]
        )

        candidate = candidates[
            candidate_number - 1
        ]

        shared_variant_id = row[
            "variant_id_a"
        ]

        candidate_record_id = (
            make_candidate_id(
                candidate
            )
        )


        endpoints = []


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

            event = event_index[
                event_id
            ]

            event_observations = (
                observations_by_event[
                    event_id
                ]
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
                    "independent entity rebuild "
                    "found multiple alleles"
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
                    "multiple normalization "
                    "methods found"
                ),
            )

            require(
                len(
                    normalization_versions
                )
                == 1,
                (
                    "multiple normalization "
                    "versions found"
                ),
            )


            endpoints.append(
                {
                    "event_id":
                        event_id,

                    "benchmark_run_id":
                        run_id,

                    "assembly":
                        event["assembly"],

                    "contig":
                        event["contig"],

                    "start_0based":
                        start_0based,

                    "end_0based":
                        end_0based,

                    "normalized_ref":
                        normalized_ref,

                    "normalized_alt":
                        normalized_alt,

                    "normalization_method":
                        normalization_methods[0],

                    "normalization_version":
                        normalization_versions[0],

                    "reference_artifact_id":
                        event[
                            "reference_artifact_id"
                        ],
                }
            )


        a = endpoints[0]
        b = endpoints[1]


        for field in (
            "assembly",
            "contig",
            "start_0based",
            "end_0based",
            "normalized_ref",
            "normalized_alt",
        ):

            require(
                a[field] == b[field],
                (
                    "independent rebuild found "
                    f"exact-identity mismatch: {field}"
                ),
            )


        source_methods = sorted(
            {
                a[
                    "normalization_method"
                ],
                b[
                    "normalization_method"
                ],
            }
        )

        source_versions = sorted(
            {
                a[
                    "normalization_version"
                ],
                b[
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
                a["assembly"],

            "contig":
                a["contig"],

            "normalized_start_0based":
                a["start_0based"],

            "normalized_end_0based":
                a["end_0based"],

            "normalized_ref":
                a["normalized_ref"],

            "normalized_alt":
                a["normalized_alt"],

            "normalization_method":
                "UPSTREAM_PHASE1A_NORMALIZED_FIELDS",

            "source_normalization_methods":
                ";".join(
                    source_methods
                ),

            "source_normalization_versions":
                ";".join(
                    source_versions
                ),

            "reference_artifact_id":
                a[
                    "reference_artifact_id"
                ],

            "identity_schema_version":
                IDENTITY_SCHEMA_VERSION,

            "phase1b_origin":
                "GENERATED_FROM_EXACT_NORMALIZED_ALLELE",
        }


        previous_variant = (
            variants_by_id.get(
                shared_variant_id
            )
        )

        if previous_variant is not None:

            require(
                previous_variant
                == variant_row,
                "variant rebuild conflict",
            )

        else:

            variants_by_id[
                shared_variant_id
            ] = variant_row


        for endpoint in endpoints:

            link_id = make_link_id(
                endpoint[
                    "event_id"
                ],
                shared_variant_id,
                endpoint[
                    "benchmark_run_id"
                ],
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
                    PHASE1A_ARCHIVE_SHA256,

                "phase1a_candidate_input_sha256":
                    EXPECTED[
                        "candidate_sha256"
                    ],

                "phase1b_classification_sha256":
                    EXPECTED[
                        "classification_sha256"
                    ],

                "phase1b_graph_audit_sha256":
                    GRAPH_AUDIT_SHA256,

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


            previous_link = (
                links_by_id.get(
                    link_id
                )
            )

            if previous_link is not None:

                require(
                    previous_link
                    == link_row,
                    "link rebuild conflict",
                )

            else:

                links_by_id[
                    link_id
                ] = link_row


    variants = sorted(
        variants_by_id.values(),
        key=lambda row: row[
            "variant_id"
        ],
    )

    links = sorted(
        links_by_id.values(),
        key=lambda row: row[
            "event_variant_link_id"
        ],
    )


    require(
        len(
            classification_rows
        )
        == EXPECTED[
            "candidate_count"
        ],
        "classification count mismatch",
    )

    require(
        len(variants)
        == EXPECTED[
            "variant_count"
        ],
        "variant count mismatch",
    )

    require(
        len(links)
        == EXPECTED[
            "link_count"
        ],
        "link count mismatch",
    )


    print(
        "PASS  independent row counts "
        "1666 classifications / "
        "1666 variants / 3332 links"
    )


    # --------------------------------------------------------
    # Write independent artifacts into temporary directory.
    # --------------------------------------------------------

    classification_fields = [
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


    with tempfile.TemporaryDirectory(
        prefix="omicsedge-phase1b-repro-"
    ) as tmp:

        tmpdir = Path(tmp)

        rebuilt_classification = (
            tmpdir
            / "candidate_identity_classification.tsv"
        )

        rebuilt_variants_tsv = (
            tmpdir
            / "variants.tsv"
        )

        rebuilt_variants_parquet = (
            tmpdir
            / "variants.parquet"
        )

        rebuilt_links_tsv = (
            tmpdir
            / "event_variant_links.tsv"
        )

        rebuilt_links_parquet = (
            tmpdir
            / "event_variant_links.parquet"
        )


        write_tsv(
            rebuilt_classification,
            classification_rows,
            classification_fields,
        )

        write_tsv(
            rebuilt_variants_tsv,
            variants,
            variant_fields,
        )

        write_tsv(
            rebuilt_links_tsv,
            links,
            link_fields,
        )


        pq.write_table(
            pa.Table.from_pylist(
                variants
            ),
            rebuilt_variants_parquet,
            compression="zstd",
        )

        pq.write_table(
            pa.Table.from_pylist(
                links
            ),
            rebuilt_links_parquet,
            compression="zstd",
        )


        rebuilt_hashes = {
            "classification":
                sha256_file(
                    rebuilt_classification
                ),

            "variants_tsv":
                sha256_file(
                    rebuilt_variants_tsv
                ),

            "variants_parquet":
                sha256_file(
                    rebuilt_variants_parquet
                ),

            "links_tsv":
                sha256_file(
                    rebuilt_links_tsv
                ),

            "links_parquet":
                sha256_file(
                    rebuilt_links_parquet
                ),
        }


        require(
            rebuilt_hashes[
                "classification"
            ]
            == EXPECTED[
                "classification_sha256"
            ],
            (
                "classification rebuild "
                "is not byte-identical"
            ),
        )


        require(
            rebuilt_hashes[
                "variants_tsv"
            ]
            == EXPECTED[
                "variants_tsv_sha256"
            ],
            (
                "variants.tsv rebuild "
                "is not byte-identical"
            ),
        )


        require(
            rebuilt_hashes[
                "variants_parquet"
            ]
            == EXPECTED[
                "variants_parquet_sha256"
            ],
            (
                "variants.parquet rebuild "
                "is not byte-identical"
            ),
        )


        require(
            rebuilt_hashes[
                "links_tsv"
            ]
            == EXPECTED[
                "links_tsv_sha256"
            ],
            (
                "event_variant_links.tsv rebuild "
                "is not byte-identical"
            ),
        )


        require(
            rebuilt_hashes[
                "links_parquet"
            ]
            == EXPECTED[
                "links_parquet_sha256"
            ],
            (
                "event_variant_links.parquet rebuild "
                "is not byte-identical"
            ),
        )


        print(
            "PASS  independent classification "
            "is byte-identical"
        )

        print(
            "PASS  independent variants.tsv "
            "is byte-identical"
        )

        print(
            "PASS  independent variants.parquet "
            "is byte-identical"
        )

        print(
            "PASS  independent "
            "event_variant_links.tsv "
            "is byte-identical"
        )

        print(
            "PASS  independent "
            "event_variant_links.parquet "
            "is byte-identical"
        )


    # --------------------------------------------------------
    # ID-level comparisons against canonical entities.
    # --------------------------------------------------------

    canonical_variants = (
        pq.read_table(
            CANONICAL_VARIANTS_PARQUET
        )
        .to_pylist()
    )

    canonical_links = (
        pq.read_table(
            CANONICAL_LINKS_PARQUET
        )
        .to_pylist()
    )


    rebuilt_variant_ids = {
        row["variant_id"]
        for row in variants
    }

    canonical_variant_ids = {
        row["variant_id"]
        for row in canonical_variants
    }


    rebuilt_link_ids = {
        row["event_variant_link_id"]
        for row in links
    }

    canonical_link_ids = {
        row["event_variant_link_id"]
        for row in canonical_links
    }


    require(
        rebuilt_variant_ids
        == canonical_variant_ids,
        "VARIANT ID set mismatch",
    )

    require(
        rebuilt_link_ids
        == canonical_link_ids,
        "EVENT_VARIANT_LINK ID set mismatch",
    )


    print(
        "PASS  deterministic VARIANT ID set"
    )

    print(
        "PASS  deterministic "
        "EVENT_VARIANT_LINK ID set"
    )


    print()

    print(
        "PHASE1B_DETERMINISTIC_REPRODUCIBILITY_PASS"
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
            "PHASE1B_DETERMINISTIC_REPRODUCIBILITY_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
