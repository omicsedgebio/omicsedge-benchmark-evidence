#!/usr/bin/env python3

import csv
import hashlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROTOCOL = PROJECT_ROOT / "docs/phase1b/phase1b_protocol.md"
INPUT_MANIFEST = PROJECT_ROOT / "data/phase1b/input_manifest.tsv"
FREEZE_MANIFEST = PROJECT_ROOT / "data/phase1b/phase1b_freeze_manifest.tsv"
SYNTHETIC_CASES = PROJECT_ROOT / "tests/phase1b/synthetic_identity_cases.tsv"

PHASE1A_ARCHIVE = (
    PROJECT_ROOT
    / "data/phase1a/omicsedge_phase1a_results.tar.gz"
)

PHASE1A_RESULTS = (
    PROJECT_ROOT
    / "data/phase1a/omicsedge_phase1a_results"
)

CANDIDATES = (
    PHASE1A_RESULTS
    / "cross_run_candidates.tsv"
)

PHASE1A_CHECKSUMS = (
    PHASE1A_RESULTS
    / "checksums.sha256"
)


EXPECTED = {
    "protocol_sha256":
        "ec1833c55877b25c37be24483f8598ff89efb18850f4d733a08b492e55ef5c45",

    "input_manifest_sha256":
        "17dac2450069be57a9a6e13abf48390f4928f55f62f98bfad84cf323cdbae92d",

    "synthetic_cases_sha256":
        "b5570acd87ad721c1a8cabc416d3630455c0417715b0b6c73d70eff1aa3f5c27",

    "freeze_manifest_sha256":
        "5e17d1d0cb7d9d7339ace8cfe1cef829303dd7e628057983a9f220a16bd7b69d",

    "phase1a_archive_sha256":
        "6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202",

    "candidate_sha256":
        "c9d0d50e8e96ce0fd98773ccf9fe306e9beac2186771fc89c76b959f91b7d758",

    "candidate_records": 1666,

    "phase1a_checksum_records": 35,

    "synthetic_cases": 12,
}


EXPECTED_CANDIDATE_HEADER = [
    "run_a",
    "event_a",
    "run_b",
    "event_b",
    "normalized_allele_lookup_key",
    "equivalence_status",
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_sha256(
    path: Path,
    expected: str,
    label: str,
) -> None:

    require(
        path.is_file(),
        f"{label} missing: {path}",
    )

    observed = sha256_file(path)

    require(
        observed == expected,
        (
            f"{label} SHA-256 mismatch\n"
            f"expected: {expected}\n"
            f"observed: {observed}\n"
            f"path: {path}"
        ),
    )

    print(
        f"PASS  {label:<32} {observed}"
    )


def verify_detached_phase1a_checksums() -> None:

    require(
        PHASE1A_CHECKSUMS.is_file(),
        (
            "Phase 1A detached checksum file "
            f"missing: {PHASE1A_CHECKSUMS}"
        ),
    )

    records = []

    for raw in PHASE1A_CHECKSUMS.read_text(
        encoding="utf-8"
    ).splitlines():

        if not raw.strip():
            continue

        expected_sha, relative_path = raw.split(
            "  ",
            1,
        )

        records.append(
            (
                expected_sha,
                relative_path,
            )
        )

    require(
        len(records)
        == EXPECTED[
            "phase1a_checksum_records"
        ],
        (
            "Phase 1A detached checksum count "
            "mismatch: "
            f"expected "
            f"{EXPECTED['phase1a_checksum_records']}, "
            f"observed {len(records)}"
        ),
    )

    failures = []

    for expected_sha, relative_path in records:

        path = (
            PHASE1A_RESULTS
            / relative_path
        )

        if not path.is_file():
            failures.append(
                f"MISSING {relative_path}"
            )
            continue

        observed = sha256_file(path)

        if observed != expected_sha:
            failures.append(
                (
                    f"SHA256_MISMATCH "
                    f"{relative_path} "
                    f"expected={expected_sha} "
                    f"observed={observed}"
                )
            )

    require(
        not failures,
        (
            "Phase 1A detached checksum "
            "verification failed:\n"
            + "\n".join(failures)
        ),
    )

    print(
        "PASS  Phase 1A detached checksums     "
        f"{len(records)}/{len(records)}"
    )


def verify_candidate_input() -> None:

    verify_sha256(
        CANDIDATES,
        EXPECTED["candidate_sha256"],
        "candidate input",
    )

    with CANDIDATES.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:

        reader = csv.reader(
            handle,
            delimiter="\t",
        )

        header = next(reader)

        require(
            header
            == EXPECTED_CANDIDATE_HEADER,
            (
                "candidate header mismatch\n"
                f"expected: "
                f"{EXPECTED_CANDIDATE_HEADER}\n"
                f"observed: {header}"
            ),
        )

        row_count = sum(
            1
            for _ in reader
        )

    require(
        row_count
        == EXPECTED["candidate_records"],
        (
            "candidate record count mismatch: "
            f"expected "
            f"{EXPECTED['candidate_records']}, "
            f"observed {row_count}"
        ),
    )

    print(
        "PASS  candidate schema/header"
    )

    print(
        "PASS  candidate record count          "
        f"{row_count}"
    )


def verify_synthetic_spec() -> None:

    verify_sha256(
        SYNTHETIC_CASES,
        EXPECTED["synthetic_cases_sha256"],
        "synthetic test specification",
    )

    with SYNTHETIC_CASES.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:

        reader = csv.DictReader(
            handle,
            delimiter="\t",
        )

        rows = list(reader)

    require(
        len(rows)
        == EXPECTED["synthetic_cases"],
        (
            "synthetic case count mismatch: "
            f"expected "
            f"{EXPECTED['synthetic_cases']}, "
            f"observed {len(rows)}"
        ),
    )

    allowed = {
        "EXACT_NORMALIZED_ALLELE",
        "REPRESENTATION_EQUIVALENCE_SUPPORTED",
        "NON_EQUIVALENT",
        "UNRESOLVED",
    }

    invalid = [
        row["case_id"]
        for row in rows
        if row["expected_status"]
        not in allowed
    ]

    require(
        not invalid,
        (
            "synthetic specification contains "
            "invalid expected states: "
            + ", ".join(invalid)
        ),
    )

    print(
        "PASS  synthetic case count            "
        f"{len(rows)}"
    )


def verify_freeze_manifest_contents() -> None:

    with FREEZE_MANIFEST.open(
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
        len(rows) == 3,
        (
            "freeze manifest should contain "
            f"3 records; found {len(rows)}"
        ),
    )

    for row in rows:

        path = (
            PROJECT_ROOT
            / row["path"]
        )

        require(
            path.is_file(),
            (
                "freeze-manifest artifact "
                f"missing: {path}"
            ),
        )

        observed = sha256_file(path)

        require(
            observed == row["sha256"],
            (
                "freeze-manifest artifact "
                "checksum mismatch\n"
                f"artifact_id: "
                f"{row['artifact_id']}\n"
                f"expected: "
                f"{row['sha256']}\n"
                f"observed: {observed}"
            ),
        )

    print(
        "PASS  freeze-manifest artifacts       "
        "3/3"
    )


def main() -> int:

    print(
        "=" * 78
    )

    print(
        "PROJECT 003 — PHASE 1B "
        "FROZEN INPUT PREFLIGHT"
    )

    print(
        "=" * 78
    )

    verify_sha256(
        PROTOCOL,
        EXPECTED["protocol_sha256"],
        "frozen protocol",
    )

    verify_sha256(
        INPUT_MANIFEST,
        EXPECTED[
            "input_manifest_sha256"
        ],
        "input manifest",
    )

    verify_sha256(
        FREEZE_MANIFEST,
        EXPECTED[
            "freeze_manifest_sha256"
        ],
        "freeze manifest",
    )

    verify_sha256(
        PHASE1A_ARCHIVE,
        EXPECTED[
            "phase1a_archive_sha256"
        ],
        "Phase 1A archive",
    )

    verify_freeze_manifest_contents()

    verify_detached_phase1a_checksums()

    verify_candidate_input()

    verify_synthetic_spec()

    print()

    print(
        "PHASE1B_FROZEN_INPUT_PREFLIGHT_PASS"
    )

    print(
        "=" * 78
    )

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print()
        print(
            "PHASE1B_FROZEN_INPUT_PREFLIGHT_FAIL"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        sys.exit(1)
