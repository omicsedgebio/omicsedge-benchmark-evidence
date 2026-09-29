#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

OUTDIR = (
    ROOT
    / "data/phase2/stratifications/v3.6/metadata"
)

MANIFEST_PATH = (
    ROOT
    / "data/phase2/stratification_metadata_manifest.tsv"
)

LOCK_PATH = (
    ROOT
    / "data/phase2/stratification_metadata.lock"
)

SUMMARY_PATH = (
    ROOT
    / "results/phase2/stratification_metadata_summary.json"
)


EXPECTED_PHASE2_PROTOCOL_SHA256 = (
    "6234485e8916fd30a335c761a62668b617cb148b5b5a1753d12fd7765fa1633f"
)

EXPECTED_ADMITTED_SOURCES_SHA256 = (
    "55ebf63901ac0c118cb5ec687b49cc81cf680bb9357246ba2f6138b27a29641f"
)

STRATIFICATION_VERSION = "v3.6"

BASE = (
    "https://ftp-trace.ncbi.nlm.nih.gov/"
    "ReferenceSamples/giab/release/"
    "genome-stratifications/v3.6"
)


FILES = [
    {
        "artifact_id":
            "giab-strat-v3.6-readme",

        "relative_path":
            "README.md",

        "url":
            f"{BASE}/README.md",
    },
    {
        "artifact_id":
            "giab-strat-v3.6-grch38-readme",

        "relative_path":
            "GRCh38-README.md",

        "url":
            (
                f"{BASE}/GRCh38@all/"
                "GRCh38-README.md"
            ),
    },
    {
        "artifact_id":
            "giab-strat-v3.6-grch38-tsv",

        "relative_path":
            "GRCh38-all-stratifications.tsv",

        "url":
            (
                f"{BASE}/GRCh38@all/"
                "GRCh38-all-stratifications.tsv"
            ),
    },
    {
        "artifact_id":
            "giab-strat-v3.6-grch38-md5",

        "relative_path":
            "GRCh38-genome-stratifications-md5s.txt",

        "url":
            (
                f"{BASE}/GRCh38@all/"
                "GRCh38-genome-stratifications-md5s.txt"
            ),
    },
    {
        "artifact_id":
            "giab-strat-v3.6-global-md5",

        "relative_path":
            "genome-stratifications-md5s.txt",

        "url":
            (
                f"{BASE}/"
                "genome-stratifications-md5s.txt"
            ),
    },
]


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


def download(
    url: str,
    output: Path,
) -> None:

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
            "120",
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


def main() -> int:

    print("=" * 78)
    print(
        "PROJECT 003 — PHASE 2B "
        "STRATIFICATION METADATA FREEZE"
    )
    print("=" * 78)

    protocol_path = (
        ROOT
        / "docs/phase2/phase2_protocol.md"
    )

    admitted_sources = (
        ROOT
        / "data/phase2/admitted_sources.tsv"
    )

    require(
        sha256_file(
            protocol_path
        )
        == EXPECTED_PHASE2_PROTOCOL_SHA256,
        "Phase 2 protocol changed",
    )

    require(
        sha256_file(
            admitted_sources
        )
        == EXPECTED_ADMITTED_SOURCES_SHA256,
        "admitted source manifest changed",
    )

    print(
        "PASS  frozen Phase 2 protocol SHA-256"
    )

    print(
        "PASS  frozen admitted-source SHA-256"
    )

    OUTDIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    # --------------------------------------------------------
    # Download small official GIAB metadata files.
    # --------------------------------------------------------

    records = []

    for spec in FILES:

        path = (
            OUTDIR
            / spec["relative_path"]
        )

        print(
            "Downloading:",
            spec["relative_path"],
        )

        download(
            spec["url"],
            path,
        )

        require(
            path.is_file(),
            (
                "download did not create file: "
                f"{path}"
            ),
        )

        require(
            path.stat().st_size > 0,
            (
                "downloaded file is empty: "
                f"{path}"
            ),
        )

        records.append(
            {
                "artifact_id":
                    spec["artifact_id"],

                "stratification_version":
                    STRATIFICATION_VERSION,

                "reference_assembly":
                    "GRCh38",

                "source":
                    "NIST/GIAB",

                "url":
                    spec["url"],

                "local_path":
                    str(
                        path.relative_to(
                            ROOT
                        )
                    ),

                "size_bytes":
                    path.stat().st_size,

                "sha256":
                    sha256_file(
                        path
                    ),
            }
        )


    print(
        "PASS  downloaded metadata files:",
        len(records),
    )


    # --------------------------------------------------------
    # Basic content validation.
    # --------------------------------------------------------

    readme = (
        OUTDIR
        / "README.md"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    grch38_readme = (
        OUTDIR
        / "GRCh38-README.md"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    strat_tsv = (
        OUTDIR
        / "GRCh38-all-stratifications.tsv"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    grch38_md5 = (
        OUTDIR
        / "GRCh38-genome-stratifications-md5s.txt"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    global_md5 = (
        OUTDIR
        / "genome-stratifications-md5s.txt"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )


    require(
        "strat" in readme.lower(),
        "top-level README does not look like GIAB stratification metadata",
    )

    require(
        "grch38" in grch38_readme.lower(),
        "GRCh38 README validation failed",
    )

    require(
        ".bed.gz" in strat_tsv,
        "GRCh38 stratification TSV contains no BED entries",
    )

    require(
        "LowComplexity" in strat_tsv,
        "LowComplexity category missing",
    )

    require(
        "Mappability" in strat_tsv,
        "Mappability category missing",
    )

    require(
        "Union" in strat_tsv,
        "Union category missing",
    )

    require(
        ".bed.gz" in grch38_md5,
        "GRCh38 MD5 manifest contains no BED files",
    )

    require(
        ".bed.gz" in global_md5,
        "global MD5 manifest contains no BED files",
    )

    print(
        "PASS  GIAB metadata content validation"
    )


    # --------------------------------------------------------
    # Record available stratification entries.
    # --------------------------------------------------------

    bed_lines = [
        line
        for line
        in strat_tsv.splitlines()
        if ".bed.gz" in line
    ]

    require(
        len(bed_lines) > 20,
        (
            "unexpectedly small GRCh38 "
            "stratification catalog"
        ),
    )

    print(
        "GRCh38 stratification BED entries:",
        len(bed_lines),
    )


    # --------------------------------------------------------
    # Write frozen metadata manifest.
    # --------------------------------------------------------

    fieldnames = [
        "artifact_id",
        "stratification_version",
        "reference_assembly",
        "source",
        "url",
        "local_path",
        "size_bytes",
        "sha256",
    ]


    with MANIFEST_PATH.open(
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
                records,
                key=lambda row:
                    row["artifact_id"],
            )
        )


    manifest_sha = sha256_file(
        MANIFEST_PATH
    )


    # --------------------------------------------------------
    # Freeze metadata selection.
    # --------------------------------------------------------

    LOCK_PATH.write_text(
        "\n".join(
            [
                "project=Project 003",
                "phase=2B",
                (
                    "phase2_protocol_sha256="
                    f"{EXPECTED_PHASE2_PROTOCOL_SHA256}"
                ),
                (
                    "admitted_sources_sha256="
                    f"{EXPECTED_ADMITTED_SOURCES_SHA256}"
                ),
                (
                    "giab_stratification_version="
                    f"{STRATIFICATION_VERSION}"
                ),
                "reference_assembly=GRCh38",
                (
                    "stratification_metadata_manifest_sha256="
                    f"{manifest_sha}"
                ),
                (
                    "benchmark_outcomes_consulted="
                    "False"
                ),
                (
                    "status="
                    "FROZEN_BEFORE_CONTEXT_INTERVAL_SELECTION"
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

        "giab_stratification_version":
            STRATIFICATION_VERSION,

        "reference_assembly":
            "GRCh38",

        "metadata_artifact_count":
            len(records),

        "grch38_stratification_bed_entries":
            len(bed_lines),

        "benchmark_outcomes_consulted":
            False,

        "manifest_sha256":
            manifest_sha,

        "lock_sha256":
            sha256_file(
                LOCK_PATH
            ),

        "artifacts":
            {
                row["artifact_id"]:
                    row["sha256"]
                for row
                in records
            },
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
        "stratification version:",
        STRATIFICATION_VERSION,
    )

    print(
        "metadata manifest SHA-256:",
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
        "PHASE2_STRATIFICATION_METADATA_FREEZE_PASS"
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
            "PHASE2_STRATIFICATION_METADATA_FREEZE_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
