#!/usr/bin/env python3

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

CONTEXT_MANIFEST = (
    ROOT
    / "data/phase2/context_beds.tsv"
)

OUTPUT_ROOT = (
    ROOT
    / "data/phase2/stratifications/v3.6/GRCh38"
)

OUTPUT_MANIFEST = (
    ROOT
    / "data/phase2/context_beds_downloaded.tsv"
)

SUMMARY_PATH = (
    ROOT
    / "results/phase2/context_beds_download_summary.json"
)

LOCK_PATH = (
    ROOT
    / "data/phase2/context_beds_download.lock"
)


EXPECTED_CONTEXT_MANIFEST_SHA256 = (
    "9e6158cfc60c44c0aa266d0a9729a0ed8ccd0122e1268a8f5b8172a8cf8b6446"
)

EXPECTED_CONTEXTS = 5


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def md5_file(path: Path) -> str:
    h = hashlib.md5()

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


def download(
    url: str,
    output: Path,
) -> None:

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--location",
            "--silent",
            "--show-error",
            "--connect-timeout",
            "20",
            "--max-time",
            "300",
            "--output",
            str(output),
            url,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    require(
        result.returncode == 0,
        (
            f"download failed:\n"
            f"{url}\n"
            f"{result.stderr.strip()}"
        ),
    )


def validate_bed_gz(
    path: Path,
) -> dict:

    line_count = 0
    interval_count = 0
    chromosomes = set()

    with gzip.open(
        path,
        "rt",
        encoding="utf-8",
        errors="replace",
    ) as handle:

        for raw in handle:

            line_count += 1

            line = raw.strip()

            if not line:
                continue

            if line.startswith(
                (
                    "#",
                    "track",
                    "browser",
                )
            ):
                continue

            parts = line.split(
                "\t"
            )

            require(
                len(parts) >= 3,
                (
                    "invalid BED row in "
                    f"{path}: {line[:200]}"
                ),
            )

            chrom = parts[0]

            try:
                start = int(
                    parts[1]
                )

                end = int(
                    parts[2]
                )

            except ValueError as exc:
                raise RuntimeError(
                    (
                        "non-integer BED coordinates "
                        f"in {path}: {line[:200]}"
                    )
                ) from exc

            require(
                start >= 0,
                (
                    "negative BED start in "
                    f"{path}: {line[:200]}"
                ),
            )

            require(
                end >= start,
                (
                    "BED end < start in "
                    f"{path}: {line[:200]}"
                ),
            )

            chromosomes.add(
                chrom
            )

            interval_count += 1

    require(
        interval_count > 0,
        (
            "BED contains no intervals: "
            f"{path}"
        ),
    )

    return {
        "line_count":
            line_count,

        "interval_count":
            interval_count,

        "chromosome_count":
            len(
                chromosomes
            ),

        "chromosomes":
            sorted(
                chromosomes
            ),
    }


def main() -> int:

    print("=" * 78)

    print(
        "PROJECT 003 — PHASE 2B "
        "CONTEXT BED DOWNLOAD + VERIFICATION"
    )

    print("=" * 78)

    # --------------------------------------------------------
    # Verify frozen context manifest.
    # --------------------------------------------------------

    observed_context_sha = (
        sha256_file(
            CONTEXT_MANIFEST
        )
    )

    require(
        observed_context_sha
        == EXPECTED_CONTEXT_MANIFEST_SHA256,
        (
            "frozen context manifest changed\n"
            f"expected: {EXPECTED_CONTEXT_MANIFEST_SHA256}\n"
            f"observed: {observed_context_sha}"
        ),
    )

    print(
        "PASS  frozen context manifest SHA-256"
    )


    with CONTEXT_MANIFEST.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:

        contexts = list(
            csv.DictReader(
                handle,
                delimiter="\t",
            )
        )


    require(
        len(contexts)
        == EXPECTED_CONTEXTS,
        (
            f"expected {EXPECTED_CONTEXTS} contexts; "
            f"observed {len(contexts)}"
        ),
    )

    print(
        "PASS  frozen contexts:",
        len(contexts),
    )


    # --------------------------------------------------------
    # Download exactly the five frozen BEDs.
    # --------------------------------------------------------

    output_rows = []


    for row in contexts:

        context_id = row[
            "context_id"
        ]

        relative_path = Path(
            row[
                "relative_path"
            ]
        )

        output_path = (
            OUTPUT_ROOT
            / relative_path
        )

        print()

        print(
            "Downloading:",
            context_id,
        )

        print(
            " ",
            row[
                "relative_path"
            ],
        )


        download(
            row[
                "url"
            ],
            output_path,
        )


        require(
            output_path.is_file(),
            (
                "downloaded BED missing: "
                f"{output_path}"
            ),
        )

        require(
            output_path.stat().st_size > 0,
            (
                "downloaded BED is empty: "
                f"{output_path}"
            ),
        )


        # ----------------------------------------------------
        # Official MD5 validation.
        # ----------------------------------------------------

        observed_md5 = (
            md5_file(
                output_path
            )
        )

        expected_md5 = (
            row[
                "official_md5"
            ].lower()
        )


        require(
            observed_md5
            == expected_md5,
            (
                f"{context_id} MD5 mismatch\n"
                f"expected: {expected_md5}\n"
                f"observed: {observed_md5}"
            ),
        )


        print(
            "  MD5: PASS"
        )


        # ----------------------------------------------------
        # Independent local SHA-256.
        # ----------------------------------------------------

        observed_sha256 = (
            sha256_file(
                output_path
            )
        )


        # ----------------------------------------------------
        # Validate compressed BED contents.
        # ----------------------------------------------------

        bed_stats = validate_bed_gz(
            output_path
        )


        print(
            "  intervals:",
            bed_stats[
                "interval_count"
            ],
        )

        print(
            "  chromosomes:",
            bed_stats[
                "chromosome_count"
            ],
        )


        output_rows.append(
            {
                "context_id":
                    context_id,

                "context_class":
                    row[
                        "context_class"
                    ],

                "stratification_version":
                    row[
                        "stratification_version"
                    ],

                "reference_assembly":
                    row[
                        "reference_assembly"
                    ],

                "relative_path":
                    row[
                        "relative_path"
                    ],

                "local_path":
                    str(
                        output_path.relative_to(
                            ROOT
                        )
                    ),

                "url":
                    row[
                        "url"
                    ],

                "official_md5":
                    expected_md5,

                "observed_md5":
                    observed_md5,

                "sha256":
                    observed_sha256,

                "size_bytes":
                    output_path.stat().st_size,

                "interval_count":
                    bed_stats[
                        "interval_count"
                    ],

                "chromosome_count":
                    bed_stats[
                        "chromosome_count"
                    ],

                "selection_basis":
                    row[
                        "selection_basis"
                    ],

                "benchmark_outcomes_consulted":
                    False,

                "download_state":
                    "VERIFIED",
            }
        )


    # --------------------------------------------------------
    # Ensure exactly five distinct contexts/files.
    # --------------------------------------------------------

    require(
        len(
            {
                row[
                    "context_id"
                ]
                for row
                in output_rows
            }
        )
        == EXPECTED_CONTEXTS,
        "context IDs are not unique",
    )


    require(
        len(
            {
                row[
                    "sha256"
                ]
                for row
                in output_rows
            }
        )
        == EXPECTED_CONTEXTS,
        (
            "unexpected duplicate BED content "
            "among selected contexts"
        ),
    )


    # --------------------------------------------------------
    # Write authoritative downloaded-BED manifest.
    # --------------------------------------------------------

    fieldnames = [
        "context_id",
        "context_class",
        "stratification_version",
        "reference_assembly",
        "relative_path",
        "local_path",
        "url",
        "official_md5",
        "observed_md5",
        "sha256",
        "size_bytes",
        "interval_count",
        "chromosome_count",
        "selection_basis",
        "benchmark_outcomes_consulted",
        "download_state",
    ]


    with OUTPUT_MANIFEST.open(
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
            sorted(
                output_rows,
                key=lambda row:
                    row[
                        "context_id"
                    ],
            )
        )


    manifest_sha = sha256_file(
        OUTPUT_MANIFEST
    )


    # --------------------------------------------------------
    # Freeze verified BED set.
    # --------------------------------------------------------

    LOCK_PATH.write_text(
        "\n".join(
            [
                "project=Project 003",
                "phase=2B",
                (
                    "context_beds_source_manifest_sha256="
                    f"{EXPECTED_CONTEXT_MANIFEST_SHA256}"
                ),
                (
                    "context_beds_downloaded_manifest_sha256="
                    f"{manifest_sha}"
                ),
                "context_count=5",
                "all_official_md5_checks=PASS",
                (
                    "benchmark_outcomes_consulted="
                    "False"
                ),
                (
                    "status="
                    "FROZEN_BEFORE_INTERVAL_SELECTION"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


    summary = {
        "project":
            "Project 003",

        "phase":
            "2B",

        "status":
            "FROZEN_BEFORE_INTERVAL_SELECTION",

        "context_count":
            len(
                output_rows
            ),

        "all_official_md5_checks_pass":
            True,

        "benchmark_outcomes_consulted":
            False,

        "downloaded_beds":
            {
                row["context_id"]: {
                    "sha256":
                        row[
                            "sha256"
                        ],

                    "official_md5":
                        row[
                            "official_md5"
                        ],

                    "size_bytes":
                        int(
                            row[
                                "size_bytes"
                            ]
                        ),

                    "interval_count":
                        int(
                            row[
                                "interval_count"
                            ]
                        ),

                    "chromosome_count":
                        int(
                            row[
                                "chromosome_count"
                            ]
                        ),
                }
                for row
                in output_rows
            },

        "manifest_sha256":
            manifest_sha,

        "lock_sha256":
            sha256_file(
                LOCK_PATH
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


    print()

    print(
        "verified BEDs:",
        len(
            output_rows
        ),
    )

    print(
        "download manifest SHA-256:",
        manifest_sha,
    )

    print(
        "lock SHA-256:",
        sha256_file(
            LOCK_PATH
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
        "PHASE2_CONTEXT_BED_DOWNLOAD_PASS"
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
            "PHASE2_CONTEXT_BED_DOWNLOAD_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
