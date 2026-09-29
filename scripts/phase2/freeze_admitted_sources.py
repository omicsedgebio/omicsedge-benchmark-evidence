#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SOURCE_CANDIDATES = (
    ROOT
    / "data/phase2/source_candidates.tsv"
)

ADMISSION_AUDIT = (
    ROOT
    / "results/phase2/source_admission_audit.tsv"
)

OUTPUT = (
    ROOT
    / "data/phase2/admitted_sources.tsv"
)

LOCK = (
    ROOT
    / "data/phase2/admitted_sources.lock"
)

SUMMARY = (
    ROOT
    / "results/phase2/admitted_sources_summary.json"
)


EXPECTED_SOURCE_CANDIDATES_SHA256 = (
    "f0085da28d6e9089f6f74fb90f1acd9606dd3f6e3d8bd2c3741f0846081edc21"
)

EXPECTED_ADMISSION_AUDIT_SHA256 = (
    "4a1c24236bb47261647196d656ab2c16e42385627d6b93a63291f18179cc5611"
)

EXPECTED_PHASE2_PROTOCOL_SHA256 = (
    "6234485e8916fd30a335c761a62668b617cb148b5b5a1753d12fd7765fa1633f"
)

EXPECTED_ROWS = 4

SHA256_RE = re.compile(
    r"^[0-9a-f]{64}$"
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


def main() -> int:

    print("=" * 78)

    print(
        "PROJECT 003 — PHASE 2A "
        "ADMITTED SOURCE FREEZE"
    )

    print("=" * 78)

    # --------------------------------------------------------
    # Verify frozen upstream artifacts.
    # --------------------------------------------------------

    require(
        sha256_file(
            SOURCE_CANDIDATES
        )
        == EXPECTED_SOURCE_CANDIDATES_SHA256,
        "source candidate manifest changed",
    )

    require(
        sha256_file(
            ADMISSION_AUDIT
        )
        == EXPECTED_ADMISSION_AUDIT_SHA256,
        "source admission audit changed",
    )

    print(
        "PASS  frozen source candidate SHA-256"
    )

    print(
        "PASS  frozen admission audit SHA-256"
    )


    candidates = read_tsv(
        SOURCE_CANDIDATES
    )

    audits = read_tsv(
        ADMISSION_AUDIT
    )


    require(
        len(candidates) == EXPECTED_ROWS,
        "unexpected source candidate count",
    )

    require(
        len(audits) == EXPECTED_ROWS,
        "unexpected admission audit count",
    )


    candidate_index = {
        row["candidate_id"]:
            row
        for row in candidates
    }

    audit_index = {
        row["candidate_id"]:
            row
        for row in audits
    }


    require(
        set(candidate_index)
        == set(audit_index),
        (
            "candidate IDs differ between "
            "candidate manifest and audit"
        ),
    )


    # --------------------------------------------------------
    # Freeze only fully ELIGIBLE records.
    # --------------------------------------------------------

    admitted = []


    for candidate_id in sorted(
        candidate_index
    ):

        source = candidate_index[
            candidate_id
        ]

        audit = audit_index[
            candidate_id
        ]


        require(
            audit[
                "admission_state"
            ]
            == "ELIGIBLE",
            (
                f"{candidate_id} is not ELIGIBLE"
            ),
        )


        require(
            audit[
                "query_checksum_record_valid"
            ]
            == "True",
            (
                f"{candidate_id} has no valid "
                "query checksum record"
            ),
        )


        expected_query_sha256 = (
            audit[
                "expected_query_sha256"
            ].lower()
        )


        require(
            bool(
                SHA256_RE.fullmatch(
                    expected_query_sha256
                )
            ),
            (
                f"{candidate_id} has invalid "
                "expected query SHA-256"
            ),
        )


        require(
            audit[
                "query_vcf_endpoint"
            ]
            == "True",
            (
                f"{candidate_id} query VCF "
                "endpoint unresolved"
            ),
        )


        require(
            audit[
                "truth_vcf_endpoint"
            ]
            == "True",
            (
                f"{candidate_id} truth VCF "
                "endpoint unresolved"
            ),
        )


        require(
            audit[
                "benchmark_bed_endpoint"
            ]
            == "True",
            (
                f"{candidate_id} benchmark BED "
                "endpoint unresolved"
            ),
        )


        require(
            source[
                "performance_consulted_for_selection"
            ]
            == "False",
            (
                f"{candidate_id} violates "
                "performance-independent selection"
            ),
        )


        admitted.append(
            {
                "candidate_id":
                    candidate_id,

                "sample_id":
                    source[
                        "sample_id"
                    ],

                "technology":
                    source[
                        "technology"
                    ],

                "platform":
                    source[
                        "platform"
                    ],

                "coverage":
                    source[
                        "coverage"
                    ],

                "source_corpus":
                    source[
                        "source_corpus"
                    ],

                "source_submission_id":
                    source[
                        "source_submission_id"
                    ],

                "pipeline_name":
                    source[
                        "pipeline_name"
                    ],

                "reference_assembly":
                    source[
                        "reference_assembly"
                    ],

                "query_vcf_url":
                    source[
                        "query_vcf_url"
                    ],

                "query_sha256_url":
                    source[
                        "query_sha256_url"
                    ],

                "expected_query_sha256":
                    expected_query_sha256,

                "truth_vcf_url":
                    source[
                        "truth_vcf_url"
                    ],

                "benchmark_bed_url":
                    source[
                        "benchmark_bed_url"
                    ],

                "selection_basis":
                    source[
                        "selection_basis"
                    ],

                "performance_consulted_for_selection":
                    False,

                "phase2a_admission_state":
                    "ELIGIBLE",
            }
        )


    require(
        len(admitted) == EXPECTED_ROWS,
        (
            "expected exactly four admitted "
            f"sources; observed {len(admitted)}"
        ),
    )


    require(
        {
            row["sample_id"]
            for row in admitted
        }
        == {
            "HG003",
            "HG004",
        },
        "unexpected admitted sample set",
    )


    require(
        {
            row["technology"]
            for row in admitted
        }
        == {
            "ILLUMINA",
            "ONT",
        },
        "unexpected admitted technology set",
    )


    # Exactly two technologies per sample.
    for sample in (
        "HG003",
        "HG004",
    ):

        technologies = {
            row["technology"]
            for row in admitted
            if row["sample_id"] == sample
        }

        require(
            technologies
            == {
                "ILLUMINA",
                "ONT",
            },
            (
                f"{sample} does not have both "
                "ILLUMINA and ONT"
            ),
        )


    # --------------------------------------------------------
    # Write authoritative admitted-source manifest.
    # --------------------------------------------------------

    fieldnames = [
        "candidate_id",
        "sample_id",
        "technology",
        "platform",
        "coverage",
        "source_corpus",
        "source_submission_id",
        "pipeline_name",
        "reference_assembly",
        "query_vcf_url",
        "query_sha256_url",
        "expected_query_sha256",
        "truth_vcf_url",
        "benchmark_bed_url",
        "selection_basis",
        "performance_consulted_for_selection",
        "phase2a_admission_state",
    ]


    with OUTPUT.open(
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
            admitted
        )


    admitted_sha = sha256_file(
        OUTPUT
    )


    # --------------------------------------------------------
    # Freeze manifest.
    # --------------------------------------------------------

    LOCK.write_text(
        "\n".join(
            [
                "project=Project 003",
                "phase=2A",
                (
                    "phase2_protocol_sha256="
                    f"{EXPECTED_PHASE2_PROTOCOL_SHA256}"
                ),
                (
                    "source_candidates_sha256="
                    f"{EXPECTED_SOURCE_CANDIDATES_SHA256}"
                ),
                (
                    "source_admission_audit_sha256="
                    f"{EXPECTED_ADMISSION_AUDIT_SHA256}"
                ),
                (
                    "admitted_sources_sha256="
                    f"{admitted_sha}"
                ),
                "admitted_sources=4",
                "samples=HG003,HG004",
                "technologies=ILLUMINA,ONT",
                (
                    "performance_consulted_for_selection="
                    "False"
                ),
                (
                    "status="
                    "FROZEN_BEFORE_LARGE_ARTIFACT_DOWNLOAD"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    summary = {
        "project":
            "Project 003",

        "phase":
            "2A",

        "status":
            "FROZEN_BEFORE_LARGE_ARTIFACT_DOWNLOAD",

        "admitted_sources":
            len(admitted),

        "samples":
            sorted(
                {
                    row["sample_id"]
                    for row in admitted
                }
            ),

        "technologies":
            sorted(
                {
                    row["technology"]
                    for row in admitted
                }
            ),

        "submission_families":
            sorted(
                {
                    row[
                        "source_submission_id"
                    ]
                    for row in admitted
                }
            ),

        "performance_consulted_for_selection":
            False,

        "expected_query_sha256": {
            row["candidate_id"]:
                row[
                    "expected_query_sha256"
                ]
            for row in admitted
        },

        "admitted_sources_sha256":
            admitted_sha,

        "lock_sha256":
            sha256_file(
                LOCK
            ),
    }


    SUMMARY.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


    print(
        "PASS  admitted sources:",
        len(admitted),
    )

    print(
        "PASS  samples: HG003, HG004"
    )

    print(
        "PASS  technologies: ILLUMINA, ONT"
    )

    print(
        "PASS  benchmark performance consulted: False"
    )

    print()

    print(
        "Frozen expected query SHA-256:"
    )


    for row in admitted:

        print(
            " ",
            row["candidate_id"],
            row["expected_query_sha256"],
        )


    print()

    print(
        "admitted sources SHA-256:",
        admitted_sha,
    )

    print(
        "lock SHA-256:",
        sha256_file(
            LOCK
        ),
    )

    print(
        "summary SHA-256:",
        sha256_file(
            SUMMARY
        ),
    )

    print()

    print(
        "PHASE2_ADMITTED_SOURCES_FREEZE_PASS"
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
            "PHASE2_ADMITTED_SOURCES_FREEZE_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
