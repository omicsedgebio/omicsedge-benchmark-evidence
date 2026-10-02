#!/usr/bin/env python3
"""Build the immutable-artifact manifest for the released Evidence Atlas v1.0.0.

The freeze has two explicitly separate lineages, both derived from Git
objects rather than the working tree:

* ``scientific_release``: every file in the ``v1.0.0`` tag tree, except the
  small set of living repository files in ``LIVING_PATHS`` / ``LIVING_PREFIXES``.
  These files existed at the tag.
* ``web_delivery``: the validated Evidence Explorer browser-delivery
  representation of the frozen v1 scientific release. These files were added
  AFTER the tag, up to commit ``da19599``, and recompute no science.

Each lineage gets its own SHA-256 manifest; ``frozen_artifacts.sha256`` is
their union and is kept for continuity.

SHA-256 digests are computed from the committed blob bytes. The script then
verifies that the working tree still matches every frozen digest and refuses
to write the manifest otherwise.

Usage (from the repository root):

    python scripts/atlas/build_v1_freeze_manifest.py           # write
    python scripts/atlas/build_v1_freeze_manifest.py --check   # verify only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "releases" / "v1.0.0"
SHA_FILE = OUTPUT_DIR / "frozen_artifacts.sha256"
SCIENTIFIC_SHA_FILE = OUTPUT_DIR / "scientific_release.sha256"
WEB_SHA_FILE = OUTPUT_DIR / "web_delivery.sha256"
RECORD_FILE = OUTPUT_DIR / "release_record.json"

RELEASE_TAG = "v1.0.0"

# Post-release delivery artifacts derived from v1.0.0 (Explorer v1 + web v1).
DERIVED_DELIVERY_COMMIT = "da19599"
DERIVED_DELIVERY_PREFIXES = (
    "docs/explorer/",
    "results/explorer_v1/",
    "results/explorer_web_v1/",
    "scripts/explorer/",
)

# Files present in the tag that are repository infrastructure, not scientific
# release content. They may evolve on main. Everything else in the tag tree
# is frozen.
LIVING_PATHS = frozenset(
    {
        ".gitignore",
        "README.md",
        "CITATION.cff",
        "pyproject.toml",
    }
)
LIVING_PREFIXES = ("tests/",)


def git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True
    ).stdout


def resolve(ref: str) -> str:
    return git("rev-parse", f"{ref}^{{commit}}").decode().strip()


def tree_files(ref: str) -> list[str]:
    out = git("ls-tree", "-r", "--name-only", "-z", ref).decode()
    return sorted(p for p in out.split("\0") if p)


def blob_sha256(ref: str, path: str) -> str:
    return hashlib.sha256(git("show", f"{ref}:{path}")).hexdigest()


def is_living(path: str) -> bool:
    return path in LIVING_PATHS or path.startswith(LIVING_PREFIXES)


def collect() -> list[tuple[str, str, str]]:
    """Return sorted (path, sha256, lineage) triples."""
    entries: dict[str, tuple[str, str]] = {}
    tag_paths = set(tree_files(RELEASE_TAG))
    for path in tag_paths:
        if not is_living(path):
            entries[path] = (blob_sha256(RELEASE_TAG, path), "scientific_release")
    for path in tree_files(DERIVED_DELIVERY_COMMIT):
        if path.startswith(DERIVED_DELIVERY_PREFIXES):
            # Web-delivery files must be genuinely post-tag additions.
            if path in tag_paths:
                raise SystemExit(f"web-delivery path already existed at {RELEASE_TAG}: {path}")
            entries[path] = (blob_sha256(DERIVED_DELIVERY_COMMIT, path), "web_delivery")
    return sorted((p, s, lineage) for p, (s, lineage) in entries.items())


def introducing_commits() -> list[dict[str, str]]:
    out = git(
        "log", "--reverse", "--format=%H%x09%s", f"{RELEASE_TAG}..{DERIVED_DELIVERY_COMMIT}",
        "--", *DERIVED_DELIVERY_PREFIXES,
    ).decode()
    return [dict(zip(("commit", "subject"), line.split("\t", 1))) for line in out.splitlines()]


def sha_lines(entries: list[tuple[str, str, str]]) -> str:
    return "".join(f"{sha}  {path}\n" for path, sha, _ in entries)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def verify_working_tree(entries: list[tuple[str, str, str]]) -> list[str]:
    failures = []
    for path, expected, _ in entries:
        local = REPO_ROOT / path
        if not local.is_file():
            failures.append(f"MISSING {path}")
        elif hashlib.sha256(local.read_bytes()).hexdigest() != expected:
            failures.append(f"CHANGED {path}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed manifest and working tree without writing",
    )
    args = parser.parse_args()

    entries = collect()
    failures = verify_working_tree(entries)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        print("V1_FREEZE_VERIFICATION_FAIL", file=sys.stderr)
        return 1

    scientific = [e for e in entries if e[2] == "scientific_release"]
    web = [e for e in entries if e[2] == "web_delivery"]
    texts = {
        SHA_FILE: sha_lines(entries),
        SCIENTIFIC_SHA_FILE: sha_lines(scientific),
        WEB_SHA_FILE: sha_lines(web),
    }
    rel = lambda path: str(path.relative_to(REPO_ROOT))  # noqa: E731
    record = {
        "freeze_record_version": "2.0.0",
        "scientific_release": {
            "version": RELEASE_TAG,
            "git_tag": RELEASE_TAG,
            "source_commit": resolve(RELEASE_TAG),
            "registry_schema_version": "1.0.0",
            "zenodo_doi": "10.5281/zenodo.23085673",
            "authoritative_archive": {
                "path": "results/phase2e/omicsedge_phase2_final_results.tar.gz",
                "sha256": "186cbed74fa718a728f7a24b43d58118a308165fae385eb95cc4cb4444788ca3",
                "size_bytes": 8708768,
            },
            "present_at_git_tag": True,
            "file_count": len(scientific),
            "manifest": rel(SCIENTIFIC_SHA_FILE),
            "manifest_sha256": digest(texts[SCIENTIFIC_SHA_FILE]),
        },
        "web_delivery": {
            "source_commit": resolve(DERIVED_DELIVERY_COMMIT),
            "source_commit_short": DERIVED_DELIVERY_COMMIT,
            "role": "validated Evidence Explorer delivery for the frozen v1 scientific release",
            "derived_from": RELEASE_TAG,
            "present_at_git_tag": False,
            "alters_scientific_observations": False,
            "statement": (
                "Added after the v1.0.0 tag. These files are the validated Evidence "
                "Explorer canonical export and its static browser-delivery bundle. "
                "They re-represent the frozen v1.0.0 observations for the web and do "
                "not add, remove, recompute or alter any scientific observation."
            ),
            "introducing_commits": introducing_commits(),
            "path_prefixes": list(DERIVED_DELIVERY_PREFIXES),
            "file_count": len(web),
            "manifest": rel(WEB_SHA_FILE),
            "manifest_sha256": digest(texts[WEB_SHA_FILE]),
        },
        "combined_freeze": {
            "manifest": rel(SHA_FILE),
            "manifest_sha256": digest(texts[SHA_FILE]),
            "file_count": len(entries),
            "note": (
                "Union of the scientific_release and web_delivery lineages. It does "
                "not claim that all files existed at the v1.0.0 tag."
            ),
        },
        "living_paths_excluded": sorted(LIVING_PATHS) + list(LIVING_PREFIXES),
        "immutability_policy": "docs/atlas/v1_immutability_policy.md",
    }
    record_text = json.dumps(record, indent=2, sort_keys=True) + "\n"

    if args.check:
        ok = all(path.is_file() and path.read_text() == text for path, text in texts.items()) and (
            RECORD_FILE.is_file() and RECORD_FILE.read_text() == record_text
        )
        print("V1_FREEZE_VERIFICATION_PASS" if ok else "V1_FREEZE_MANIFEST_STALE")
        return 0 if ok else 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in texts.items():
        path.write_text(text)
    RECORD_FILE.write_text(record_text)
    print(f"wrote {len(entries)} frozen entries")
    print("V1_FREEZE_VERIFICATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
