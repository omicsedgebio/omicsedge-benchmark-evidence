#!/usr/bin/env python3

import csv
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(PROJECT_ROOT / "src"),
)

from benchmark_evidence.phase1b_identity import (  # noqa: E402
    EXACT_NORMALIZED_ALLELE,
    REPRESENTATION_EQUIVALENCE_SUPPORTED,
    classify_identity,
    variant_id,
)


CASES = (
    PROJECT_ROOT
    / "tests/phase1b/synthetic_identity_cases.tsv"
)

EXPECTED_CASES_SHA256 = (
    "b5570acd87ad721c1a8cabc416d3630455c0417715b0b6c73d70eff1aa3f5c27"
)


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def make_allele(
    row,
    suffix,
):
    return {
        "assembly":
            row[f"assembly_{suffix}"],
        "contig":
            row[f"contig_{suffix}"],
        "start":
            int(row[f"start_{suffix}"]),
        "end":
            int(row[f"end_{suffix}"]),
        "ref":
            row[f"ref_{suffix}"],
        "alt":
            row[f"alt_{suffix}"],
    }


observed_spec_sha = sha256_file(
    CASES
)

if observed_spec_sha != EXPECTED_CASES_SHA256:
    raise RuntimeError(
        "frozen synthetic specification changed\n"
        f"expected: {EXPECTED_CASES_SHA256}\n"
        f"observed: {observed_spec_sha}"
    )


with CASES.open(
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


if len(rows) != 12:
    raise RuntimeError(
        f"expected 12 frozen cases, found {len(rows)}"
    )


failures = []


for row in rows:

    allele_a = make_allele(
        row,
        "a",
    )

    allele_b = make_allele(
        row,
        "b",
    )

    observed = classify_identity(
        allele_a,
        allele_b,
    )

    expected = row[
        "expected_status"
    ]

    if observed != expected:
        failures.append(
            (
                row["case_id"],
                expected,
                observed,
            )
        )

    # Determinism check.
    id_a_1 = variant_id(
        allele_a
    )

    id_a_2 = variant_id(
        allele_a
    )

    id_b_1 = variant_id(
        allele_b
    )

    id_b_2 = variant_id(
        allele_b
    )

    if id_a_1 != id_a_2:
        failures.append(
            (
                row["case_id"],
                "DETERMINISTIC_VARIANT_ID_A",
                "FAILED",
            )
        )

    if id_b_1 != id_b_2:
        failures.append(
            (
                row["case_id"],
                "DETERMINISTIC_VARIANT_ID_B",
                "FAILED",
            )
        )

    # Exact identity must generate the same biological
    # variant identifier.
    if (
        observed
        == EXACT_NORMALIZED_ALLELE
        and
        id_a_1 != id_b_1
    ):
        failures.append(
            (
                row["case_id"],
                "SAME_VARIANT_ID_FOR_EXACT",
                "FAILED",
            )
        )

    # v1 must never claim representation equivalence.
    if (
        observed
        ==
        REPRESENTATION_EQUIVALENCE_SUPPORTED
    ):
        failures.append(
            (
                row["case_id"],
                "NO_REPRESENTATION_EQUIVALENCE_IN_V1",
                observed,
            )
        )

    print(
        f"{row['case_id']} "
        f"{observed} "
        f"{'PASS' if observed == expected else 'FAIL'}"
    )


print()
print(
    f"synthetic cases evaluated: {len(rows)}"
)

print(
    f"failures: {len(failures)}"
)


if failures:

    for failure in failures:
        print(
            "FAIL",
            *failure,
        )

    print()
    print(
        "PHASE1B_IDENTITY_PRIMITIVE_FAIL"
    )

    sys.exit(1)


print()
print(
    "PHASE1B_IDENTITY_PRIMITIVE_PASS"
)
