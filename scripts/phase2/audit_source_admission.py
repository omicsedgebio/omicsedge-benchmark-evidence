#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

SOURCE_PATH = (
    ROOT
    / "data/phase2/source_candidates.tsv"
)

OUTPUT_PATH = (
    ROOT
    / "results/phase2/source_admission_audit.tsv"
)

SUMMARY_PATH = (
    ROOT
    / "results/phase2/source_admission_summary.txt"
)

EXPECTED_SOURCE_SHA256 = (
    "f0085da28d6e9089f6f74fb90f1acd9606dd3f6e3d8bd2c3741f0846081edc21"
)

EXPECTED_CANDIDATES = 4

SHA256_RE = re.compile(
    r"\b([0-9a-fA-F]{64})\b"
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


def run_curl(
    args: list[str],
) -> subprocess.CompletedProcess:

    return subprocess.run(
        [
            "curl",
            "--silent",
            "--show-error",
            "--location",
            "--max-redirs",
            "10",
            "--connect-timeout",
            "20",
            "--max-time",
            "60",
            *args,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def fetch_small_text(
    url: str,
) -> tuple[bool, str, str]:

    result = run_curl(
        [
            "--fail",
            url,
        ]
    )

    if result.returncode != 0:

        return (
            False,
            "",
            result.stderr.strip(),
        )

    text = result.stdout.strip()

    if len(text) > 10000:

        return (
            False,
            "",
            "response unexpectedly large",
        )

    return (
        True,
        text,
        "",
    )


def endpoint_exists(
    url: str,
) -> tuple[bool, str]:

    # First try a normal HEAD request.
    result = run_curl(
        [
            "--head",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            url,
        ]
    )

    code = result.stdout.strip()

    if (
        result.returncode == 0
        and code.startswith("2")
    ):
        return (
            True,
            code,
        )

    # Some public repositories reject HEAD while serving GET.
    # Request only the first byte as a fallback.
    result = run_curl(
        [
            "--range",
            "0-0",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            url,
        ]
    )

    code = result.stdout.strip()

    if (
        result.returncode == 0
        and code.startswith("2")
    ):
        return (
            True,
            code,
        )

    return (
        False,
        code or "CURL_ERROR",
    )


def main() -> int:

    print("=" * 78)
    print(
        "PROJECT 003 — PHASE 2A "
        "SOURCE ADMISSION PREFLIGHT"
    )
    print("=" * 78)

    require(
        SOURCE_PATH.is_file(),
        "source candidate manifest missing",
    )

    observed_source_sha = (
        sha256_file(
            SOURCE_PATH
        )
    )

    require(
        observed_source_sha
        == EXPECTED_SOURCE_SHA256,
        (
            "frozen source candidate manifest changed\n"
            f"expected: {EXPECTED_SOURCE_SHA256}\n"
            f"observed: {observed_source_sha}"
        ),
    )

    print(
        "PASS  frozen source candidate SHA-256"
    )


    with SOURCE_PATH.open(
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
        len(rows)
        == EXPECTED_CANDIDATES,
        (
            f"expected {EXPECTED_CANDIDATES} "
            f"candidates; observed {len(rows)}"
        ),
    )

    print(
        "PASS  candidate rows:",
        len(rows),
    )


    output_rows = []


    for row in rows:

        candidate_id = row[
            "candidate_id"
        ]

        print()
        print(
            "Checking:",
            candidate_id,
        )


        # ----------------------------------------------------
        # Selection-independence checks.
        # ----------------------------------------------------

        performance_independent = (
            row[
                "performance_consulted_for_selection"
            ]
            == "False"
        )

        assembly_ok = (
            row[
                "reference_assembly"
            ]
            == "GRCh38"
        )


        # ----------------------------------------------------
        # Retrieve tiny authoritative query SHA-256 record.
        # ----------------------------------------------------

        (
            checksum_reachable,
            checksum_text,
            checksum_error,
        ) = fetch_small_text(
            row[
                "query_sha256_url"
            ]
        )


        expected_query_sha256 = ""

        checksum_valid = False


        if checksum_reachable:

            match = SHA256_RE.search(
                checksum_text
            )

            if match:

                expected_query_sha256 = (
                    match.group(1).lower()
                )

                checksum_valid = True


        print(
            "  query checksum record:",
            (
                "PASS"
                if checksum_valid
                else "FAIL"
            ),
        )


        # ----------------------------------------------------
        # Endpoint existence checks.
        #
        # Large VCFs are not intentionally downloaded.
        # ----------------------------------------------------

        (
            query_exists,
            query_http,
        ) = endpoint_exists(
            row[
                "query_vcf_url"
            ]
        )

        print(
            "  query VCF endpoint:",
            (
                "PASS"
                if query_exists
                else "FAIL"
            ),
            f"({query_http})",
        )


        (
            truth_exists,
            truth_http,
        ) = endpoint_exists(
            row[
                "truth_vcf_url"
            ]
        )

        print(
            "  truth VCF endpoint:",
            (
                "PASS"
                if truth_exists
                else "FAIL"
            ),
            f"({truth_http})",
        )


        (
            bed_exists,
            bed_http,
        ) = endpoint_exists(
            row[
                "benchmark_bed_url"
            ]
        )

        print(
            "  benchmark BED endpoint:",
            (
                "PASS"
                if bed_exists
                else "FAIL"
            ),
            f"({bed_http})",
        )


        metadata_complete = all(
            bool(
                row[field].strip()
            )
            for field in (
                "sample_id",
                "technology",
                "platform",
                "coverage",
                "source_corpus",
                "source_submission_id",
                "pipeline_name",
                "query_vcf_url",
                "query_sha256_url",
                "truth_vcf_url",
                "benchmark_bed_url",
                "reference_assembly",
                "selection_basis",
            )
        )


        eligible = all(
            (
                performance_independent,
                assembly_ok,
                metadata_complete,
                checksum_valid,
                query_exists,
                truth_exists,
                bed_exists,
            )
        )


        admission_state = (
            "ELIGIBLE"
            if eligible
            else "UNRESOLVED"
        )


        unresolved_reasons = []

        if not performance_independent:
            unresolved_reasons.append(
                "PERFORMANCE_SELECTION_VIOLATION"
            )

        if not assembly_ok:
            unresolved_reasons.append(
                "NON_GRCH38"
            )

        if not metadata_complete:
            unresolved_reasons.append(
                "INCOMPLETE_METADATA"
            )

        if not checksum_valid:
            unresolved_reasons.append(
                "QUERY_SHA256_RECORD_UNRESOLVED"
            )

        if not query_exists:
            unresolved_reasons.append(
                "QUERY_VCF_ENDPOINT_UNRESOLVED"
            )

        if not truth_exists:
            unresolved_reasons.append(
                "TRUTH_VCF_ENDPOINT_UNRESOLVED"
            )

        if not bed_exists:
            unresolved_reasons.append(
                "BENCHMARK_BED_ENDPOINT_UNRESOLVED"
            )


        output_rows.append(
            {
                "candidate_id":
                    candidate_id,

                "sample_id":
                    row[
                        "sample_id"
                    ],

                "technology":
                    row[
                        "technology"
                    ],

                "source_submission_id":
                    row[
                        "source_submission_id"
                    ],

                "reference_assembly":
                    row[
                        "reference_assembly"
                    ],

                "performance_consulted_for_selection":
                    row[
                        "performance_consulted_for_selection"
                    ],

                "metadata_complete":
                    metadata_complete,

                "query_checksum_record_reachable":
                    checksum_reachable,

                "query_checksum_record_valid":
                    checksum_valid,

                "expected_query_sha256":
                    expected_query_sha256,

                "query_vcf_endpoint":
                    query_exists,

                "query_http":
                    query_http,

                "truth_vcf_endpoint":
                    truth_exists,

                "truth_http":
                    truth_http,

                "benchmark_bed_endpoint":
                    bed_exists,

                "benchmark_bed_http":
                    bed_http,

                "admission_state":
                    admission_state,

                "unresolved_reasons":
                    ";".join(
                        unresolved_reasons
                    ),

                "checksum_error":
                    checksum_error,
            }
        )


        print(
            "  admission:",
            admission_state,
        )


    # --------------------------------------------------------
    # Write deterministic audit.
    # --------------------------------------------------------

    fieldnames = [
        "candidate_id",
        "sample_id",
        "technology",
        "source_submission_id",
        "reference_assembly",
        "performance_consulted_for_selection",
        "metadata_complete",
        "query_checksum_record_reachable",
        "query_checksum_record_valid",
        "expected_query_sha256",
        "query_vcf_endpoint",
        "query_http",
        "truth_vcf_endpoint",
        "truth_http",
        "benchmark_bed_endpoint",
        "benchmark_bed_http",
        "admission_state",
        "unresolved_reasons",
        "checksum_error",
    ]


    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    with OUTPUT_PATH.open(
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
            output_rows
        )


    states = {}

    for row in output_rows:

        state = row[
            "admission_state"
        ]

        states[state] = (
            states.get(
                state,
                0,
            )
            + 1
        )


    eligible_samples = sorted(
        {
            row["sample_id"]
            for row
            in output_rows
            if row[
                "admission_state"
            ]
            == "ELIGIBLE"
        }
    )


    eligible_technologies = sorted(
        {
            row["technology"]
            for row
            in output_rows
            if row[
                "admission_state"
            ]
            == "ELIGIBLE"
        }
    )


    summary = [
        "PROJECT 003 — PHASE 2A SOURCE ADMISSION PREFLIGHT",
        "",
        (
            "source_candidates_sha256="
            f"{observed_source_sha}"
        ),
        (
            "source_candidates="
            f"{len(rows)}"
        ),
        (
            "eligible="
            f"{states.get('ELIGIBLE', 0)}"
        ),
        (
            "unresolved="
            f"{states.get('UNRESOLVED', 0)}"
        ),
        (
            "eligible_samples="
            + ",".join(
                eligible_samples
            )
        ),
        (
            "eligible_technologies="
            + ",".join(
                eligible_technologies
            )
        ),
        (
            "benchmark_performance_consulted=False"
        ),
    ]


    SUMMARY_PATH.write_text(
        "\n".join(
            summary
        )
        + "\n",
        encoding="utf-8",
    )


    print()
    print("=" * 78)

    print(
        "Admission state counts:"
    )

    for state in sorted(
        states
    ):

        print(
            f"  {state}: "
            f"{states[state]}"
        )


    print()

    print(
        "audit SHA-256:",
        sha256_file(
            OUTPUT_PATH
        ),
    )

    print(
        "summary SHA-256:",
        sha256_file(
            SUMMARY_PATH
        ),
    )

    print()


    if (
        states.get(
            "ELIGIBLE",
            0,
        )
        == EXPECTED_CANDIDATES
    ):

        print(
            "PHASE2_SOURCE_ADMISSION_PREFLIGHT_PASS"
        )

        return 0


    print(
        "PHASE2_SOURCE_ADMISSION_PREFLIGHT_UNRESOLVED"
    )

    return 1


if __name__ == "__main__":

    try:
        sys.exit(
            main()
        )

    except Exception as exc:

        print()

        print(
            "PHASE2_SOURCE_ADMISSION_PREFLIGHT_ERROR"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(2)
