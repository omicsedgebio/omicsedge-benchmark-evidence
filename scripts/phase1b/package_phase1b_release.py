#!/usr/bin/env python3

from __future__ import annotations

import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

MANIFEST_PATH = (
    ROOT
    / "results/phase1b/phase1b_release_manifest.json"
)

ARCHIVE_PATH = (
    ROOT
    / "results/phase1b/omicsedge_phase1b_results.tar.gz"
)

DETACHED_SHA_PATH = (
    ROOT
    / "results/phase1b/omicsedge_phase1b_results.tar.gz.sha256"
)


EXPECTED_MANIFEST_SHA256 = (
    "2442378e76a79f4a6a940eacd6508c15d538cbdcc8eb463e433e4a6c7340235e"
)

EXPECTED_MANIFEST_ARTIFACTS = 34
EXPECTED_ARCHIVE_FILES = 35


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


def deterministic_tar_gz(
    output_path: Path,
    members: list[tuple[str, Path]],
) -> None:

    with output_path.open("wb") as raw:

        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            mtime=0,
        ) as gz:

            with tarfile.open(
                mode="w",
                fileobj=gz,
                format=tarfile.USTAR_FORMAT,
            ) as tar:

                for archive_name, source_path in members:

                    data = source_path.read_bytes()

                    info = tarfile.TarInfo(
                        name=archive_name
                    )

                    info.size = len(data)
                    info.mtime = 0
                    info.mode = 0o644
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""

                    tar.addfile(
                        info,
                        io.BytesIO(data),
                    )


def safe_extract(
    archive_path: Path,
    destination: Path,
) -> list[str]:

    extracted_names = []

    with tarfile.open(
        archive_path,
        mode="r:gz",
    ) as tar:

        for member in tar.getmembers():

            require(
                member.isfile(),
                (
                    "archive contains non-file member: "
                    f"{member.name}"
                ),
            )

            member_path = Path(
                member.name
            )

            require(
                not member_path.is_absolute(),
                (
                    "archive contains absolute path: "
                    f"{member.name}"
                ),
            )

            require(
                ".."
                not in member_path.parts,
                (
                    "archive contains unsafe parent path: "
                    f"{member.name}"
                ),
            )

            target = (
                destination
                / member_path
            )

            target.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            source = tar.extractfile(
                member
            )

            require(
                source is not None,
                (
                    "unable to read archive member: "
                    f"{member.name}"
                ),
            )

            with source:

                with target.open(
                    "wb"
                ) as handle:

                    shutil.copyfileobj(
                        source,
                        handle,
                    )

            extracted_names.append(
                member.name
            )

    return extracted_names


def main() -> int:

    print("=" * 78)

    print(
        "PROJECT 003 — PHASE 1B "
        "FINAL RELEASE PACKAGING"
    )

    print("=" * 78)

    # --------------------------------------------------------
    # Verify release manifest.
    # --------------------------------------------------------

    require(
        MANIFEST_PATH.is_file(),
        "release manifest is missing",
    )

    observed_manifest_sha = (
        sha256_file(
            MANIFEST_PATH
        )
    )

    require(
        observed_manifest_sha
        == EXPECTED_MANIFEST_SHA256,
        (
            "release manifest SHA-256 mismatch\n"
            f"expected: {EXPECTED_MANIFEST_SHA256}\n"
            f"observed: {observed_manifest_sha}"
        ),
    )

    print(
        "PASS  frozen release manifest SHA-256"
    )


    manifest = json.loads(
        MANIFEST_PATH.read_text(
            encoding="utf-8"
        )
    )


    require(
        manifest[
            "scientific_gate"
        ]
        == "PASS",
        "release manifest scientific gate is not PASS",
    )

    require(
        manifest[
            "validation_criteria"
        ]
        == "15/15 PASS",
        "release manifest does not record 15/15 PASS",
    )


    artifacts = manifest[
        "artifacts"
    ]


    require(
        len(artifacts)
        == EXPECTED_MANIFEST_ARTIFACTS,
        (
            "unexpected manifest artifact count: "
            f"{len(artifacts)}"
        ),
    )

    print(
        "PASS  manifest artifacts:",
        len(artifacts),
    )


    # --------------------------------------------------------
    # Reverify every source artifact immediately before
    # packaging.
    # --------------------------------------------------------

    source_members = []

    for artifact in artifacts:

        relative = artifact[
            "path"
        ]

        source = (
            ROOT
            / relative
        )

        require(
            source.is_file(),
            (
                "missing authoritative artifact: "
                f"{relative}"
            ),
        )

        observed = sha256_file(
            source
        )

        require(
            observed
            == artifact[
                "sha256"
            ],
            (
                "authoritative artifact changed "
                "after release-manifest freeze:\n"
                f"{relative}\n"
                f"expected: {artifact['sha256']}\n"
                f"observed: {observed}"
            ),
        )

        require(
            source.stat().st_size
            == artifact[
                "size_bytes"
            ],
            (
                "authoritative artifact size changed: "
                f"{relative}"
            ),
        )

        source_members.append(
            (
                relative,
                source,
            )
        )


    print(
        "PASS  all 34 source artifacts "
        "match frozen manifest"
    )


    # --------------------------------------------------------
    # Add the release manifest itself as the 35th member.
    # --------------------------------------------------------

    manifest_relative = (
        "results/phase1b/"
        "phase1b_release_manifest.json"
    )

    require(
        manifest_relative
        not in {
            name
            for name, _path
            in source_members
        },
        (
            "release manifest is unexpectedly "
            "already listed as an artifact"
        ),
    )


    archive_members = (
        source_members
        + [
            (
                manifest_relative,
                MANIFEST_PATH,
            )
        ]
    )


    archive_members = sorted(
        archive_members,
        key=lambda item: item[0],
    )


    require(
        len(
            archive_members
        )
        == EXPECTED_ARCHIVE_FILES,
        (
            "unexpected archive member count: "
            f"{len(archive_members)}"
        ),
    )


    # --------------------------------------------------------
    # Create deterministic tar.gz.
    # --------------------------------------------------------

    if ARCHIVE_PATH.exists():
        ARCHIVE_PATH.unlink()

    if DETACHED_SHA_PATH.exists():
        DETACHED_SHA_PATH.unlink()


    deterministic_tar_gz(
        ARCHIVE_PATH,
        archive_members,
    )


    require(
        ARCHIVE_PATH.is_file(),
        "archive was not created",
    )


    archive_sha = sha256_file(
        ARCHIVE_PATH
    )


    DETACHED_SHA_PATH.write_text(
        (
            f"{archive_sha}  "
            f"{ARCHIVE_PATH.name}\n"
        ),
        encoding="utf-8",
    )


    print(
        "PASS  deterministic archive created"
    )


    # --------------------------------------------------------
    # Detached archive checksum verification.
    # --------------------------------------------------------

    detached_line = (
        DETACHED_SHA_PATH.read_text(
            encoding="utf-8"
        )
        .strip()
    )

    detached_sha, detached_name = (
        detached_line.split(
            "  ",
            1,
        )
    )


    require(
        detached_name
        == ARCHIVE_PATH.name,
        (
            "detached checksum filename mismatch"
        ),
    )

    require(
        detached_sha
        == sha256_file(
            ARCHIVE_PATH
        ),
        (
            "detached archive checksum "
            "verification failed"
        ),
    )


    print(
        "PASS  detached archive SHA-256"
    )


    # --------------------------------------------------------
    # Independently extract into a temporary directory.
    # --------------------------------------------------------

    with tempfile.TemporaryDirectory(
        prefix="omicsedge-phase1b-release-audit-"
    ) as tmp:

        temp_root = Path(
            tmp
        )

        extracted_names = safe_extract(
            ARCHIVE_PATH,
            temp_root,
        )


        require(
            len(
                extracted_names
            )
            == EXPECTED_ARCHIVE_FILES,
            (
                "extracted file count mismatch: "
                f"{len(extracted_names)}"
            ),
        )


        require(
            len(
                set(
                    extracted_names
                )
            )
            == EXPECTED_ARCHIVE_FILES,
            (
                "archive contains duplicate filenames"
            ),
        )


        expected_names = {
            relative
            for relative, _source
            in archive_members
        }


        require(
            set(
                extracted_names
            )
            == expected_names,
            (
                "archive filename set differs "
                "from authoritative release set"
            ),
        )


        print(
            "PASS  archive member set: 35 files"
        )


        # ----------------------------------------------------
        # Verify the extracted manifest itself.
        # ----------------------------------------------------

        extracted_manifest = (
            temp_root
            / manifest_relative
        )


        require(
            sha256_file(
                extracted_manifest
            )
            == EXPECTED_MANIFEST_SHA256,
            (
                "packaged release manifest "
                "checksum mismatch"
            ),
        )


        print(
            "PASS  packaged release manifest SHA-256"
        )


        # ----------------------------------------------------
        # Verify all 34 extracted artifacts against the
        # packaged manifest.
        # ----------------------------------------------------

        packaged_manifest = json.loads(
            extracted_manifest.read_text(
                encoding="utf-8"
            )
        )


        packaged_artifacts = (
            packaged_manifest[
                "artifacts"
            ]
        )


        require(
            len(
                packaged_artifacts
            )
            == EXPECTED_MANIFEST_ARTIFACTS,
            (
                "packaged manifest artifact "
                "count mismatch"
            ),
        )


        verified = 0


        for artifact in packaged_artifacts:

            relative = artifact[
                "path"
            ]

            extracted_path = (
                temp_root
                / relative
            )


            require(
                extracted_path.is_file(),
                (
                    "packaged artifact missing: "
                    f"{relative}"
                ),
            )


            observed_sha = sha256_file(
                extracted_path
            )


            require(
                observed_sha
                == artifact[
                    "sha256"
                ],
                (
                    "packaged artifact SHA-256 "
                    f"mismatch: {relative}"
                ),
            )


            require(
                extracted_path.stat().st_size
                == artifact[
                    "size_bytes"
                ],
                (
                    "packaged artifact size "
                    f"mismatch: {relative}"
                ),
            )


            verified += 1


        require(
            verified
            == EXPECTED_MANIFEST_ARTIFACTS,
            (
                "not all packaged artifacts "
                "were verified"
            ),
        )


        print(
            "PASS  packaged artifacts verified:",
            verified,
            "/",
            EXPECTED_MANIFEST_ARTIFACTS,
        )


    # --------------------------------------------------------
    # Human-readable result.
    # --------------------------------------------------------

    print()

    print(
        "archive:",
        ARCHIVE_PATH.relative_to(
            ROOT
        ),
    )

    print(
        "archive size:",
        ARCHIVE_PATH.stat().st_size,
        "bytes",
    )

    print(
        "archive SHA-256:",
        archive_sha,
    )

    print(
        "detached checksum:",
        DETACHED_SHA_PATH.relative_to(
            ROOT
        ),
    )

    print()

    print(
        "archive files:",
        EXPECTED_ARCHIVE_FILES,
    )

    print(
        "manifest-tracked artifacts:",
        EXPECTED_MANIFEST_ARTIFACTS,
    )

    print()

    print(
        "PHASE1B_FINAL_ARCHIVE_VERIFICATION_PASS"
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
            "PHASE1B_FINAL_ARCHIVE_VERIFICATION_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
