#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

METADATA_DIR = (
    ROOT
    / "data/phase2/stratifications/v3.6/metadata"
)

CATALOG_PATH = (
    METADATA_DIR
    / "GRCh38-all-stratifications.tsv"
)

MD5_PATH = (
    METADATA_DIR
    / "GRCh38-genome-stratifications-md5s.txt"
)

OUTPUT_PATH = (
    ROOT
    / "data/phase2/context_beds.tsv"
)

LOCK_PATH = (
    ROOT
    / "data/phase2/context_beds.lock"
)

SUMMARY_PATH = (
    ROOT
    / "results/phase2/context_beds_summary.json"
)


EXPECTED_PROTOCOL_SHA256 = (
    "6234485e8916fd30a335c761a62668b617cb148b5b5a1753d12fd7765fa1633f"
)

EXPECTED_ADMITTED_SOURCES_SHA256 = (
    "55ebf63901ac0c118cb5ec687b49cc81cf680bb9357246ba2f6138b27a29641f"
)

EXPECTED_STRATIFICATION_METADATA_MANIFEST_SHA256 = (
    "effe001197dd7c3d62d0078beb946de4d6cc546cf06d9a3109e0dad732ccbfdc"
)

STRATIFICATION_VERSION = "v3.6"

BASE_URL = (
    "https://ftp-trace.ncbi.nlm.nih.gov/"
    "ReferenceSamples/giab/release/"
    "genome-stratifications/v3.6/GRCh38@all"
)


SELECTED_CONTEXTS = [
    {
        "context_id":
            "NON_DIFFICULT",

        "catalog_name":
            "notinalldifficultregions",

        "relative_path":
            "Union/GRCh38_notinalldifficultregions.bed.gz",

        "context_class":
            "COMPARATIVELY_UNCOMPLICATED",

        "selection_basis":
            (
                "Official GIAB complement of the "
                "combined difficult-region union; "
                "selected before benchmark outcomes."
            ),
    },
    {
        "context_id":
            "HOMOPOLYMER",

        "catalog_name":
            "AllHomopolymers_ge7bp_imperfectge11bp_slop5",

        "relative_path":
            (
                "LowComplexity/"
                "GRCh38_AllHomopolymers_ge7bp_"
                "imperfectge11bp_slop5.bed.gz"
            ),

        "context_class":
            "LOW_COMPLEXITY_HOMOPOLYMER",

        "selection_basis":
            (
                "Broad GIAB homopolymer stratification "
                "covering long perfect and imperfect "
                "homopolymer contexts; selected before "
                "benchmark outcomes."
            ),
    },
    {
        "context_id":
            "TANDEM_REPEAT",

        "catalog_name":
            "AllTandemRepeats",

        "relative_path":
            (
                "LowComplexity/"
                "GRCh38_AllTandemRepeats.bed.gz"
            ),

        "context_class":
            "LOW_COMPLEXITY_TANDEM_REPEAT",

        "selection_basis":
            (
                "Broad GIAB tandem-repeat "
                "stratification; selected before "
                "benchmark outcomes."
            ),
    },
    {
        "context_id":
            "LOW_MAPPABILITY",

        "catalog_name":
            "lowmappabilityall",

        "relative_path":
            (
                "Mappability/"
                "GRCh38_lowmappabilityall.bed.gz"
            ),

        "context_class":
            "DIFFICULT_MAPPING",

        "selection_basis":
            (
                "GIAB aggregate low-mappability "
                "stratification; selected before "
                "benchmark outcomes."
            ),
    },
    {
        "context_id":
            "SEGMENTAL_DUPLICATION",

        "catalog_name":
            "segdups",

        "relative_path":
            (
                "SegmentalDuplications/"
                "GRCh38_segdups.bed.gz"
            ),

        "context_class":
            "SEGMENTAL_DUPLICATION",

        "selection_basis":
            (
                "GIAB segmental-duplication "
                "stratification; selected before "
                "benchmark outcomes."
            ),
    },
]


MD5_RE = re.compile(
    r"^([0-9a-fA-F]{32})\s+\*?(.+?)\s*$"
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


def normalize_manifest_path(
    value: str,
) -> str:

    value = value.strip()

    while value.startswith("./"):
        value = value[2:]

    # Some manifests may include the GRCh38@all directory.
    marker = "GRCh38@all/"

    if marker in value:
        value = value.split(
            marker,
            1,
        )[1]

    return value


def parse_md5_manifest(
    path: Path,
) -> dict[str, str]:

    result = {}

    for raw in path.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():

        raw = raw.strip()

        if not raw:
            continue

        match = MD5_RE.match(
            raw
        )

        if not match:
            continue

        digest = (
            match.group(1)
            .lower()
        )

        relative = normalize_manifest_path(
            match.group(2)
        )

        result[
            relative
        ] = digest

    return result


def main() -> int:

    print("=" * 78)
    print(
        "PROJECT 003 — PHASE 2B "
        "CONTEXT BED FREEZE"
    )
    print("=" * 78)

    # --------------------------------------------------------
    # Verify upstream frozen state.
    # --------------------------------------------------------

    protocol = (
        ROOT
        / "docs/phase2/phase2_protocol.md"
    )

    admitted = (
        ROOT
        / "data/phase2/admitted_sources.tsv"
    )

    metadata_manifest = (
        ROOT
        / "data/phase2/"
        "stratification_metadata_manifest.tsv"
    )


    require(
        sha256_file(
            protocol
        )
        == EXPECTED_PROTOCOL_SHA256,
        "Phase 2 protocol changed",
    )


    require(
        sha256_file(
            admitted
        )
        == EXPECTED_ADMITTED_SOURCES_SHA256,
        "admitted sources changed",
    )


    require(
        sha256_file(
            metadata_manifest
        )
        ==
        EXPECTED_STRATIFICATION_METADATA_MANIFEST_SHA256,
        "stratification metadata manifest changed",
    )


    print(
        "PASS  frozen Phase 2 protocol"
    )

    print(
        "PASS  frozen admitted sources"
    )

    print(
        "PASS  frozen stratification metadata"
    )


    # --------------------------------------------------------
    # Parse catalog.
    # --------------------------------------------------------

    catalog_entries = {}

    for raw in CATALOG_PATH.read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines():

        raw = raw.strip()

        if not raw:
            continue

        parts = raw.split(
            "\t"
        )

        require(
            len(parts) >= 2,
            (
                "unexpected catalog line: "
                f"{raw}"
            ),
        )

        name = parts[0]
        relative = parts[1]

        catalog_entries[
            name
        ] = relative


    require(
        len(catalog_entries) >= 100,
        (
            "unexpectedly small "
            "stratification catalog"
        ),
    )


    # --------------------------------------------------------
    # Parse official GIAB MD5 manifest.
    # --------------------------------------------------------

    md5_entries = parse_md5_manifest(
        MD5_PATH
    )


    require(
        len(md5_entries) >= 100,
        (
            "unexpectedly small GRCh38 "
            "MD5 manifest"
        ),
    )


    print(
        "catalog entries:",
        len(
            catalog_entries
        ),
    )

    print(
        "MD5 entries:",
        len(
            md5_entries
        ),
    )


    # --------------------------------------------------------
    # Validate and freeze selected contexts.
    # --------------------------------------------------------

    output_rows = []


    for selected in SELECTED_CONTEXTS:

        context_id = (
            selected[
                "context_id"
            ]
        )

        catalog_name = (
            selected[
                "catalog_name"
            ]
        )

        expected_path = (
            selected[
                "relative_path"
            ]
        )


        require(
            catalog_name
            in catalog_entries,
            (
                "selected catalog entry missing: "
                f"{catalog_name}"
            ),
        )


        observed_catalog_path = (
            catalog_entries[
                catalog_name
            ]
        )


        require(
            observed_catalog_path
            == expected_path,
            (
                "catalog path mismatch\n"
                f"context: {context_id}\n"
                f"expected: {expected_path}\n"
                f"observed: "
                f"{observed_catalog_path}"
            ),
        )


        # Try exact relative path first.
        official_md5 = (
            md5_entries.get(
                expected_path
            )
        )


        # Fall back to unique basename match if the official
        # manifest has an additional directory prefix.
        if official_md5 is None:

            basename = Path(
                expected_path
            ).name

            matches = [
                digest
                for relative, digest
                in md5_entries.items()
                if Path(
                    relative
                ).name
                == basename
            ]


            require(
                len(matches) == 1,
                (
                    "could not uniquely resolve "
                    f"official MD5 for {expected_path}; "
                    f"matches={len(matches)}"
                ),
            )


            official_md5 = (
                matches[0]
            )


        require(
            bool(
                re.fullmatch(
                    r"[0-9a-f]{32}",
                    official_md5,
                )
            ),
            (
                "invalid official MD5 for "
                f"{context_id}"
            ),
        )


        url = (
            f"{BASE_URL}/"
            f"{expected_path}"
        )


        output_rows.append(
            {
                "context_id":
                    context_id,

                "context_class":
                    selected[
                        "context_class"
                    ],

                "stratification_version":
                    STRATIFICATION_VERSION,

                "reference_assembly":
                    "GRCh38",

                "catalog_name":
                    catalog_name,

                "relative_path":
                    expected_path,

                "url":
                    url,

                "official_md5":
                    official_md5,

                "selection_basis":
                    selected[
                        "selection_basis"
                    ],

                "benchmark_outcomes_consulted":
                    False,

                "download_state":
                    "NOT_DOWNLOADED",
            }
        )


        print()

        print(
            context_id
        )

        print(
            "  path:",
            expected_path,
        )

        print(
            "  MD5:",
            official_md5,
        )


    require(
        len(
            output_rows
        )
        == 5,
        "expected exactly five contexts",
    )


    require(
        len(
            {
                row[
                    "relative_path"
                ]
                for row
                in output_rows
            }
        )
        == 5,
        "duplicate selected BED path",
    )


    # --------------------------------------------------------
    # Write frozen context manifest.
    # --------------------------------------------------------

    fieldnames = [
        "context_id",
        "context_class",
        "stratification_version",
        "reference_assembly",
        "catalog_name",
        "relative_path",
        "url",
        "official_md5",
        "selection_basis",
        "benchmark_outcomes_consulted",
        "download_state",
    ]


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


    context_manifest_sha = (
        sha256_file(
            OUTPUT_PATH
        )
    )


    # --------------------------------------------------------
    # Freeze selection.
    # --------------------------------------------------------

    LOCK_PATH.write_text(
        "\n".join(
            [
                "project=Project 003",
                "phase=2B",
                (
                    "phase2_protocol_sha256="
                    f"{EXPECTED_PROTOCOL_SHA256}"
                ),
                (
                    "admitted_sources_sha256="
                    f"{EXPECTED_ADMITTED_SOURCES_SHA256}"
                ),
                (
                    "stratification_metadata_manifest_sha256="
                    f"{EXPECTED_STRATIFICATION_METADATA_MANIFEST_SHA256}"
                ),
                (
                    "stratification_version="
                    f"{STRATIFICATION_VERSION}"
                ),
                "reference_assembly=GRCh38",
                "context_count=5",
                (
                    "context_beds_sha256="
                    f"{context_manifest_sha}"
                ),
                (
                    "benchmark_outcomes_consulted="
                    "False"
                ),
                (
                    "status="
                    "FROZEN_BEFORE_CONTEXT_BED_DOWNLOAD"
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
            "FROZEN_BEFORE_CONTEXT_BED_DOWNLOAD",

        "stratification_version":
            STRATIFICATION_VERSION,

        "reference_assembly":
            "GRCh38",

        "context_count":
            len(
                output_rows
            ),

        "contexts":
            {
                row["context_id"]: {
                    "path":
                        row[
                            "relative_path"
                        ],

                    "official_md5":
                        row[
                            "official_md5"
                        ],
                }
                for row
                in output_rows
            },

        "benchmark_outcomes_consulted":
            False,

        "context_manifest_sha256":
            context_manifest_sha,

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
        "contexts frozen:",
        len(
            output_rows
        ),
    )

    print(
        "context manifest SHA-256:",
        context_manifest_sha,
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
        "PHASE2_CONTEXT_BEDS_FREEZE_PASS"
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
            "PHASE2_CONTEXT_BEDS_FREEZE_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
