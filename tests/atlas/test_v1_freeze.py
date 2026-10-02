"""The released v1.0.0 artifacts must never change, and their lineage is explicit."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from evidence_atlas import protocol

REPO = Path(__file__).resolve().parents[2]
RELEASE_DIR = REPO / "releases" / "v1.0.0"

V1_TAG_COMMIT = "c61b84335a8cdce0e27fedc146da263f3b10a7fd"
WEB_DELIVERY_COMMIT = "da195997c5fc14d7b11f55550a9650a4ab568811"


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(protocol.V1_RELEASE_RECORD.read_text())


@pytest.fixture(scope="module")
def combined() -> dict[str, str]:
    return protocol.read_sha256_manifest(protocol.V1_FREEZE_MANIFEST)


@pytest.fixture(scope="module")
def scientific(record) -> dict[str, str]:
    return protocol.read_sha256_manifest(REPO / record["scientific_release"]["manifest"])


@pytest.fixture(scope="module")
def web(record) -> dict[str, str]:
    return protocol.read_sha256_manifest(REPO / record["web_delivery"]["manifest"])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_no_frozen_v1_artifact_is_missing_or_changed() -> None:
    assert protocol.v1_freeze_violations() == []


# ----------------------------------------------------------------- lineage


def test_scientific_release_lineage_is_the_v1_tag(record, scientific) -> None:
    sci = record["scientific_release"]
    assert sci["version"] == "v1.0.0"
    assert sci["git_tag"] == "v1.0.0"
    assert sci["source_commit"] == V1_TAG_COMMIT
    assert sci["present_at_git_tag"] is True
    assert sci["zenodo_doi"] == "10.5281/zenodo.23085673"
    assert sci["file_count"] == len(scientific) == 197
    assert sci["manifest_sha256"] == _sha(REPO / sci["manifest"])


def test_web_delivery_lineage_is_post_tag_and_non_scientific(record, web) -> None:
    delivery = record["web_delivery"]
    assert delivery["source_commit"] == WEB_DELIVERY_COMMIT
    assert delivery["source_commit_short"] == "da19599"
    assert delivery["role"] == "validated Evidence Explorer delivery for the frozen v1 scientific release"
    assert delivery["derived_from"] == "v1.0.0"
    assert delivery["present_at_git_tag"] is False
    assert delivery["alters_scientific_observations"] is False
    assert delivery["introducing_commits"][-1]["commit"] == WEB_DELIVERY_COMMIT
    assert delivery["file_count"] == len(web) == 270
    assert delivery["manifest_sha256"] == _sha(REPO / delivery["manifest"])
    assert all(p.startswith(tuple(delivery["path_prefixes"])) for p in web)


def test_lineages_are_disjoint_and_union_to_the_combined_freeze(record, combined, scientific, web) -> None:
    assert not set(scientific) & set(web)
    assert {**scientific, **web} == combined
    freeze = record["combined_freeze"]
    assert freeze["file_count"] == len(combined) == 467
    assert freeze["manifest_sha256"] == _sha(protocol.V1_FREEZE_MANIFEST)
    assert "does not claim that all files existed" in freeze["note"]


def test_combined_freeze_checksums_are_unchanged_since_m0_draft() -> None:
    # The 467 per-file digests are pinned by the hash of the combined manifest
    # first generated in the M0 draft; restructuring lineage must not move it.
    assert _sha(protocol.V1_FREEZE_MANIFEST) == "e685d5572582d832b40b4d908960f4c03537692114062cfad06729cb130193bc"


def test_no_web_delivery_file_in_scientific_release(scientific, record) -> None:
    prefixes = tuple(record["web_delivery"]["path_prefixes"])
    assert not any(p.startswith(prefixes) for p in scientific)


def _git_tree(ref: str) -> set[str] | None:
    try:
        out = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref], cwd=REPO,
                             check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return set(out.splitlines())


def test_lineage_matches_git_history(scientific, web) -> None:
    tag_tree = _git_tree(V1_TAG_COMMIT)
    web_tree = _git_tree(WEB_DELIVERY_COMMIT)
    if tag_tree is None or web_tree is None:
        pytest.skip("release commits not available in this checkout (e.g. shallow clone)")
    assert set(scientific) <= tag_tree, "scientific-release files must exist at the v1.0.0 tag"
    assert not set(web) & tag_tree, "web-delivery files must not exist at the v1.0.0 tag"
    assert set(web) <= web_tree


# -------------------------------------------------------- archive / scope


def test_authoritative_archive_is_frozen_with_documented_digest(scientific, record) -> None:
    archive = record["scientific_release"]["authoritative_archive"]
    assert scientific[archive["path"]] == archive["sha256"]
    assert archive["sha256"] == "186cbed74fa718a728f7a24b43d58118a308165fae385eb95cc4cb4444788ca3"
    assert (REPO / archive["path"]).stat().st_size == archive["size_bytes"]


@pytest.mark.parametrize(
    ("path", "lineage"),
    [
        ("docs/phase2/phase2_final_release.lock", "scientific"),
        ("docs/phase2/phase2_protocol.lock", "scientific"),
        ("data/phase2/interval_panel.lock", "scientific"),
        ("schemas/experiment.schema.json", "scientific"),
        ("src/benchmark_evidence/validation.py", "scientific"),
        ("results/explorer_v1/explorer_manifest.json", "web"),
        ("results/explorer_web_v1/manifest.json", "web"),
    ],
)
def test_key_v1_artifacts_are_in_the_right_lineage(scientific, web, path, lineage) -> None:
    assert path in (scientific if lineage == "scientific" else web)


def test_living_files_are_not_frozen(combined) -> None:
    for path in ("README.md", "CITATION.cff", "pyproject.toml", ".gitignore"):
        assert path not in combined
    assert not any(p.startswith(("tests/", "config/atlas/", "schemas/atlas/", "docs/atlas/")) for p in combined)


def test_freeze_check_detects_tampering(tmp_path) -> None:
    rel_manifest = protocol.V1_FREEZE_MANIFEST.relative_to(protocol.REPO_ROOT)
    (tmp_path / rel_manifest).parent.mkdir(parents=True)
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("alpha")
    b.write_text("beta")
    (tmp_path / rel_manifest).write_text(
        "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in (a, b))
    )
    assert protocol.v1_freeze_violations(tmp_path) == []
    a.write_text("alpha!")
    b.unlink()
    assert protocol.v1_freeze_violations(tmp_path) == ["CHANGED a.txt", "MISSING b.txt"]
