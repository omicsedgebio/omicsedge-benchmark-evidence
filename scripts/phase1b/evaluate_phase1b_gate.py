#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import pyarrow.parquet as pq

from benchmark_evidence.phase1b_identity import (
    EXACT_NORMALIZED_ALLELE,
    REPRESENTATION_EQUIVALENCE_SUPPORTED,
    UNRESOLVED,
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

PROTOCOL_PATH = (
    PROJECT_ROOT
    / "docs/phase1b/phase1b_protocol.md"
)

FREEZE_MANIFEST_PATH = (
    PROJECT_ROOT
    / "data/phase1b/phase1b_freeze_manifest.tsv"
)

PHASE1A_ARCHIVE = (
    PROJECT_ROOT
    / "data/phase1a/omicsedge_phase1a_results.tar.gz"
)

PHASE1A_CHECKSUMS = (
    PHASE1A
    / "checksums.sha256"
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

EXPERIMENTS_PATH = (
    PHASE1A
    / "experiments.tsv"
)

RUNS_PATH = (
    PHASE1A
    / "benchmark_runs.tsv"
)

VARIANTS_PATH = (
    PHASE1B
    / "variants.parquet"
)

LINKS_PATH = (
    PHASE1B
    / "event_variant_links.parquet"
)

CLASSIFICATION_PATH = (
    PHASE1B
    / "candidate_identity_classification.tsv"
)

QUERY_SQL_PATH = (
    PROJECT_ROOT
    / "sql/phase1b/variant_evidence.sql"
)

SYNTHETIC_CASES_PATH = (
    PROJECT_ROOT
    / "tests/phase1b/synthetic_identity_cases.tsv"
)

VALIDATION_TSV = (
    PHASE1B
    / "phase1b_validation.tsv"
)

VALIDATION_JSON = (
    PHASE1B
    / "phase1b_validation.json"
)

REPORT_PATH = (
    PHASE1B
    / "phase1b_gate_report.md"
)


EXPECTED = {
    "protocol_sha256":
        "ec1833c55877b25c37be24483f8598ff89efb18850f4d733a08b492e55ef5c45",

    "freeze_manifest_sha256":
        "5e17d1d0cb7d9d7339ace8cfe1cef829303dd7e628057983a9f220a16bd7b69d",

    "phase1a_archive_sha256":
        "6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202",

    "candidate_sha256":
        "c9d0d50e8e96ce0fd98773ccf9fe306e9beac2186771fc89c76b959f91b7d758",

    "synthetic_cases_sha256":
        "b5570acd87ad721c1a8cabc416d3630455c0417715b0b6c73d70eff1aa3f5c27",

    "classification_sha256":
        "b06f0c8a12b9f782a1ca73076906ce085cdff8191c09f7e00add7d028fa0f8fd",

    "variants_sha256":
        "c08939e19a71f140dd7c1901df0a7eafd528a4d35c4808701c3282cb4a008968",

    "links_sha256":
        "bd695855e3e9fb6c80bd5d16d93f1a64bffc25da71754614f640e225bdb1e76e",

    "candidate_count":
        1666,

    "variant_count":
        1666,

    "link_count":
        3332,

    "phase1a_checksum_count":
        35,
}


CRITICAL_STOP_CRITERIA = {
    4,   # Phase 1A mutation
    5,   # candidate disappearance
    7,   # unsafe exact-identity assertion
    8,   # cross-assembly unsafe merge
    11,  # forced ambiguous equivalence
    12,  # provenance failure
}


FORBIDDEN_PRODUCT_FIELDS = {
    "consensus",
    "consensus_decision",
    "reliability_score",
    "confidence_score",
    "trust_score",
    "trusted",
    "technology_winner",
    "technology_rank",
}


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


def read_tsv(path: Path) -> list[dict]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        return list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


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


def parse_locked_criteria(
    protocol_text: str,
) -> dict[int, str]:

    start_marker = (
        "## Locked Phase 1B Validation Criteria"
    )

    end_marker = "## Outcome Gate"

    require(
        start_marker in protocol_text,
        "locked validation section missing",
    )

    require(
        end_marker in protocol_text,
        "outcome gate section missing",
    )

    section = (
        protocol_text
        .split(
            start_marker,
            1,
        )[1]
        .split(
            end_marker,
            1,
        )[0]
    )

    criteria = {}
    current = None
    parts = []

    for raw in section.splitlines():

        match = re.match(
            r"^(\d+)\.\s+(.*)$",
            raw,
        )

        if match:

            if current is not None:
                criteria[current] = (
                    " ".join(
                        parts
                    ).strip()
                )

            current = int(
                match.group(1)
            )

            parts = [
                match.group(2).strip()
            ]

        elif (
            current is not None
            and raw.strip()
        ):
            parts.append(
                raw.strip()
            )

    if current is not None:
        criteria[current] = (
            " ".join(
                parts
            ).strip()
        )

    require(
        set(criteria)
        == set(
            range(
                1,
                16,
            )
        ),
        (
            "expected exactly 15 frozen "
            f"criteria; found {sorted(criteria)}"
        ),
    )

    return criteria


def verify_all_phase1a_checksums() -> tuple[
    bool,
    dict,
]:

    records = []

    for raw in PHASE1A_CHECKSUMS.read_text(
        encoding="utf-8"
    ).splitlines():

        if not raw.strip():
            continue

        expected_sha, relative = raw.split(
            "  ",
            1,
        )

        records.append(
            (
                expected_sha,
                relative,
            )
        )

    failures = []

    for expected_sha, relative in records:

        path = (
            PHASE1A
            / relative
        )

        if not path.is_file():

            failures.append(
                {
                    "file":
                        relative,

                    "reason":
                        "MISSING",
                }
            )

            continue

        observed = sha256_file(
            path
        )

        if observed != expected_sha:

            failures.append(
                {
                    "file":
                        relative,

                    "reason":
                        "SHA256_MISMATCH",

                    "expected":
                        expected_sha,

                    "observed":
                        observed,
                }
            )

    passed = (
        len(records)
        == EXPECTED[
            "phase1a_checksum_count"
        ]
        and
        not failures
    )

    evidence = {
        "expected_checksum_records":
            EXPECTED[
                "phase1a_checksum_count"
            ],

        "observed_checksum_records":
            len(records),

        "failures":
            failures,
    }

    return (
        passed,
        evidence,
    )


def event_normalized_allele(
    event: dict,
    observations_by_event: dict,
) -> tuple:

    observations = (
        observations_by_event[
            event["event_id"]
        ]
    )

    alleles = {
        (
            event["assembly"],
            event["contig"],
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
        for row
        in observations
    }

    require(
        len(alleles) == 1,
        (
            "event does not resolve to "
            "one normalized allele: "
            f"{event['event_id']}"
        ),
    )

    return next(
        iter(
            alleles
        )
    )


def candidate_record_id(
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


def main() -> int:

    print("=" * 78)

    print(
        "PROJECT 003 — PHASE 1B "
        "FROZEN 15-CRITERION GATE"
    )

    print("=" * 78)

    PHASE1B.mkdir(
        parents=True,
        exist_ok=True,
    )


    # --------------------------------------------------------
    # Frozen protocol itself.
    # --------------------------------------------------------

    protocol_sha = sha256_file(
        PROTOCOL_PATH
    )

    require(
        protocol_sha
        == EXPECTED[
            "protocol_sha256"
        ],
        "frozen Phase 1B protocol changed",
    )

    require(
        sha256_file(
            FREEZE_MANIFEST_PATH
        )
        == EXPECTED[
            "freeze_manifest_sha256"
        ],
        "Phase 1B freeze manifest changed",
    )

    protocol_text = (
        PROTOCOL_PATH.read_text(
            encoding="utf-8"
        )
    )

    locked_criteria = (
        parse_locked_criteria(
            protocol_text
        )
    )

    print(
        "PASS  frozen protocol / "
        "15 criteria loaded"
    )


    # --------------------------------------------------------
    # Core artifacts.
    # --------------------------------------------------------

    candidates = read_tsv(
        CANDIDATES_PATH
    )

    classifications = read_tsv(
        CLASSIFICATION_PATH
    )

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

    experiments = read_tsv(
        EXPERIMENTS_PATH
    )

    benchmark_runs = read_tsv(
        RUNS_PATH
    )


    event_index = {
        row["event_id"]:
            row
        for row
        in events
    }

    variant_index = {
        row["variant_id"]:
            row
        for row
        in variants
    }

    run_index = {
        row["benchmark_run_id"]:
            row
        for row
        in benchmark_runs
    }

    experiment_index = {
        row["experiment_id"]:
            row
        for row
        in experiments
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
    # Criterion 1
    # --------------------------------------------------------

    criterion_1 = (
        sha256_file(
            PHASE1A_ARCHIVE
        )
        ==
        EXPECTED[
            "phase1a_archive_sha256"
        ]
    )

    evidence_1 = {
        "expected_sha256":
            EXPECTED[
                "phase1a_archive_sha256"
            ],

        "observed_sha256":
            sha256_file(
                PHASE1A_ARCHIVE
            ),
    }


    # --------------------------------------------------------
    # Criterion 2 + strongest available mutation check.
    # --------------------------------------------------------

    (
        all_phase1a_checksums_pass,
        checksum_evidence,
    ) = verify_all_phase1a_checksums()

    criterion_2 = (
        all_phase1a_checksums_pass
    )


    # --------------------------------------------------------
    # Criterion 3
    # --------------------------------------------------------

    criterion_3 = (
        len(candidates)
        ==
        EXPECTED[
            "candidate_count"
        ]
        and
        sha256_file(
            CANDIDATES_PATH
        )
        ==
        EXPECTED[
            "candidate_sha256"
        ]
    )

    evidence_3 = {
        "expected_candidates":
            EXPECTED[
                "candidate_count"
            ],

        "observed_candidates":
            len(candidates),

        "candidate_sha256":
            sha256_file(
                CANDIDATES_PATH
            ),
    }


    # --------------------------------------------------------
    # Criterion 4
    #
    # All 35 packaged Phase 1A artifacts remain byte-identical
    # to their final Phase 1A detached checksums.
    # --------------------------------------------------------

    criterion_4 = (
        all_phase1a_checksums_pass
    )

    evidence_4 = {
        "phase1a_detached_checksum_verification":
            checksum_evidence,

        "scientific_records_modified":
            False
            if all_phase1a_checksums_pass
            else "UNKNOWN_OR_CHANGED",
    }


    # --------------------------------------------------------
    # Criterion 5
    #
    # Candidate numbers must account for every frozen input
    # candidate exactly once.
    # --------------------------------------------------------

    classification_numbers = [
        int(
            row[
                "candidate_number"
            ]
        )
        for row
        in classifications
    ]

    criterion_5 = (
        len(
            classifications
        )
        ==
        EXPECTED[
            "candidate_count"
        ]
        and
        classification_numbers
        ==
        list(
            range(
                1,
                EXPECTED[
                    "candidate_count"
                ]
                + 1,
            )
        )
    )

    evidence_5 = {
        "input_candidates":
            len(candidates),

        "classified_candidates":
            len(classifications),

        "candidate_numbering_complete":
            classification_numbers
            ==
            list(
                range(
                    1,
                    EXPECTED[
                        "candidate_count"
                    ]
                    + 1,
                )
            ),
    }


    # --------------------------------------------------------
    # Criterion 6
    #
    # Recompute each content-derived VARIANT identifier.
    # --------------------------------------------------------

    deterministic_variant_failures = []

    for row in variants:

        recomputed = variant_id(
            {
                "assembly":
                    row["assembly"],

                "contig":
                    row["contig"],

                "start":
                    row[
                        "normalized_start_0based"
                    ],

                "end":
                    row[
                        "normalized_end_0based"
                    ],

                "ref":
                    row[
                        "normalized_ref"
                    ],

                "alt":
                    row[
                        "normalized_alt"
                    ],
            }
        )

        if (
            recomputed
            != row[
                "variant_id"
            ]
        ):
            deterministic_variant_failures.append(
                row[
                    "variant_id"
                ]
            )

    criterion_6 = (
        len(variants)
        ==
        EXPECTED[
            "variant_count"
        ]
        and
        not deterministic_variant_failures
    )

    evidence_6 = {
        "variant_count":
            len(variants),

        "deterministic_id_failures":
            len(
                deterministic_variant_failures
            ),
    }


    # --------------------------------------------------------
    # Criterion 7
    #
    # Every exact link must have equality across all six
    # frozen biological identity fields.
    # --------------------------------------------------------

    exact_identity_failures = []

    for link in links:

        event = event_index.get(
            link[
                "event_id"
            ]
        )

        variant = variant_index.get(
            link[
                "variant_id"
            ]
        )

        if (
            event is None
            or variant is None
        ):
            exact_identity_failures.append(
                link[
                    "event_variant_link_id"
                ]
            )
            continue

        event_allele = (
            event_normalized_allele(
                event,
                observations_by_event,
            )
        )

        variant_allele = (
            variant["assembly"],
            variant["contig"],
            variant[
                "normalized_start_0based"
            ],
            variant[
                "normalized_end_0based"
            ],
            variant[
                "normalized_ref"
            ],
            variant[
                "normalized_alt"
            ],
        )

        if (
            link[
                "identity_status"
            ]
            != EXACT_NORMALIZED_ALLELE
            or
            event_allele
            != variant_allele
        ):
            exact_identity_failures.append(
                link[
                    "event_variant_link_id"
                ]
            )

    criterion_7 = (
        len(links)
        ==
        EXPECTED[
            "link_count"
        ]
        and
        not exact_identity_failures
    )

    evidence_7 = {
        "links_checked":
            len(links),

        "exact_identity_failures":
            len(
                exact_identity_failures
            ),

        "fields":
            [
                "assembly",
                "contig",
                "normalized_start_0based",
                "normalized_end_0based",
                "normalized_ref",
                "normalized_alt",
            ],
    }


    # --------------------------------------------------------
    # Criterion 8
    #
    # Assembly is integral to variant identity.
    # Current real scope must remain GRCh38; frozen synthetic
    # case11 separately tests GRCh38 vs GRCh37.
    # --------------------------------------------------------

    assembly_set = {
        row["assembly"]
        for row
        in variants
    }

    criterion_8 = (
        assembly_set
        == {"GRCh38"}
    )

    evidence_8 = {
        "real_variant_assemblies":
            sorted(
                assembly_set
            ),

        "identity_payload_includes_assembly":
            True,
    }


    # --------------------------------------------------------
    # Criterion 9
    #
    # Reference provenance consistency. The compact Phase 1A
    # bundle does not contain the full GRCh38 FASTA, so this
    # gate checks the frozen requirement as written:
    # each Phase 1B REF assertion must remain attached to the
    # same locked Phase 1A reference provenance used by its
    # source event and benchmark run.
    # --------------------------------------------------------

    reference_failures = []

    for link in links:

        event = event_index[
            link["event_id"]
        ]

        run = run_index[
            link[
                "benchmark_run_id"
            ]
        ]

        variant = variant_index[
            link[
                "variant_id"
            ]
        ]

        if not (
            variant[
                "reference_artifact_id"
            ]
            ==
            event[
                "reference_artifact_id"
            ]
            ==
            run[
                "reference_artifact_id"
            ]
        ):
            reference_failures.append(
                link[
                    "event_variant_link_id"
                ]
            )

    criterion_9 = (
        not reference_failures
    )

    evidence_9 = {
        "links_checked":
            len(links),

        "reference_provenance_failures":
            len(
                reference_failures
            ),

        "reference_sequence_recomputed_in_phase1b":
            False,

        "reason":
            (
                "Phase 1B uses the validated "
                "Phase 1A normalized allele fields "
                "and locked reference provenance."
            ),
    }


    # --------------------------------------------------------
    # Criterion 10
    #
    # Evaluate frozen synthetic expectations directly.
    # --------------------------------------------------------

    require(
        sha256_file(
            SYNTHETIC_CASES_PATH
        )
        ==
        EXPECTED[
            "synthetic_cases_sha256"
        ],
        "frozen synthetic specification changed",
    )

    synthetic_cases = read_tsv(
        SYNTHETIC_CASES_PATH
    )

    synthetic_failures = []

    synthetic_observed = {}


    for row in synthetic_cases:

        allele_a = {
            "assembly":
                row[
                    "assembly_a"
                ],

            "contig":
                row[
                    "contig_a"
                ],

            "start":
                int(
                    row[
                        "start_a"
                    ]
                ),

            "end":
                int(
                    row[
                        "end_a"
                    ]
                ),

            "ref":
                row[
                    "ref_a"
                ],

            "alt":
                row[
                    "alt_a"
                ],
        }

        allele_b = {
            "assembly":
                row[
                    "assembly_b"
                ],

            "contig":
                row[
                    "contig_b"
                ],

            "start":
                int(
                    row[
                        "start_b"
                    ]
                ),

            "end":
                int(
                    row[
                        "end_b"
                    ]
                ),

            "ref":
                row[
                    "ref_b"
                ],

            "alt":
                row[
                    "alt_b"
                ],
        }

        observed = classify_identity(
            allele_a,
            allele_b,
        )

        synthetic_observed[
            row["case_id"]
        ] = observed

        if (
            observed
            != row[
                "expected_status"
            ]
        ):
            synthetic_failures.append(
                {
                    "case_id":
                        row[
                            "case_id"
                        ],

                    "expected":
                        row[
                            "expected_status"
                        ],

                    "observed":
                        observed,
                }
            )

    criterion_10 = (
        len(
            synthetic_cases
        )
        == 12
        and
        not synthetic_failures
    )

    evidence_10 = {
        "synthetic_cases":
            len(
                synthetic_cases
            ),

        "failures":
            synthetic_failures,
    }


    # --------------------------------------------------------
    # Criterion 11
    #
    # Ambiguous representation-equivalence cases must remain
    # UNRESOLVED; real v1 must never emit representation-
    # equivalence support.
    # --------------------------------------------------------

    ambiguous_case_ids = {
        "case05",
        "case07",
        "case08",
        "case12",
    }

    ambiguous_ok = all(
        synthetic_observed.get(
            case_id
        )
        == UNRESOLVED
        for case_id
        in ambiguous_case_ids
    )

    real_representation_equivalence = [
        row
        for row
        in classifications
        if (
            row[
                "phase1b_identity_status"
            ]
            ==
            REPRESENTATION_EQUIVALENCE_SUPPORTED
        )
    ]

    criterion_11 = (
        ambiguous_ok
        and
        not real_representation_equivalence
    )

    evidence_11 = {
        "ambiguous_cases":
            sorted(
                ambiguous_case_ids
            ),

        "all_ambiguous_cases_unresolved":
            ambiguous_ok,

        "real_representation_equivalence_assertions":
            len(
                real_representation_equivalence
            ),
    }


    # --------------------------------------------------------
    # Criterion 12
    #
    # Complete EVENT_VARIANT_LINK provenance.
    # --------------------------------------------------------

    candidate_by_number = {
        i:
            row
        for i, row
        in enumerate(
            candidates,
            start=1,
        )
    }

    provenance_failures = []

    for link in links:

        try:

            provenance = json.loads(
                link[
                    "provenance"
                ]
            )

            evidence = json.loads(
                link[
                    "evidence"
                ]
            )

        except Exception:

            provenance_failures.append(
                link[
                    "event_variant_link_id"
                ]
            )

            continue


        candidate_number = int(
            link[
                "candidate_number"
            ]
        )

        candidate = (
            candidate_by_number.get(
                candidate_number
            )
        )

        if candidate is None:

            provenance_failures.append(
                link[
                    "event_variant_link_id"
                ]
            )

            continue


        expected_candidate_id = (
            candidate_record_id(
                candidate
            )
        )


        required_provenance = (
            provenance.get(
                "phase1a_archive_sha256"
            )
            ==
            EXPECTED[
                "phase1a_archive_sha256"
            ]
            and
            provenance.get(
                "phase1a_candidate_input_sha256"
            )
            ==
            EXPECTED[
                "candidate_sha256"
            ]
            and
            provenance.get(
                "source_event_id"
            )
            ==
            link[
                "event_id"
            ]
            and
            provenance.get(
                "source_benchmark_run_id"
            )
            ==
            link[
                "benchmark_run_id"
            ]
            and
            link[
                "identity_method"
            ]
            ==
            "PHASE1B_EXACT_NORMALIZED_ALLELE_V1"
            and
            link[
                "identity_method_version"
            ]
            ==
            "1.0.0"
            and
            link[
                "candidate_id"
            ]
            ==
            expected_candidate_id
            and
            evidence.get(
                "candidate_number"
            )
            ==
            candidate_number
            and
            evidence.get(
                "candidate_id"
            )
            ==
            expected_candidate_id
        )


        if not required_provenance:

            provenance_failures.append(
                link[
                    "event_variant_link_id"
                ]
            )


    criterion_12 = (
        len(links)
        ==
        EXPECTED[
            "link_count"
        ]
        and
        not provenance_failures
    )

    evidence_12 = {
        "links_checked":
            len(links),

        "provenance_failures":
            len(
                provenance_failures
            ),
    }


    # --------------------------------------------------------
    # Criterion 13
    #
    # Re-run the independent byte-identical rebuild.
    # --------------------------------------------------------

    repro_script = (
        PROJECT_ROOT
        / "scripts/phase1b/verify_reproducibility.py"
    )

    repro_env = os.environ.copy()

    repro_env[
        "PYTHONPATH"
    ] = str(
        PROJECT_ROOT
        / "src"
    )


    repro = subprocess.run(
        [
            sys.executable,
            str(
                repro_script
            ),
        ],
        cwd=str(
            PROJECT_ROOT
        ),
        env=repro_env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


    criterion_13 = (
        repro.returncode == 0
        and
        "PHASE1B_DETERMINISTIC_REPRODUCIBILITY_PASS"
        in repro.stdout
    )

    evidence_13 = {
        "returncode":
            repro.returncode,

        "pass_marker_present":
            (
                "PHASE1B_DETERMINISTIC_REPRODUCIBILITY_PASS"
                in repro.stdout
            ),
    }


    # --------------------------------------------------------
    # Criterion 14
    #
    # Execute the actual product SQL for all variants.
    # --------------------------------------------------------

    query_sql = (
        QUERY_SQL_PATH.read_text(
            encoding="utf-8"
        )
    )


    con = duckdb.connect(
        ":memory:"
    )


    con.execute(
        """
        CREATE TABLE variants AS
        SELECT *
        FROM read_parquet(?)
        """,
        [
            str(
                VARIANTS_PATH
            )
        ],
    )


    con.execute(
        """
        CREATE TABLE event_variant_links AS
        SELECT *
        FROM read_parquet(?)
        """,
        [
            str(
                LINKS_PATH
            )
        ],
    )


    con.execute(
        """
        CREATE TABLE phase1a_events AS
        SELECT *
        FROM read_parquet(?)
        """,
        [
            str(
                EVENTS_PATH
            )
        ],
    )


    con.execute(
        """
        CREATE TABLE phase1a_observations AS
        SELECT *
        FROM read_parquet(?)
        """,
        [
            str(
                OBSERVATIONS_PATH
            )
        ],
    )


    con.execute(
        """
        CREATE TABLE benchmark_runs AS
        SELECT *
        FROM read_csv(
            ?,
            delim = '\t',
            header = true,
            all_varchar = true
        )
        """,
        [
            str(
                RUNS_PATH
            )
        ],
    )


    con.execute(
        """
        CREATE TABLE experiments AS
        SELECT *
        FROM read_csv(
            ?,
            delim = '\t',
            header = true,
            all_varchar = true
        )
        """,
        [
            str(
                EXPERIMENTS_PATH
            )
        ],
    )


    query_topology = (
        con.execute(
            """
            SELECT
                v.variant_id,
                count(
                    DISTINCT evl.event_id
                ) AS event_count,
                count(
                    DISTINCT evl.benchmark_run_id
                ) AS run_count,
                count(
                    DISTINCT br.experiment_id
                ) AS experiment_count,
                count(
                    DISTINCT ex.technology
                ) AS technology_count
            FROM variants v
            JOIN event_variant_links evl
              ON evl.variant_id = v.variant_id
            JOIN benchmark_runs br
              ON br.benchmark_run_id =
                 evl.benchmark_run_id
            JOIN experiments ex
              ON ex.experiment_id =
                 br.experiment_id
            GROUP BY v.variant_id
            """
        )
        .fetchall()
    )


    all_variants_two_contexts = (
        len(
            query_topology
        )
        ==
        EXPECTED[
            "variant_count"
        ]
        and
        all(
            (
                event_count == 2
                and
                run_count == 2
                and
                experiment_count == 2
                and
                technology_count == 2
            )
            for (
                _variant_id,
                event_count,
                run_count,
                experiment_count,
                technology_count,
            )
            in query_topology
        )
    )


    example_variant = min(
        variant_index
    )

    product_relation = con.execute(
        query_sql,
        [
            example_variant
        ],
    )

    product_columns = [
        description[0]
        for description
        in product_relation.description
    ]

    product_rows = (
        product_relation.fetchall()
    )

    con.close()


    required_query_columns = {
        "variant_id",
        "event_variant_link_id",
        "event_id",
        "benchmark_run_id",
        "experiment_id",
        "technology",
        "observation_id",
        "side",
        "raw_decision",
        "raw_match_kind",
        "phase1b_identity_provenance",
    }


    criterion_14 = (
        all_variants_two_contexts
        and
        bool(
            product_rows
        )
        and
        required_query_columns
        <= set(
            product_columns
        )
    )

    evidence_14 = {
        "variants_with_queryable_context":
            len(
                query_topology
            ),

        "all_variants_preserve_two_runs":
            all_variants_two_contexts,

        "example_variant":
            example_variant,

        "example_query_rows":
            len(
                product_rows
            ),

        "required_columns_present":
            required_query_columns
            <= set(
                product_columns
            ),
    }


    # --------------------------------------------------------
    # Criterion 15
    #
    # No reliability/confidence/trust/ranking/consensus output.
    # --------------------------------------------------------

    entity_fields = (
        set(
            variants[0].keys()
        )
        |
        set(
            links[0].keys()
        )
        |
        set(
            classifications[0].keys()
        )
        |
        set(
            product_columns
        )
    )


    forbidden_present = (
        FORBIDDEN_PRODUCT_FIELDS
        & entity_fields
    )


    criterion_15 = (
        not forbidden_present
    )

    evidence_15 = {
        "forbidden_fields_present":
            sorted(
                forbidden_present
            ),

        "reliability_score_generated":
            False,

        "confidence_score_generated":
            False,

        "forced_consensus_generated":
            False,

        "technology_ranking_generated":
            False,
    }


    # --------------------------------------------------------
    # Collect all results.
    # --------------------------------------------------------

    results = {
        1:
            criterion_1,

        2:
            criterion_2,

        3:
            criterion_3,

        4:
            criterion_4,

        5:
            criterion_5,

        6:
            criterion_6,

        7:
            criterion_7,

        8:
            criterion_8,

        9:
            criterion_9,

        10:
            criterion_10,

        11:
            criterion_11,

        12:
            criterion_12,

        13:
            criterion_13,

        14:
            criterion_14,

        15:
            criterion_15,
    }


    evidence = {
        1:
            evidence_1,

        2:
            checksum_evidence,

        3:
            evidence_3,

        4:
            evidence_4,

        5:
            evidence_5,

        6:
            evidence_6,

        7:
            evidence_7,

        8:
            evidence_8,

        9:
            evidence_9,

        10:
            evidence_10,

        11:
            evidence_11,

        12:
            evidence_12,

        13:
            evidence_13,

        14:
            evidence_14,

        15:
            evidence_15,
    }


    failed_criteria = [
        i
        for i in range(
            1,
            16,
        )
        if not results[i]
    ]


    # --------------------------------------------------------
    # Frozen outcome-gate interpretation.
    # --------------------------------------------------------

    if not failed_criteria:

        verdict = "PASS"

    elif (
        set(
            failed_criteria
        )
        &
        CRITICAL_STOP_CRITERIA
    ):

        verdict = "STOP"

    else:

        verdict = "MODIFY"


    # --------------------------------------------------------
    # Write validation TSV.
    # --------------------------------------------------------

    validation_rows = []

    for i in range(
        1,
        16,
    ):

        validation_rows.append(
            {
                "criterion_id":
                    i,

                "description":
                    locked_criteria[i],

                "status":
                    (
                        "PASS"
                        if results[i]
                        else "FAIL"
                    ),

                "evidence":
                    json.dumps(
                        evidence[i],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
            }
        )


    with VALIDATION_TSV.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "criterion_id",
                "description",
                "status",
                "evidence",
            ],
            delimiter="\t",
            lineterminator="\n",
        )

        writer.writeheader()

        writer.writerows(
            validation_rows
        )


    # --------------------------------------------------------
    # JSON result.
    # --------------------------------------------------------

    result_document = {
        "project":
            "Project 003",

        "phase":
            "1B",

        "protocol_sha256":
            protocol_sha,

        "phase1a_archive_sha256":
            EXPECTED[
                "phase1a_archive_sha256"
            ],

        "candidate_input_sha256":
            EXPECTED[
                "candidate_sha256"
            ],

        "criteria_total":
            15,

        "criteria_passed":
            sum(
                1
                for value
                in results.values()
                if value
            ),

        "criteria_failed":
            len(
                failed_criteria
            ),

        "failed_criteria":
            failed_criteria,

        "verdict":
            verdict,

        "variant_count":
            len(
                variants
            ),

        "event_variant_link_count":
            len(
                links
            ),

        "candidate_count":
            len(
                candidates
            ),

        "representation_equivalence_evaluated":
            False,

        "reliability_score_generated":
            False,

        "phase1a_entities_modified":
            False
            if criterion_4
            else "UNKNOWN_OR_CHANGED",
    }


    VALIDATION_JSON.write_text(
        json.dumps(
            result_document,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


    # --------------------------------------------------------
    # Human-readable gate report.
    # --------------------------------------------------------

    lines = [
        "# Project 003 — Phase 1B Gate Report",
        "",
        f"Verdict: **{verdict}**",
        "",
        (
            f"Frozen criteria: "
            f"{result_document['criteria_passed']}/15 PASS"
        ),
        "",
        "## Scope",
        "",
        (
            "- Cross-run biological identity layer for the "
            "frozen Phase 1A candidate set."
        ),
        (
            f"- Candidates: {len(candidates):,}"
        ),
        (
            f"- Materialized VARIANT records: "
            f"{len(variants):,}"
        ),
        (
            f"- EVENT_VARIANT_LINK records: "
            f"{len(links):,}"
        ),
        (
            "- Representation-equivalence inference: "
            "not enabled in v1."
        ),
        (
            "- Reliability/confidence/trust scoring: "
            "not generated."
        ),
        "",
        "## Locked validation",
        "",
    ]


    for i in range(
        1,
        16,
    ):

        lines.append(
            (
                f"{i}. "
                f"{'PASS' if results[i] else 'FAIL'} — "
                f"{locked_criteria[i]}"
            )
        )


    lines.extend(
        [
            "",
            "## Scientific interpretation",
            "",
            (
                "Phase 1B preserves Phase 1A run-scoped "
                "events and observations while adding a "
                "separate biological VARIANT identity layer."
            ),
            (
                "Exact normalized allele identity is "
                "deterministic and provenance-backed."
            ),
            (
                "No representation-equivalence claim is "
                "made where deterministic v1 rules do not "
                "support one."
            ),
            (
                "Variant identity does not imply agreement "
                "between benchmark observations or "
                "sequencing technologies."
            ),
            "",
        ]
    )


    REPORT_PATH.write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )


    # --------------------------------------------------------
    # Terminal report.
    # --------------------------------------------------------

    print()

    print(
        "Frozen validation results:"
    )

    print()


    for i in range(
        1,
        16,
    ):

        print(
            f"{i:02d}",
            (
                "PASS"
                if results[i]
                else "FAIL"
            ),
            "-",
            locked_criteria[i],
        )


    pass_count = sum(
        1
        for value
        in results.values()
        if value
    )

    fail_count = (
        15
        - pass_count
    )


    print()

    print(
        "PASS:",
        pass_count,
    )

    print(
        "FAIL:",
        fail_count,
    )

    print()

    print(
        "PHASE1B_VERDICT:",
        verdict,
    )

    print()

    print(
        "validation TSV SHA-256:",
        sha256_file(
            VALIDATION_TSV
        ),
    )

    print(
        "validation JSON SHA-256:",
        sha256_file(
            VALIDATION_JSON
        ),
    )

    print(
        "gate report SHA-256:",
        sha256_file(
            REPORT_PATH
        ),
    )

    print()


    if verdict == "PASS":

        print(
            "PHASE1B_GATE_PASS"
        )

    elif verdict == "MODIFY":

        print(
            "PHASE1B_GATE_MODIFY"
        )

    else:

        print(
            "PHASE1B_GATE_STOP"
        )


    print("=" * 78)

    return (
        0
        if verdict == "PASS"
        else 1
    )


if __name__ == "__main__":

    try:

        sys.exit(
            main()
        )

    except Exception as exc:

        print()

        print(
            "PHASE1B_GATE_EVALUATION_ERROR"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(2)
