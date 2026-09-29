#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]

ADMITTED_SOURCES = (
    ROOT
    / "data/phase2/admitted_sources.tsv"
)

INTERVAL_METHOD = (
    ROOT
    / "docs/phase2/interval_selection_method.md"
)

TRUTH_BED_DIR = (
    ROOT
    / "data/phase2/truth_beds"
)

TRUTH_BED_MANIFEST = (
    ROOT
    / "data/phase2/truth_beds_manifest.tsv"
)

SHARED_CALLABLE = (
    ROOT
    / "data/phase2/shared_callable.bed"
)

SUMMARY_PATH = (
    ROOT
    / "results/phase2/shared_callable_summary.json"
)

LOCK_PATH = (
    ROOT
    / "data/phase2/shared_callable.lock"
)


EXPECTED_ADMITTED_SOURCES_SHA256 = (
    "55ebf63901ac0c118cb5ec687b49cc81cf680bb9357246ba2f6138b27a29641f"
)

EXPECTED_INTERVAL_METHOD_SHA256 = (
    "b3dd8fdbd8c308a9f9098fbc213a9a243ceec081b92b74862d60d212ea1619b2"
)

EXPECTED_SAMPLES = {
    "HG003",
    "HG004",
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
            "--retry",
            "3",
            "--retry-delay",
            "2",
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


def chromosome_sort_key(
    chrom: str,
) -> tuple:

    value = chrom

    if value.lower().startswith("chr"):
        value = value[3:]

    if value.isdigit():
        return (
            0,
            int(value),
        )

    special = {
        "X": 23,
        "Y": 24,
        "M": 25,
        "MT": 25,
    }

    upper = value.upper()

    if upper in special:
        return (
            0,
            special[upper],
        )

    return (
        1,
        chrom,
    )


def parse_bed(
    path: Path,
) -> tuple[
    dict[str, list[tuple[int, int]]],
    dict,
]:

    intervals = defaultdict(
        list
    )

    raw_interval_count = 0
    raw_bases = 0

    with path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as handle:

        for line_number, raw in enumerate(
            handle,
            start=1,
        ):

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

            parts = line.split()

            require(
                len(parts) >= 3,
                (
                    f"{path}: invalid BED row "
                    f"at line {line_number}"
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
                        f"{path}: non-integer BED "
                        f"coordinate at line "
                        f"{line_number}"
                    )
                ) from exc

            require(
                start >= 0,
                (
                    f"{path}: negative start "
                    f"at line {line_number}"
                ),
            )

            require(
                end > start,
                (
                    f"{path}: end <= start "
                    f"at line {line_number}"
                ),
            )

            intervals[
                chrom
            ].append(
                (
                    start,
                    end,
                )
            )

            raw_interval_count += 1
            raw_bases += (
                end - start
            )

    require(
        raw_interval_count > 0,
        f"{path}: no BED intervals",
    )

    return (
        intervals,
        {
            "raw_interval_count":
                raw_interval_count,

            "raw_interval_bases":
                raw_bases,

            "raw_chromosome_count":
                len(intervals),
        },
    )


def merge_intervals(
    intervals_by_chrom: dict[
        str,
        list[
            tuple[
                int,
                int,
            ]
        ],
    ],
) -> dict[
    str,
    list[
        tuple[
            int,
            int,
        ]
    ],
]:

    merged = {}

    for chrom, intervals in (
        intervals_by_chrom.items()
    ):

        ordered = sorted(
            intervals
        )

        output = []

        for start, end in ordered:

            if not output:

                output.append(
                    [
                        start,
                        end,
                    ]
                )

                continue

            previous = output[-1]

            if start <= previous[1]:

                if end > previous[1]:
                    previous[1] = end

            else:

                output.append(
                    [
                        start,
                        end,
                    ]
                )

        merged[
            chrom
        ] = [
            (
                start,
                end,
            )
            for start, end
            in output
        ]

    return merged


def interval_stats(
    intervals_by_chrom,
) -> dict:

    count = 0
    bases = 0

    for intervals in (
        intervals_by_chrom.values()
    ):

        count += len(
            intervals
        )

        bases += sum(
            end - start
            for start, end
            in intervals
        )

    return {
        "interval_count":
            count,

        "bases":
            bases,

        "chromosome_count":
            len(
                [
                    chrom
                    for chrom, intervals
                    in intervals_by_chrom.items()
                    if intervals
                ]
            ),
    }


def intersect_two(
    left: dict[
        str,
        list[
            tuple[
                int,
                int,
            ]
        ],
    ],
    right: dict[
        str,
        list[
            tuple[
                int,
                int,
            ]
        ],
    ],
) -> dict[
    str,
    list[
        tuple[
            int,
            int,
        ]
    ],
]:

    result = {}

    common_chroms = (
        set(left)
        & set(right)
    )

    for chrom in common_chroms:

        a = left[
            chrom
        ]

        b = right[
            chrom
        ]

        i = 0
        j = 0
        intersections = []

        while (
            i < len(a)
            and
            j < len(b)
        ):

            a_start, a_end = a[i]
            b_start, b_end = b[j]

            start = max(
                a_start,
                b_start,
            )

            end = min(
                a_end,
                b_end,
            )

            if start < end:

                intersections.append(
                    (
                        start,
                        end,
                    )
                )

            if a_end < b_end:
                i += 1

            else:
                j += 1

        if intersections:

            result[
                chrom
            ] = intersections

    return merge_intervals(
        result
    )


def write_bed(
    path: Path,
    intervals_by_chrom,
) -> None:

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        for chrom in sorted(
            intervals_by_chrom,
            key=chromosome_sort_key,
        ):

            for start, end in (
                intervals_by_chrom[
                    chrom
                ]
            ):

                handle.write(
                    f"{chrom}\t{start}\t{end}\n"
                )


def main() -> int:

    print("=" * 78)

    print(
        "PROJECT 003 — PHASE 2B "
        "SHARED CALLABLE UNIVERSE"
    )

    print("=" * 78)

    # --------------------------------------------------------
    # Verify frozen upstream inputs.
    # --------------------------------------------------------

    require(
        sha256_file(
            ADMITTED_SOURCES
        )
        ==
        EXPECTED_ADMITTED_SOURCES_SHA256,
        "admitted source manifest changed",
    )

    require(
        sha256_file(
            INTERVAL_METHOD
        )
        ==
        EXPECTED_INTERVAL_METHOD_SHA256,
        "interval-selection method changed",
    )

    print(
        "PASS  frozen admitted-source SHA-256"
    )

    print(
        "PASS  frozen interval-selection method SHA-256"
    )


    admitted = read_tsv(
        ADMITTED_SOURCES
    )


    # --------------------------------------------------------
    # Derive one unique benchmark BED URL per sample.
    # Both technologies for a sample must point to the same
    # frozen truth-region BED.
    # --------------------------------------------------------

    sample_urls = defaultdict(
        set
    )

    for row in admitted:

        sample_urls[
            row["sample_id"]
        ].add(
            row[
                "benchmark_bed_url"
            ]
        )


    require(
        set(
            sample_urls
        )
        == EXPECTED_SAMPLES,
        (
            "unexpected Phase 2 sample set: "
            f"{sorted(sample_urls)}"
        ),
    )


    for sample_id in EXPECTED_SAMPLES:

        require(
            len(
                sample_urls[
                    sample_id
                ]
            )
            == 1,
            (
                f"{sample_id} technologies do not "
                "share one benchmark BED URL"
            ),
        )


    print(
        "PASS  HG003/HG004 benchmark-BED provenance"
    )


    # --------------------------------------------------------
    # Download and validate source BEDs.
    # --------------------------------------------------------

    TRUTH_BED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    merged_by_sample = {}

    manifest_rows = []


    for sample_id in sorted(
        EXPECTED_SAMPLES
    ):

        url = next(
            iter(
                sample_urls[
                    sample_id
                ]
            )
        )


        remote_name = Path(
            urlparse(
                url
            ).path
        ).name


        require(
            remote_name,
            (
                f"cannot derive filename "
                f"for {sample_id}"
            ),
        )


        local_path = (
            TRUTH_BED_DIR
            / remote_name
        )


        print()

        print(
            "Downloading:",
            sample_id,
        )

        print(
            " ",
            url,
        )


        download(
            url,
            local_path,
        )


        require(
            local_path.is_file(),
            (
                "downloaded benchmark BED "
                f"missing: {local_path}"
            ),
        )

        require(
            local_path.stat().st_size > 0,
            (
                "downloaded benchmark BED "
                f"is empty: {local_path}"
            ),
        )


        (
            raw_intervals,
            raw_stats,
        ) = parse_bed(
            local_path
        )


        merged = merge_intervals(
            raw_intervals
        )


        merged_stats = (
            interval_stats(
                merged
            )
        )


        merged_by_sample[
            sample_id
        ] = merged


        observed_sha = (
            sha256_file(
                local_path
            )
        )


        print(
            "  SHA-256:",
            observed_sha,
        )

        print(
            "  raw intervals:",
            raw_stats[
                "raw_interval_count"
            ],
        )

        print(
            "  merged intervals:",
            merged_stats[
                "interval_count"
            ],
        )

        print(
            "  merged bases:",
            merged_stats[
                "bases"
            ],
        )

        print(
            "  chromosomes:",
            merged_stats[
                "chromosome_count"
            ],
        )


        manifest_rows.append(
            {
                "sample_id":
                    sample_id,

                "reference_assembly":
                    "GRCh38",

                "truth_version":
                    "GIAB_v4.2.1",

                "benchmark_bed_url":
                    url,

                "local_path":
                    str(
                        local_path.relative_to(
                            ROOT
                        )
                    ),

                "size_bytes":
                    local_path.stat().st_size,

                "sha256":
                    observed_sha,

                "raw_interval_count":
                    raw_stats[
                        "raw_interval_count"
                    ],

                "merged_interval_count":
                    merged_stats[
                        "interval_count"
                    ],

                "merged_bases":
                    merged_stats[
                        "bases"
                    ],

                "chromosome_count":
                    merged_stats[
                        "chromosome_count"
                    ],
            }
        )


    # --------------------------------------------------------
    # Build deterministic HG003 ∩ HG004 shared callable.
    # --------------------------------------------------------

    shared = intersect_two(
        merged_by_sample[
            "HG003"
        ],
        merged_by_sample[
            "HG004"
        ],
    )


    shared_stats = interval_stats(
        shared
    )


    require(
        shared_stats[
            "interval_count"
        ]
        > 0,
        (
            "HG003/HG004 shared callable "
            "intersection is empty"
        ),
    )


    write_bed(
        SHARED_CALLABLE,
        shared,
    )


    require(
        SHARED_CALLABLE.is_file(),
        "shared_callable.bed not created",
    )


    shared_sha = sha256_file(
        SHARED_CALLABLE
    )


    # --------------------------------------------------------
    # Validate required autosomal scope.
    # --------------------------------------------------------

    shared_chromosomes = {
        chrom
        for chrom, intervals
        in shared.items()
        if intervals
    }


    required_autosomes = {
        f"chr{i}"
        for i in range(
            1,
            23,
        )
    }


    require(
        required_autosomes
        <= shared_chromosomes,
        (
            "shared callable universe is missing "
            "one or more chr1-chr22 autosomes: "
            f"{sorted(required_autosomes - shared_chromosomes)}"
        ),
    )


    print()

    print(
        "PASS  HG003/HG004 shared callable intersection"
    )

    print(
        "shared intervals:",
        shared_stats[
            "interval_count"
        ],
    )

    print(
        "shared bases:",
        shared_stats[
            "bases"
        ],
    )

    print(
        "shared chromosomes:",
        shared_stats[
            "chromosome_count"
        ],
    )

    print(
        "PASS  shared callable contains chr1-chr22"
    )


    # --------------------------------------------------------
    # Record autosomal selection universe excluding chr20.
    # --------------------------------------------------------

    eligible_chromosomes = [
        f"chr{i}"
        for i in range(
            1,
            23,
        )
        if i != 20
    ]


    eligible_shared = {
        chrom:
            shared[
                chrom
            ]
        for chrom
        in eligible_chromosomes
    }


    eligible_stats = interval_stats(
        eligible_shared
    )


    require(
        "chr20"
        not in eligible_shared,
        "chr20 exclusion failed",
    )


    require(
        eligible_stats[
            "chromosome_count"
        ]
        == 21,
        (
            "expected 21 eligible autosomes "
            "after excluding chr20"
        ),
    )


    print(
        "eligible Phase 2 chromosomes:",
        eligible_stats[
            "chromosome_count"
        ],
    )

    print(
        "eligible shared-callable bases:",
        eligible_stats[
            "bases"
        ],
    )


    # --------------------------------------------------------
    # Write truth BED manifest.
    # --------------------------------------------------------

    manifest_fields = [
        "sample_id",
        "reference_assembly",
        "truth_version",
        "benchmark_bed_url",
        "local_path",
        "size_bytes",
        "sha256",
        "raw_interval_count",
        "merged_interval_count",
        "merged_bases",
        "chromosome_count",
    ]


    with TRUTH_BED_MANIFEST.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=manifest_fields,
            delimiter="\t",
            lineterminator="\n",
        )

        writer.writeheader()

        writer.writerows(
            sorted(
                manifest_rows,
                key=lambda row:
                    row["sample_id"],
            )
        )


    truth_manifest_sha = (
        sha256_file(
            TRUTH_BED_MANIFEST
        )
    )


    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    summary = {
        "project":
            "Project 003",

        "phase":
            "2B",

        "operation":
            "SHARED_CALLABLE_INTERSECTION",

        "reference_assembly":
            "GRCh38",

        "truth_version":
            "GIAB_v4.2.1",

        "samples":
            [
                "HG003",
                "HG004",
            ],

        "query_vcfs_consulted":
            False,

        "benchmark_outcomes_consulted":
            False,

        "truth_beds":
            {
                row["sample_id"]: {
                    "sha256":
                        row[
                            "sha256"
                        ],

                    "size_bytes":
                        int(
                            row[
                                "size_bytes"
                            ]
                        ),

                    "raw_interval_count":
                        int(
                            row[
                                "raw_interval_count"
                            ]
                        ),

                    "merged_interval_count":
                        int(
                            row[
                                "merged_interval_count"
                            ]
                        ),

                    "merged_bases":
                        int(
                            row[
                                "merged_bases"
                            ]
                        ),
                }
                for row
                in manifest_rows
            },

        "shared_callable": {
            "path":
                str(
                    SHARED_CALLABLE.relative_to(
                        ROOT
                    )
                ),

            "sha256":
                shared_sha,

            "interval_count":
                shared_stats[
                    "interval_count"
                ],

            "bases":
                shared_stats[
                    "bases"
                ],

            "chromosome_count":
                shared_stats[
                    "chromosome_count"
                ],
        },

        "phase2_eligible_scope": {
            "chromosomes":
                eligible_chromosomes,

            "excluded_chromosome":
                "chr20",

            "chromosome_count":
                eligible_stats[
                    "chromosome_count"
                ],

            "shared_callable_bases":
                eligible_stats[
                    "bases"
                ],
        },

        "truth_bed_manifest_sha256":
            truth_manifest_sha,
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
    # Freeze shared callable authority.
    # --------------------------------------------------------

    LOCK_PATH.write_text(
        "\n".join(
            [
                "project=Project 003",
                "phase=2B",
                (
                    "admitted_sources_sha256="
                    f"{EXPECTED_ADMITTED_SOURCES_SHA256}"
                ),
                (
                    "interval_selection_method_sha256="
                    f"{EXPECTED_INTERVAL_METHOD_SHA256}"
                ),
                (
                    "truth_beds_manifest_sha256="
                    f"{truth_manifest_sha}"
                ),
                (
                    "shared_callable_sha256="
                    f"{shared_sha}"
                ),
                (
                    "shared_callable_intervals="
                    f"{shared_stats['interval_count']}"
                ),
                (
                    "shared_callable_bases="
                    f"{shared_stats['bases']}"
                ),
                "phase2_eligible_autosomes=21",
                "excluded_chromosome=chr20",
                "query_vcfs_consulted=False",
                "benchmark_outcomes_consulted=False",
                (
                    "status="
                    "FROZEN_BEFORE_INTERVAL_SELECTION"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


    print()

    print(
        "truth BED manifest SHA-256:",
        truth_manifest_sha,
    )

    print(
        "shared callable SHA-256:",
        shared_sha,
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
        "PHASE2_SHARED_CALLABLE_FREEZE_PASS"
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
            "PHASE2_SHARED_CALLABLE_FREEZE_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
