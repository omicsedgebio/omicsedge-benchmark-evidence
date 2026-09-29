#!/usr/bin/env python3
"""
OmicsEdgeBio Project 003 — Phase 2C GitHub Actions compute runner.

This runner executes the frozen Phase 2C benchmark expansion on a
GitHub-hosted Linux Actions runner using Docker for the exact pinned hap.py
OCI comparator. It expects the workflow to materialize the frozen Project 003
configuration under OMICSEDGE_PHASE2C_CONFIG_DIR.

Large genomic inputs remain in ephemeral runner storage and are excluded from
the compact result archive.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path

UTC = dt.timezone.utc

DEFAULT_RUNTIME_ROOT = Path(
    os.environ.get("RUNNER_TEMP", "/tmp")
)

WORK_ROOT = Path(
    os.environ.get(
        "OMICSEDGE_PHASE2C_WORK_ROOT",
        str(DEFAULT_RUNTIME_ROOT / "omicsedge_phase2c"),
    )
)
SOURCE_DIR = WORK_ROOT / "source"
STAGED_DIR = WORK_ROOT / "staged"
TOOLS_DIR = WORK_ROOT / "tools"
RUNS_DIR = WORK_ROOT / "runs"
CONFIG_DIR = Path(
    os.environ.get(
        "OMICSEDGE_PHASE2C_CONFIG_DIR",
        str(WORK_ROOT / "authoritative_config"),
    )
)

RESULTS_DIR = Path(
    os.environ.get(
        "OMICSEDGE_PHASE2C_RESULTS_DIR",
        str(DEFAULT_RUNTIME_ROOT / "omicsedge_phase2c_results"),
    )
)
ARCHIVE_PATH = Path(
    os.environ.get(
        "OMICSEDGE_PHASE2C_ARCHIVE",
        str(DEFAULT_RUNTIME_ROOT / "omicsedge_phase2c_results.tar.gz"),
    )
)

for directory in (
    SOURCE_DIR,
    STAGED_DIR,
    TOOLS_DIR,
    RUNS_DIR,
    CONFIG_DIR,
    RESULTS_DIR,
):
    directory.mkdir(parents=True, exist_ok=True)

COMMAND_LOG = RESULTS_DIR / "commands.log"
COMMAND_LOG.write_text("", encoding="utf-8")

STATUS_EMITTED = False
PIPELINE_ABORTED = False
PIPELINE_ABORT_STAGE = None

runtime_identity: dict = {}
retrieval_rows: list[dict] = []
artifact_records: dict[str, dict] = {}
provenance_links: list[dict] = []
provenance_ids: set[str] = set()
derived_paths: dict[str, Path] = {}
runs_state: dict[str, dict] = {}


class Phase2CAbort(RuntimeError):
    pass


def now_iso() -> str:
    return (
        dt.datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256_file(path: Path | str, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def md5_file(path: Path | str, chunk: int = 8 * 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def tree_sha256(path: Path | str) -> str:
    root = Path(path)
    h = hashlib.sha256()
    for item in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(str(item.relative_to(root)).encode())
        h.update(b"\0")
        h.update(sha256_file(item).encode())
        h.update(b"\n")
    return h.hexdigest()


def stable_id(prefix: str, payload: dict) -> str:
    blob = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"{prefix}-{hashlib.sha256(blob).hexdigest()[:32]}"


def emit_status_once(status: str) -> None:
    global STATUS_EMITTED
    allowed = {
        "PHASE2C_COMPUTE_PASS",
        "PHASE2C_COMPUTE_FAIL",
        "COMPARATOR_ENVIRONMENT_BLOCKED",
    }
    if status not in allowed:
        raise ValueError(status)
    if not STATUS_EMITTED:
        print(status)
        STATUS_EMITTED = True


def append_command(argv, cwd=None) -> None:
    with COMMAND_LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "captured_at": now_iso(),
                    "cwd": str(cwd or Path.cwd()),
                    "argv": [str(x) for x in argv],
                },
                sort_keys=True,
            )
            + "\n"
        )


def run(argv, *, cwd=None, check=True, capture=True, env=None):
    argv = [str(x) for x in argv]
    append_command(argv, cwd)
    cp = subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and cp.returncode:
        raise RuntimeError(
            f"command failed ({cp.returncode}): {shlex.join(argv)}\n"
            f"stdout:\n{(cp.stdout or '')[-4000:]}\n"
            f"stderr:\n{(cp.stderr or '')[-4000:]}"
        )
    return cp


def run_to_file(argv, destination, *, env=None):
    argv = [str(x) for x in argv]
    destination = Path(destination)
    append_command(argv)
    with destination.open("w", encoding="utf-8") as out:
        cp = subprocess.run(
            argv,
            stdout=out,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    if cp.returncode:
        raise RuntimeError(
            f"command failed ({cp.returncode}): {shlex.join(argv)}\n"
            f"stderr:\n{(cp.stderr or '')[-4000:]}"
        )
    return cp


def write_tsv(path, rows, fieldnames=None) -> None:
    path = Path(path)
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def read_tsv(path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def parse_kv_lock(path) -> dict[str, str]:
    values = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            values[key] = value
    return values


def media_type_for(name: str) -> str:
    mappings = [
        (".vcf.gz", "application/gzip"),
        (".tbi", "application/octet-stream"),
        (".bed", "text/tab-separated-values"),
        (".fasta.gz", "application/gzip"),
        (".fasta", "text/plain"),
        (".fai", "text/plain"),
        (".gzi", "application/octet-stream"),
        (".parquet", "application/vnd.apache.parquet"),
        (".tsv", "text/tab-separated-values"),
        (".json", "application/json"),
        (".yaml", "text/yaml"),
        (".md", "text/markdown"),
        (".zip", "application/zip"),
        (".log", "text/plain"),
    ]
    for suffix, mime in mappings:
        if name.endswith(suffix):
            return mime
    return "application/octet-stream"


def register_artifact(record: dict) -> dict:
    artifact_id = record["source_artifact_id"]
    previous = artifact_records.get(artifact_id)
    if previous is not None:
        if previous != record:
            raise RuntimeError(f"Conflicting artifact record: {artifact_id}")
        return previous
    artifact_records[artifact_id] = record
    return record


def make_source_artifact(
    artifact_id,
    name,
    role,
    uri,
    version,
    *,
    path=None,
    checksums=None,
    checksum_status="COMPUTED_NOT_YET_VERIFIED",
    reuse_basis="Public research artifact",
    notes=None,
):
    checksums = list(checksums or [])
    if path is not None:
        path = Path(path)
        if not any(c["algorithm"] == "sha256" for c in checksums):
            checksums.append(
                {
                    "algorithm": "sha256",
                    "value": sha256_file(path),
                    "source": "COMPUTED_ON_RETRIEVAL",
                }
            )

    record = {
        "schema_version": "1.0.0",
        "source_artifact_id": artifact_id,
        "artifact_name": name,
        "artifact_role": role,
        "uri": uri,
        "media_type": media_type_for(name),
        "byte_size": path.stat().st_size if path is not None else None,
        "version": version,
        "checksums": checksums,
        "checksum_status": checksum_status,
        "retrieval_status": "DOWNLOADED" if path is not None else "NOT_DOWNLOADED",
        "retrieved_at": now_iso() if path is not None else None,
        "license_expression": "UNKNOWN",
        "reuse_basis": reuse_basis,
        "derivation_state": "SOURCE",
        "publisher_last_modified": None,
        "notes": notes,
    }
    return register_artifact(record)


def make_derived_artifact(artifact_id, path, role, version, notes):
    path = Path(path)
    record = {
        "schema_version": "1.0.0",
        "source_artifact_id": artifact_id,
        "artifact_name": path.name,
        "artifact_role": role,
        "uri": "file://" + str(path),
        "media_type": media_type_for(path.name),
        "byte_size": path.stat().st_size,
        "version": version,
        "checksums": [
            {
                "algorithm": "sha256",
                "value": sha256_file(path),
                "source": "COMPUTED_ON_RETRIEVAL",
            }
        ],
        "checksum_status": "COMPUTED_NOT_YET_VERIFIED",
        "retrieval_status": "GENERATED",
        "retrieved_at": now_iso(),
        "license_expression": "UNKNOWN",
        "reuse_basis": "Project 003 Phase 2C derived evidence",
        "derivation_state": "GENERATED",
        "publisher_last_modified": None,
        "notes": notes,
    }
    register_artifact(record)
    derived_paths[artifact_id] = path
    return record


def add_link(
    source_type,
    source_id,
    target_type,
    target_id,
    relation,
    transformation,
    software=None,
    version=None,
    parameters=None,
    notes=None,
):
    parameters = parameters or {}
    identity = {
        "source_entity_type": source_type,
        "source_entity_id": source_id,
        "target_entity_type": target_type,
        "target_entity_id": target_id,
        "relation": relation,
        "transformation": transformation,
        "software_name": software,
        "software_version": version,
        "parameters": parameters,
    }
    link_id = stable_id("prov", identity)
    if link_id in provenance_ids:
        return
    provenance_ids.add(link_id)
    provenance_links.append(
        {
            "schema_version": "1.0.0",
            "provenance_link_id": link_id,
            **identity,
            "asserted_at": now_iso(),
            "asserted_by": "project003_phase2c_actions",
            "notes": notes,
        }
    )


@contextmanager
def stage_guard(stage, *, blocked=False):
    global PIPELINE_ABORTED, PIPELINE_ABORT_STAGE
    if PIPELINE_ABORTED:
        raise Phase2CAbort(
            f"Pipeline already stopped at {PIPELINE_ABORT_STAGE}"
        )
    try:
        yield
    except Phase2CAbort:
        raise
    except Exception as exc:
        PIPELINE_ABORTED = True
        PIPELINE_ABORT_STAGE = stage
        status = (
            "COMPARATOR_ENVIRONMENT_BLOCKED"
            if blocked
            else "PHASE2C_COMPUTE_FAIL"
        )
        diagnostic = {
            "status": status,
            "stage": stage,
            "captured_at": now_iso(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "runtime_identity": runtime_identity,
        }
        (
            RESULTS_DIR / "blocked_or_failed_diagnostics.json"
        ).write_text(
            json.dumps(diagnostic, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        emit_status_once(status)
        raise Phase2CAbort(f"{status}: {stage}: {exc}") from None


def refresh_checksums() -> None:
    checksum_path = RESULTS_DIR / "checksums.sha256"
    lines = []
    for path in sorted(RESULTS_DIR.rglob("*")):
        if path.is_file() and path != checksum_path:
            lines.append(
                f"{sha256_file(path)}  {path.relative_to(RESULTS_DIR)}"
            )
    checksum_path.write_text(
        "\n".join(lines) + ("\n" if lines else ""),
        encoding="utf-8",
    )


def package_archive() -> str | None:
    try:
        tar_argv = [
            "tar",
            "-C",
            str(RESULTS_DIR.parent),
            "-czf",
            str(ARCHIVE_PATH),
            RESULTS_DIR.name,
        ]
        append_command(tar_argv)
        refresh_checksums()

        if ARCHIVE_PATH.exists():
            ARCHIVE_PATH.unlink()

        cp = subprocess.run(
            tar_argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if cp.returncode:
            print(
                f"PARTIAL_PACKAGE_ERROR: {cp.stderr.strip()}",
                file=sys.stderr,
            )
            return None

        digest = sha256_file(ARCHIVE_PATH)
        print(f"archive path: {ARCHIVE_PATH}")
        print(f"archive size: {ARCHIVE_PATH.stat().st_size}")
        print(f"archive SHA-256: {digest}")
        return digest
    except Exception as exc:
        print(
            f"PARTIAL_PACKAGE_ERROR: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None


def require_config_paths() -> dict[str, Path]:
    paths = {
        "comparator_lock": CONFIG_DIR / "environment/comparator-lock.yaml",
        "admitted": CONFIG_DIR / "data/phase2/admitted_sources.tsv",
        "panel": CONFIG_DIR / "data/phase2/selected_assessable_segments.bed",
        "selected_intervals": CONFIG_DIR / "data/phase2/selected_intervals.tsv",
        "panel_lock": CONFIG_DIR / "data/phase2/interval_panel.lock",
        "phase2_protocol": CONFIG_DIR / "docs/phase2/phase2_protocol.md",
        "compute_protocol": CONFIG_DIR / "docs/phase2/phase2c_compute_protocol.md",
        "compute_lock": CONFIG_DIR / "docs/phase2/phase2c_compute_protocol.lock",
        "run_schema_lock": CONFIG_DIR / "docs/phase2/benchmark_run_schema_extension.lock",
        "submission_metadata": CONFIG_DIR / "data/manifests/selected_experiments.tsv",
        "event_schema": CONFIG_DIR / "schemas/event.schema.json",
        "observation_schema": CONFIG_DIR / "schemas/observation.schema.json",
        "experiment_schema": CONFIG_DIR / "schemas/experiment.schema.json",
        "source_artifact_schema": CONFIG_DIR / "schemas/source_artifact.schema.json",
        "provenance_schema": CONFIG_DIR / "schemas/provenance_link.schema.json",
        "run_schema": CONFIG_DIR / "schemas/phase2/benchmark_run.schema.json",
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise RuntimeError(
            "Required embedded configuration is missing:\n"
            + "\n".join(missing)
        )
    return paths


def install_runtime(paths):
    with stage_guard("comparator/runtime installation", blocked=True):
        run(["sudo", "apt-get", "update"], capture=False)
        run(
            [
                "sudo",
                "apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "bcftools",
                "samtools",
                "tabix",
                "bedtools",
                "unzip",
                "curl",
                "time",
            ],
            capture=False,
        )
        python_site = TOOLS_DIR / "python-site"
        python_site.mkdir(parents=True, exist_ok=True)

        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "--target",
                str(python_site),
                "duckdb==1.5.6",
                "pyarrow==25.0.1",
                "pysam==0.23.3",
                "jsonschema==4.26.0",
                "PyYAML==6.0.3",
            ],
            capture=False,
        )

        sys.path.insert(0, str(python_site))

        import duckdb
        import jsonschema
        import pyarrow
        import pysam
        import yaml

        runtime_identity["python_dependency_import_gate"] = {
            "duckdb": getattr(duckdb, "__version__", "UNKNOWN"),
            "pyarrow": getattr(pyarrow, "__version__", "UNKNOWN"),
            "pysam": getattr(pysam, "__version__", "UNKNOWN"),
            "jsonschema": getattr(jsonschema, "__version__", "UNKNOWN"),
            "PyYAML": getattr(yaml, "__version__", "UNKNOWN"),
        }

        comparator_lock = yaml.safe_load(
            paths["comparator_lock"].read_text(encoding="utf-8")
        )

        if comparator_lock["hap_py"]["version"] != "0.3.15":
            raise RuntimeError("hap.py version lock changed")
        if comparator_lock["rtg_tools"]["version"] != "3.12.1":
            raise RuntimeError("RTG version lock changed")
        if comparator_lock["comparison"]["engine"] != "vcfeval":
            raise RuntimeError("Comparator engine changed")
        if comparator_lock["comparison"]["threads"] != 2:
            raise RuntimeError("Comparator thread lock changed")

        expected_digest = comparator_lock["hap_py"]["container"][
            "manifest_digest"
        ]
        image_reference = comparator_lock["hap_py"]["container"]["reference"]

        if not image_reference.endswith("@" + expected_digest):
            raise RuntimeError(
                "Frozen hap.py image reference does not end in the locked digest"
            )

        run(["docker", "pull", image_reference], capture=False)

        repo_digest_text = run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{join .RepoDigests \"\\n\"}}",
                image_reference,
            ]
        ).stdout.strip()

        observed_digests = set(
            re.findall(r"sha256:[0-9a-f]{64}", repo_digest_text)
        )
        if expected_digest not in observed_digests:
            raise RuntimeError(
                "Docker image digest mismatch: "
                f"{sorted(observed_digests)} does not contain {expected_digest}"
            )

        observed_platform = run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{.Os}}/{{.Architecture}}",
                image_reference,
            ]
        ).stdout.strip()

        if observed_platform != "linux/amd64":
            raise RuntimeError(
                f"Comparator image platform mismatch: {observed_platform}"
            )

        rtg_url = comparator_lock["rtg_tools"]["linux_x64_archive_url"]
        rtg_expected_sha = comparator_lock["rtg_tools"][
            "linux_x64_archive_sha256"
        ]
        rtg_zip = TOOLS_DIR / "rtg-tools-3.12.1-linux-x64.zip"

        if not rtg_zip.exists():
            run(
                [
                    "curl",
                    "-L",
                    "--fail",
                    "--retry",
                    "5",
                    "--retry-delay",
                    "2",
                    "-o",
                    str(rtg_zip),
                    rtg_url,
                ]
            )

        if sha256_file(rtg_zip) != rtg_expected_sha:
            raise RuntimeError("RTG archive SHA-256 mismatch")

        run(
            [
                "unzip",
                "-q",
                "-o",
                str(rtg_zip),
                "-d",
                str(TOOLS_DIR),
            ]
        )

        rtg_dir = TOOLS_DIR / "rtg-tools-3.12.1"
        rtg_exe = rtg_dir / "rtg"
        if not rtg_exe.exists():
            raise RuntimeError("RTG executable missing")

        container_env = dict(os.environ)
        mount_root = WORK_ROOT.parent.resolve()

        def container_argv(inner):
            return [
                "docker",
                "run",
                "--rm",
                "--volume",
                f"{mount_root}:{mount_root}",
                "--volume",
                f"{rtg_dir}:/opt/rtg-tools-3.12.1:ro",
                image_reference,
                *[str(x) for x in inner],
            ]

        help_cp = run(
            container_argv(["hap.py", "--help"]),
            check=False,
            env=container_env,
        )
        if help_cp.returncode != 0:
            raise RuntimeError("hap.py executable sanity probe failed")

        version_cp = run(
            container_argv(["hap.py", "--version"]),
            check=False,
            env=container_env,
        )
        version_text = (
            (version_cp.stdout or "")
            + "\n"
            + (version_cp.stderr or "")
        ).strip()
        observed_versions = set(
            re.findall(
                r"(?<![0-9.])(\d+\.\d+\.\d+)(?![0-9.])",
                version_text,
            )
        )
        conflicting = sorted(
            version
            for version in observed_versions
            if version != "0.3.15"
        )
        if conflicting:
            raise RuntimeError(
                f"Runtime hap.py version conflict: {conflicting}"
            )

        rtg_cp = run(
            [str(rtg_exe), "version"],
            check=False,
        )
        rtg_version_text = (
            (rtg_cp.stdout or "")
            + "\n"
            + (rtg_cp.stderr or "")
        ).strip()
        if "3.12.1" not in rtg_version_text:
            raise RuntimeError(
                f"RTG runtime version mismatch: {rtg_version_text}"
            )

        def first_line(argv):
            cp = run(argv, check=False)
            output = (
                (cp.stdout or "")
                + "\n"
                + (cp.stderr or "")
            ).strip()
            return output.splitlines()[0] if output else "UNKNOWN"

        try:
            ram_bytes = (
                os.sysconf("SC_PAGE_SIZE")
                * os.sysconf("SC_PHYS_PAGES")
            )
        except (ValueError, OSError, AttributeError):
            ram_bytes = 0

        free_disk_bytes = shutil.disk_usage(WORK_ROOT).free
        docker_version_text = first_line(["docker", "--version"])

        runtime_identity.update(
            {
                "captured_at": now_iso(),
                "architecture": platform.machine(),
                "logical_cpus": os.cpu_count() or 0,
                "ram_bytes": ram_bytes,
                "free_disk_bytes": free_disk_bytes,
                "python_version": sys.version,
                "github_sha": os.environ.get("GITHUB_SHA"),
                "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
                "runner_os": os.environ.get("RUNNER_OS"),
                "runner_arch": os.environ.get("RUNNER_ARCH"),
                "hap_py_expected_version": "0.3.15",
                "hap_py_version_probe": version_text,
                "hap_py_identity_mode": (
                    "IN_CONTAINER_VERSION_EVIDENCE_PLUS_IMMUTABLE_DIGEST"
                    if "0.3.15" in observed_versions
                    else "IMMUTABLE_OCI_DIGEST_PLUS_BIOCONDA_BUILD_TAG_AND_EXECUTABLE_PROBE"
                ),
                "hap_py_container_digest": expected_digest,
                "docker_repo_digests": sorted(observed_digests),
                "docker_version": docker_version_text,
                "rtg_version_output": rtg_version_text,
                "java_version": first_line(["java", "-version"]),
                "bcftools_version": first_line(["bcftools", "--version"]),
                "samtools_version": first_line(["samtools", "--version"]),
                "bedtools_version": first_line(["bedtools", "--version"]),
            }
        )

        (
            RESULTS_DIR / "runtime_identity.json"
        ).write_text(
            json.dumps(runtime_identity, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        make_source_artifact(
            "artifact-happy-container",
            "hap.py BioContainer",
            "SOFTWARE_IMAGE",
            image_reference,
            "hap.py 0.3.15",
            checksums=[
                {
                    "algorithm": "oci-manifest-digest",
                    "value": expected_digest.removeprefix("sha256:"),
                    "source": "REGISTRY",
                }
            ],
            checksum_status="PUBLISHER_VERIFIED",
            reuse_basis=(
                "BSD-2-Clause for hap.py; bundled components retain licenses"
            ),
            notes=(
                "Immutable OCI manifest digest pinned in the frozen comparator "
                "lock and verified from Docker RepoDigests after pull."
            ),
        )
        image_record = artifact_records["artifact-happy-container"]
        image_record["retrieval_status"] = "DOWNLOADED"
        image_record["retrieved_at"] = now_iso()

        make_source_artifact(
            "artifact-rtg-tools-3121",
            rtg_zip.name,
            "SOFTWARE_ARCHIVE",
            rtg_url,
            "RTG Tools 3.12.1",
            path=rtg_zip,
            checksums=[
                {
                    "algorithm": "sha256",
                    "value": rtg_expected_sha,
                    "source": "COMPUTED_ON_RETRIEVAL",
                }
            ],
            reuse_basis="BSD-2-Clause",
            notes="Pinned RTG Tools release archive.",
        )

        return {
            "comparator_lock": comparator_lock,
            "rtg_exe": rtg_exe,
            "rtg_dir": rtg_dir,
            "container_env": container_env,
            "container_argv": container_argv,
        }


def validate_frozen_configuration(paths):
    compute_lock = parse_kv_lock(paths["compute_lock"])
    run_schema_lock = parse_kv_lock(paths["run_schema_lock"])

    if (
        sha256_file(paths["compute_protocol"])
        != compute_lock["protocol_sha256"]
    ):
        raise RuntimeError("Phase 2C protocol lock mismatch")

    if (
        sha256_file(paths["panel"])
        != compute_lock["selected_assessable_segments_sha256"]
    ):
        raise RuntimeError("Frozen Phase 2 panel checksum mismatch")

    if (
        sha256_file(paths["run_schema"])
        != run_schema_lock["schema_sha256"]
    ):
        raise RuntimeError("Phase 2 BENCHMARK_RUN schema lock mismatch")

    admitted_rows = read_tsv(paths["admitted"])
    if len(admitted_rows) != 4:
        raise RuntimeError(
            f"Expected four admitted Phase 2 sources, found {len(admitted_rows)}"
        )

    expected_candidates = {
        "phase2-hg003-60z59",
        "phase2-hg003-ru88n",
        "phase2-hg004-60z59",
        "phase2-hg004-ru88n",
    }
    if {row["candidate_id"] for row in admitted_rows} != expected_candidates:
        raise RuntimeError("Admitted Phase 2 candidate set changed")

    for row in admitted_rows:
        if row["performance_consulted_for_selection"].lower() != "false":
            raise RuntimeError(
                "Outcome-independent source selection invariant violated"
            )
        if row["phase2a_admission_state"] != "ELIGIBLE":
            raise RuntimeError(
                f"Non-eligible source present: {row['candidate_id']}"
            )
        if row["reference_assembly"] != "GRCh38":
            raise RuntimeError(
                f"Unexpected assembly for {row['candidate_id']}"
            )

    panel_rows = []
    for raw in paths["panel"].read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        fields = raw.split("\t")
        panel_rows.append(
            (fields[0], int(fields[1]), int(fields[2]))
        )

    if len(panel_rows) != 541:
        raise RuntimeError(
            f"Expected 541 panel segments, found {len(panel_rows)}"
        )

    panel_bases = sum(
        end - start for _, start, end in panel_rows
    )
    if panel_bases != 1162571:
        raise RuntimeError(
            f"Expected 1162571 assessable bases, found {panel_bases}"
        )

    def chrom_sort_key(chrom):
        suffix = chrom.removeprefix("chr")
        return (
            int(suffix) if suffix.isdigit() else 1000,
            chrom,
        )

    panel_chromosomes = sorted(
        {row[0] for row in panel_rows},
        key=chrom_sort_key,
    )
    if len(panel_chromosomes) != 19:
        raise RuntimeError(
            f"Expected 19 panel chromosomes, found {len(panel_chromosomes)}"
        )
    if "chr20" in panel_chromosomes:
        raise RuntimeError("chr20 is forbidden in Phase 2C")

    selected_rows = read_tsv(paths["selected_intervals"])
    if len(selected_rows) != 50:
        raise RuntimeError(
            f"Expected 50 selected windows, found {len(selected_rows)}"
        )

    panel_lock = parse_kv_lock(paths["panel_lock"])
    if (
        panel_lock.get("status")
        != "FROZEN_BEFORE_QUERY_VCF_DOWNLOAD_AND_BENCHMARKING"
    ):
        raise RuntimeError("Unexpected Phase 2 panel lock status")
    if panel_lock.get("query_vcfs_consulted") != "False":
        raise RuntimeError(
            "Frozen panel source-isolation invariant changed"
        )
    if panel_lock.get("benchmark_outcomes_consulted") != "False":
        raise RuntimeError(
            "Frozen panel outcome-isolation invariant changed"
        )

    submission_rows = read_tsv(paths["submission_metadata"])
    submission_metadata = {
        row["source_submission_id"]: row
        for row in submission_rows
    }
    if set(submission_metadata) != {"60Z59", "RU88N"}:
        raise RuntimeError(
            "Submission-method metadata does not contain 60Z59/RU88N"
        )

    runs = {}
    for row in admitted_rows:
        sample = row["sample_id"]
        submission = row["source_submission_id"]
        key = row["candidate_id"]
        runs[key] = {
            **row,
            "key": key,
            "experiment_id": (
                f"exp-pfda-v2-{submission.lower()}-{sample.lower()}"
            ),
            "run_id": (
                f"run-phase2c-{sample.lower()}-"
                f"{submission.lower()}-grch38-v421"
            ),
            "query_artifact_id": (
                f"artifact-query-{submission.lower()}-{sample.lower()}"
            ),
            "truth_artifact_id": (
                f"artifact-truth-{sample.lower()}-grch38-v421"
            ),
            "truth_index_artifact_id": (
                f"artifact-truth-{sample.lower()}-grch38-v421-tbi"
            ),
            "benchmark_bed_artifact_id": (
                f"artifact-bed-{sample.lower()}-grch38-v421"
            ),
        }

    return {
        "compute_lock": compute_lock,
        "run_schema_lock": run_schema_lock,
        "admitted_rows": admitted_rows,
        "panel_rows": panel_rows,
        "panel_bases": panel_bases,
        "panel_chromosomes": panel_chromosomes,
        "selected_rows": selected_rows,
        "submission_metadata": submission_metadata,
        "runs": runs,
        "run_keys": sorted(runs),
    }


def register_embedded_artifacts(paths):
    items = [
        (
            "artifact-phase2-admitted-sources",
            paths["admitted"],
            "EXPERIMENT_METADATA",
            "Phase 2A frozen admission",
            "Outcome-independent Phase 2 source admission.",
        ),
        (
            "artifact-phase2-frozen-panel",
            paths["panel"],
            "BENCHMARK_BED",
            "Phase 2B frozen panel",
            "Exact multi-context Phase 2 benchmark domain.",
        ),
        (
            "artifact-phase2-selected-intervals",
            paths["selected_intervals"],
            "DATASET_MANIFEST",
            "Phase 2B frozen selection",
            "Fifty selected Phase 2 windows.",
        ),
        (
            "artifact-phase2-compute-protocol",
            paths["compute_protocol"],
            "OTHER",
            "Phase 2C frozen protocol",
            "Frozen before Phase 2 query retrieval.",
        ),
        (
            "artifact-phase2-run-schema",
            paths["run_schema"],
            "OTHER",
            "BENCHMARK_RUN schema 2.0.0",
            "Multi-region benchmark-run schema.",
        ),
        (
            "artifact-submission-method-template",
            paths["submission_metadata"],
            "EXPERIMENT_METADATA",
            "precisionFDA V2 submission methods",
            (
                "Submission-level pipeline metadata reused for the "
                "same 60Z59 and RU88N challenge submissions."
            ),
        ),
    ]

    for artifact_id, path, role, version, notes in items:
        make_source_artifact(
            artifact_id,
            path.name,
            role,
            "repository://" + str(path.relative_to(CONFIG_DIR)),
            version,
            path=path,
            checksum_status="COMPUTED_NOT_YET_VERIFIED",
            reuse_basis="Frozen Project 003 repository artifact",
            notes=notes,
        )


def source_specs(frozen):
    runs = frozen["runs"]

    reference_base = (
        "https://ftp-trace.ncbi.nlm.nih.gov/"
        "ReferenceSamples/giab/release/references/GRCh38/"
    )
    reference_name = (
        "GCA_000001405.15_GRCh38_no_alt_analysis_set.fasta.gz"
    )

    specs = {}

    for key in frozen["run_keys"]:
        row = runs[key]
        specs[row["query_artifact_id"]] = {
            "artifact_id": row["query_artifact_id"],
            "name": (
                f"{row['source_submission_id']}_{row['sample_id']}.vcf.gz"
            ),
            "role": "QUERY_VCF",
            "url": row["query_vcf_url"],
            "version": "precisionFDA Truth Challenge V2 NIST deposit",
            "expected_sha256": row["expected_query_sha256"],
            "expected_md5": None,
            "reuse_basis": "CC0 plus NIST Data Use Policy",
            "notes": (
                "Whole public query artifact; source bytes remain immutable."
            ),
        }

    expected_bed_sha = {
        "HG003": (
            "652afd3046705af3200f9c87c255fef11bb212dd76c75a19999c9b2df8a3180c"
        ),
        "HG004": (
            "88d1c926fdc8abd9c39b3e9fe2af3fc43dd67d284690a3dc6127b369d96bccad"
        ),
    }

    for sample in ("HG003", "HG004"):
        row = next(
            value
            for value in runs.values()
            if value["sample_id"] == sample
        )
        truth_id = row["truth_artifact_id"]
        truth_index_id = row["truth_index_artifact_id"]
        bed_id = row["benchmark_bed_artifact_id"]
        truth_url = row["truth_vcf_url"]
        bed_url = row["benchmark_bed_url"]

        specs[truth_id] = {
            "artifact_id": truth_id,
            "name": f"{sample}_GRCh38_1_22_v4.2.1_benchmark.vcf.gz",
            "role": "TRUTH_VCF",
            "url": truth_url,
            "version": f"GIAB {sample} v4.2.1",
            "expected_sha256": None,
            "expected_md5": None,
            "reuse_basis": "NIST open terms",
            "notes": "GIAB v4.2.1 benchmark truth.",
        }

        specs[truth_index_id] = {
            "artifact_id": truth_index_id,
            "name": f"{sample}_GRCh38_1_22_v4.2.1_benchmark.vcf.gz.tbi",
            "role": "TRUTH_INDEX",
            "url": truth_url + ".tbi",
            "version": f"GIAB {sample} v4.2.1",
            "expected_sha256": None,
            "expected_md5": None,
            "reuse_basis": "NIST open terms",
            "notes": "GIAB v4.2.1 truth tabix index.",
        }

        specs[bed_id] = {
            "artifact_id": bed_id,
            "name": (
                f"{sample}_GRCh38_1_22_v4.2.1_"
                "benchmark_noinconsistent.bed"
            ),
            "role": "BENCHMARK_BED",
            "url": bed_url,
            "version": f"GIAB {sample} v4.2.1",
            "expected_sha256": expected_bed_sha[sample],
            "expected_md5": None,
            "reuse_basis": "NIST open terms",
            "notes": (
                "Frozen sample benchmark BED used to verify that the "
                "Phase 2 shared panel remains within each sample truth domain."
            ),
        }

    specs["artifact-reference-grch38-no-alt"] = {
        "artifact_id": "artifact-reference-grch38-no-alt",
        "name": reference_name,
        "role": "REFERENCE_FASTA",
        "url": reference_base + reference_name,
        "version": "GCA_000001405.15 GRCh38 no-alt analysis set",
        "expected_sha256": None,
        "expected_md5": "3a3347eae0893f96ecf495d1c39e2284",
        "reuse_basis": "CC0 plus NIST Data Use Policy",
        "notes": "Pinned BGZF GRCh38 reference.",
    }

    specs["artifact-reference-grch38-no-alt-fai"] = {
        "artifact_id": "artifact-reference-grch38-no-alt-fai",
        "name": reference_name + ".fai",
        "role": "REFERENCE_INDEX",
        "url": reference_base + reference_name + ".fai",
        "version": "GCA_000001405.15 GRCh38 no-alt analysis set",
        "expected_sha256": None,
        "expected_md5": "5fddbc109c82980f9436aa5c21a57c61",
        "reuse_basis": "CC0 plus NIST Data Use Policy",
        "notes": "FAI for pinned reference.",
    }

    specs["artifact-reference-grch38-no-alt-gzi"] = {
        "artifact_id": "artifact-reference-grch38-no-alt-gzi",
        "name": reference_name + ".gzi",
        "role": "REFERENCE_INDEX",
        "url": reference_base + reference_name + ".gzi",
        "version": "GCA_000001405.15 GRCh38 no-alt analysis set",
        "expected_sha256": None,
        "expected_md5": "cfa1ee11b1ecb29f936578b27014fbe0",
        "reuse_basis": "CC0 plus NIST Data Use Policy",
        "notes": "GZI for pinned reference.",
    }

    return specs


def download_source(spec):
    destination = SOURCE_DIR / spec["name"]

    if not destination.exists():
        run(
            [
                "curl",
                "-L",
                "--fail",
                "--retry",
                "5",
                "--retry-delay",
                "2",
                "--continue-at",
                "-",
                "--output",
                str(destination),
                spec["url"],
            ]
        )

    actual_sha = sha256_file(destination)
    actual_md5 = md5_file(destination)

    if (
        spec["expected_sha256"] is not None
        and actual_sha != spec["expected_sha256"]
    ):
        raise RuntimeError(
            f"{spec['artifact_id']} SHA-256 mismatch"
        )

    if (
        spec["expected_md5"] is not None
        and actual_md5 != spec["expected_md5"]
    ):
        raise RuntimeError(
            f"{spec['artifact_id']} publisher MD5 mismatch"
        )

    checksums = [
        {
            "algorithm": "sha256",
            "value": actual_sha,
            "source": "COMPUTED_ON_RETRIEVAL",
        }
    ]
    if spec["expected_md5"] is not None:
        checksums.append(
            {
                "algorithm": "md5",
                "value": actual_md5,
                "source": "PUBLISHER",
            }
        )

    make_source_artifact(
        spec["artifact_id"],
        spec["name"],
        spec["role"],
        spec["url"],
        spec["version"],
        path=destination,
        checksums=checksums,
        checksum_status=(
            "PUBLISHER_VERIFIED"
            if spec["expected_md5"] is not None
            else "COMPUTED_NOT_YET_VERIFIED"
        ),
        reuse_basis=spec["reuse_basis"],
        notes=spec["notes"],
    )

    retrieval_rows.append(
        {
            "source_artifact_id": spec["artifact_id"],
            "artifact_name": spec["name"],
            "uri": spec["url"],
            "byte_size": destination.stat().st_size,
            "computed_sha256": actual_sha,
            "computed_md5": actual_md5,
            "expected_sha256": spec["expected_sha256"] or "",
            "expected_md5": spec["expected_md5"] or "",
            "verified_at": now_iso(),
            "status": "VERIFIED",
        }
    )

    return destination


def download_genomic_sources(frozen):
    specs = source_specs(frozen)
    downloaded = {}

    with stage_guard("public genomic source retrieval"):
        for artifact_id in sorted(specs):
            downloaded[artifact_id] = download_source(
                specs[artifact_id]
            )
        write_tsv(
            RESULTS_DIR / "retrieved_artifacts.tsv",
            retrieval_rows,
        )

    return specs, downloaded


def merge_intervals(rows):
    by_chrom = {}
    for chrom, start, end in rows:
        by_chrom.setdefault(chrom, []).append((start, end))

    merged = {}
    for chrom, intervals in by_chrom.items():
        out = []
        for start, end in sorted(intervals):
            if out and start <= out[-1][1]:
                out[-1] = (out[-1][0], max(out[-1][1], end))
            else:
                out.append((start, end))
        merged[chrom] = out
    return merged


def interval_fully_covered(merged_by_chrom, chrom, start, end):
    cursor = start
    for region_start, region_end in merged_by_chrom.get(chrom, []):
        if region_end <= cursor:
            continue
        if region_start > cursor:
            return False
        cursor = max(cursor, region_end)
        if cursor >= end:
            return True
    return False


def interval_any_overlap(merged_by_chrom, chrom, start, end):
    return any(
        start < region_end and end > region_start
        for region_start, region_end in merged_by_chrom.get(chrom, [])
    )


def verify_panel_contained_in_sample_bed(panel_rows, sample_bed, sample):
    sample_rows = []
    for raw in Path(sample_bed).read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.startswith(("#", "track", "browser")):
            continue
        fields = raw.split("\t")
        sample_rows.append(
            (fields[0], int(fields[1]), int(fields[2]))
        )
    merged_sample = merge_intervals(sample_rows)

    failures = [
        (chrom, start, end)
        for chrom, start, end in panel_rows
        if not interval_fully_covered(
            merged_sample,
            chrom,
            start,
            end,
        )
    ]

    if failures:
        raise RuntimeError(
            f"Frozen panel is not fully contained in {sample} benchmark BED; "
            f"first failures: {failures[:3]}"
        )


def build_padded_panel(frozen, downloaded):
    panel_rows = frozen["panel_rows"]
    panel_chromosomes = frozen["panel_chromosomes"]

    fai = downloaded["artifact-reference-grch38-no-alt-fai"]
    chrom_lengths = {}
    for raw in fai.read_text(encoding="utf-8").splitlines():
        fields = raw.split("\t")
        chrom_lengths[fields[0]] = int(fields[1])

    for chrom in panel_chromosomes:
        if chrom not in chrom_lengths:
            raise RuntimeError(
                f"Panel chromosome absent from reference FAI: {chrom}"
            )

    padded = []
    for chrom, start, end in panel_rows:
        padded.append(
            (
                chrom,
                max(0, start - 1000),
                min(chrom_lengths[chrom], end + 1000),
            )
        )

    def chrom_sort_key(chrom):
        suffix = chrom.removeprefix("chr")
        return (
            int(suffix) if suffix.isdigit() else 1000,
            chrom,
        )

    padded.sort(
        key=lambda row: (
            chrom_sort_key(row[0]),
            row[1],
            row[2],
        )
    )

    merged = []
    for chrom, start, end in padded:
        if (
            merged
            and merged[-1][0] == chrom
            and start <= merged[-1][2]
        ):
            merged[-1] = (
                chrom,
                merged[-1][1],
                max(merged[-1][2], end),
            )
        else:
            merged.append((chrom, start, end))

    padded_path = STAGED_DIR / "phase2c_padded_retrieval_segments.bed"
    with padded_path.open("w", encoding="utf-8") as handle:
        for chrom, start, end in merged:
            handle.write(f"{chrom}\t{start}\t{end}\n")

    make_derived_artifact(
        "artifact-phase2-padded-retrieval-panel",
        padded_path,
        "DERIVED_SLICE",
        "Phase 2C retrieval padding v1",
        (
            "1,000 bp padding around frozen assessable segments followed "
            "by deterministic within-chromosome merging."
        ),
    )
    add_link(
        "SOURCE_ARTIFACT",
        "artifact-phase2-frozen-panel",
        "SOURCE_ARTIFACT",
        "artifact-phase2-padded-retrieval-panel",
        "DERIVED_FROM",
        "pad 1000 bp and merge overlapping retrieval intervals",
        "project003_phase2c_actions",
        "1.0.0",
        {
            "padding_bp": 1000,
            "benchmark_domain_changed": False,
        },
    )

    runs = frozen["runs"]
    for sample in ("HG003", "HG004"):
        row = next(
            value
            for value in runs.values()
            if value["sample_id"] == sample
        )
        verify_panel_contained_in_sample_bed(
            panel_rows,
            downloaded[row["benchmark_bed_artifact_id"]],
            sample,
        )

    return padded_path, sha256_file(padded_path), merged


def prepare_query_vcfs(frozen, downloaded):
    query_ready = {}

    with stage_guard("query VCF preparation"):
        for key in frozen["run_keys"]:
            cfg = frozen["runs"][key]
            source_id = cfg["query_artifact_id"]
            original = downloaded[source_id]
            original_sha = sha256_file(original)

            probe = run(
                ["bcftools", "view", "-h", str(original)],
                check=False,
            )
            if probe.returncode:
                raise RuntimeError(
                    f"{source_id} is not readable as VCF"
                )

            index_path = Path(str(original) + ".tbi")
            index_cp = run(
                [
                    "bcftools",
                    "index",
                    "--tbi",
                    "--force",
                    str(original),
                ],
                check=False,
            )

            if index_cp.returncode == 0:
                ready = original
                index_id = source_id + "-generated-tbi"
                make_derived_artifact(
                    index_id,
                    index_path,
                    "OTHER",
                    "tabix index",
                    "Index generated without altering original query VCF bytes.",
                )
                add_link(
                    "SOURCE_ARTIFACT",
                    source_id,
                    "SOURCE_ARTIFACT",
                    index_id,
                    "GENERATED",
                    "bcftools index --tbi",
                    "bcftools",
                    runtime_identity["bcftools_version"],
                )
            else:
                derived = STAGED_DIR / f"{key}.sorted.vcf.gz"
                run(
                    [
                        "bcftools",
                        "sort",
                        "-Oz",
                        "-o",
                        str(derived),
                        str(original),
                    ]
                )
                run(
                    [
                        "bcftools",
                        "index",
                        "--tbi",
                        "--force",
                        str(derived),
                    ]
                )
                derived_id = source_id + "-sorted-bgzf"
                make_derived_artifact(
                    derived_id,
                    derived,
                    "DERIVED_SLICE",
                    "Phase 2C VCF prerequisite",
                    (
                        "Sorted/BGZF derivative; original source retained "
                        "byte-identical."
                    ),
                )
                make_derived_artifact(
                    derived_id + "-tbi",
                    Path(str(derived) + ".tbi"),
                    "OTHER",
                    "tabix index",
                    "Index for sorted/BGZF query derivative.",
                )
                add_link(
                    "SOURCE_ARTIFACT",
                    source_id,
                    "SOURCE_ARTIFACT",
                    derived_id,
                    "DERIVED_FROM",
                    "bcftools sort -Oz",
                    "bcftools",
                    runtime_identity["bcftools_version"],
                )
                add_link(
                    "SOURCE_ARTIFACT",
                    derived_id,
                    "SOURCE_ARTIFACT",
                    derived_id + "-tbi",
                    "GENERATED",
                    "bcftools index --tbi",
                    "bcftools",
                    runtime_identity["bcftools_version"],
                )
                ready = derived

            if sha256_file(original) != original_sha:
                raise RuntimeError(
                    f"Original query bytes changed: {source_id}"
                )

            query_ready[key] = ready

    return query_ready


def slice_vcfs(frozen, downloaded, padded_panel, query_ready):
    truth_slices = {}
    query_slices = {}

    with stage_guard("multi-region VCF slicing"):
        for sample in ("HG003", "HG004"):
            cfg = next(
                value
                for value in frozen["runs"].values()
                if value["sample_id"] == sample
            )
            truth_id = cfg["truth_artifact_id"]
            truth_source = downloaded[truth_id]

            truth_slice = STAGED_DIR / f"{sample}.phase2c.truth.vcf.gz"
            run(
                [
                    "bcftools",
                    "view",
                    "-R",
                    str(padded_panel),
                    "--regions-overlap",
                    "1",
                    "-Oz",
                    "-o",
                    str(truth_slice),
                    str(truth_source),
                ]
            )
            run(
                [
                    "bcftools",
                    "index",
                    "--tbi",
                    "--force",
                    str(truth_slice),
                ]
            )

            truth_slices[sample] = truth_slice
            truth_slice_id = truth_id + "-phase2c-padded"
            make_derived_artifact(
                truth_slice_id,
                truth_slice,
                "DERIVED_SLICE",
                "GIAB v4.2.1 Phase 2C padded slice",
                "Truth records retrieved using deterministic padded panel.",
            )
            make_derived_artifact(
                truth_slice_id + "-tbi",
                Path(str(truth_slice) + ".tbi"),
                "OTHER",
                "tabix index",
                "Index for Phase 2C truth slice.",
            )
            add_link(
                "SOURCE_ARTIFACT",
                truth_id,
                "SOURCE_ARTIFACT",
                truth_slice_id,
                "DERIVED_FROM",
                "bcftools view -R padded retrieval panel",
                "bcftools",
                runtime_identity["bcftools_version"],
            )

        for key in frozen["run_keys"]:
            cfg = frozen["runs"][key]
            query_slice = STAGED_DIR / f"{key}.query.vcf.gz"
            run(
                [
                    "bcftools",
                    "view",
                    "-R",
                    str(padded_panel),
                    "--regions-overlap",
                    "1",
                    "-Oz",
                    "-o",
                    str(query_slice),
                    str(query_ready[key]),
                ]
            )
            run(
                [
                    "bcftools",
                    "index",
                    "--tbi",
                    "--force",
                    str(query_slice),
                ]
            )

            query_slices[key] = query_slice
            query_slice_id = cfg["query_artifact_id"] + "-phase2c-padded"
            make_derived_artifact(
                query_slice_id,
                query_slice,
                "DERIVED_SLICE",
                "Phase 2C padded query slice",
                "Query records retrieved using deterministic padded panel.",
            )
            make_derived_artifact(
                query_slice_id + "-tbi",
                Path(str(query_slice) + ".tbi"),
                "OTHER",
                "tabix index",
                "Index for Phase 2C query slice.",
            )
            add_link(
                "SOURCE_ARTIFACT",
                cfg["query_artifact_id"],
                "SOURCE_ARTIFACT",
                query_slice_id,
                "DERIVED_FROM",
                "bcftools view -R padded retrieval panel",
                "bcftools",
                runtime_identity["bcftools_version"],
            )

    return truth_slices, query_slices


def prepare_reference(frozen, downloaded, runtime):
    with stage_guard("reference subset and RTG SDF preparation"):
        reference_source = downloaded[
            "artifact-reference-grch38-no-alt"
        ]
        reference_subset = (
            STAGED_DIR / "GRCh38.phase2c.chromosomes.fasta"
        )

        run_to_file(
            [
                "samtools",
                "faidx",
                str(reference_source),
                *frozen["panel_chromosomes"],
            ],
            reference_subset,
        )
        run(["samtools", "faidx", str(reference_subset)])

        subset_fai = Path(str(reference_subset) + ".fai")
        observed_chromosomes = {
            raw.split("\t")[0]
            for raw in subset_fai.read_text(
                encoding="utf-8"
            ).splitlines()
            if raw.strip()
        }
        if observed_chromosomes != set(
            frozen["panel_chromosomes"]
        ):
            raise RuntimeError(
                "Reference subset chromosome set mismatch"
            )

        reference_sdf = STAGED_DIR / "GRCh38.phase2c.sdf"
        if reference_sdf.exists():
            shutil.rmtree(reference_sdf)

        run(
            [
                str(runtime["rtg_exe"]),
                "format",
                "-o",
                str(reference_sdf),
                str(reference_subset),
            ]
        )

        sdf_manifest = (
            STAGED_DIR / "GRCh38.phase2c.sdf.manifest.json"
        )
        sdf_manifest.write_text(
            json.dumps(
                {
                    "tree_sha256": tree_sha256(reference_sdf),
                    "files": [
                        str(item.relative_to(reference_sdf))
                        for item in sorted(reference_sdf.rglob("*"))
                        if item.is_file()
                    ],
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        make_derived_artifact(
            "artifact-reference-phase2c-chromosomes",
            reference_subset,
            "DERIVED_SLICE",
            "Phase 2C GRCh38 chromosome subset",
            (
                "Whole GRCh38 reference chromosomes represented by the "
                "frozen Phase 2 panel."
            ),
        )
        make_derived_artifact(
            "artifact-reference-phase2c-chromosomes-fai",
            subset_fai,
            "REFERENCE_INDEX",
            "samtools faidx",
            "FAI for Phase 2C reference chromosome subset.",
        )
        make_derived_artifact(
            "artifact-reference-phase2c-sdf",
            sdf_manifest,
            "OTHER",
            "RTG SDF 3.12.1",
            "Manifest and tree hash for the ephemeral RTG SDF directory.",
        )
        add_link(
            "SOURCE_ARTIFACT",
            "artifact-reference-grch38-no-alt",
            "SOURCE_ARTIFACT",
            "artifact-reference-phase2c-chromosomes",
            "DERIVED_FROM",
            "samtools faidx whole selected chromosomes",
            "samtools",
            runtime_identity["samtools_version"],
            {"chromosomes": frozen["panel_chromosomes"]},
        )

        return reference_subset, reference_sdf


def run_benchmarks(
    frozen,
    paths,
    runtime,
    truth_slices,
    query_slices,
    reference_subset,
    reference_sdf,
):
    comparator_lock = runtime["comparator_lock"]

    def run_one(key):
        cfg = frozen["runs"][key]
        run_dir = RUNS_DIR / key
        run_dir.mkdir(parents=True, exist_ok=True)

        prefix = run_dir / "phase2c.happy"
        stdout_path = run_dir / "hap.py.stdout.log"
        stderr_path = run_dir / "hap.py.stderr.log"
        timing_path = run_dir / "hap.py.time.txt"

        inner = [
            "hap.py",
            str(truth_slices[cfg["sample_id"]]),
            str(query_slices[key]),
            "-f",
            str(paths["panel"]),
            "-r",
            str(reference_subset),
            "-o",
            str(prefix),
            "-V",
            "--engine=vcfeval",
            "--engine-vcfeval-path=/opt/rtg-tools-3.12.1/rtg",
            "--engine-vcfeval-template",
            str(reference_sdf),
            "--threads=2",
        ]
        argv = runtime["container_argv"](inner)

        started_at = now_iso()
        timed = [
            "/usr/bin/time",
            "-v",
            "-o",
            str(timing_path),
            *argv,
        ]
        append_command(timed)

        with stdout_path.open(
            "w", encoding="utf-8"
        ) as out, stderr_path.open(
            "w", encoding="utf-8"
        ) as err:
            process = subprocess.run(
                timed,
                stdout=out,
                stderr=err,
                text=True,
                env=runtime["container_env"],
            )

        completed_at = now_iso()
        if process.returncode:
            raise RuntimeError(
                f"hap.py failed for {key}; see {stderr_path}"
            )

        runs_state[key] = {
            "run_id": cfg["run_id"],
            "experiment_id": cfg["experiment_id"],
            "prefix": prefix,
            "run_dir": run_dir,
            "command_argv": argv,
            "started_at": started_at,
            "completed_at": completed_at,
            "exit_code": process.returncode,
            "stdout": stdout_path,
            "stderr": stderr_path,
            "timing": timing_path,
        }

    with stage_guard("four Phase 2C hap.py comparisons"):
        for key in frozen["run_keys"]:
            print(f"Running Phase 2C benchmark: {key}")
            run_one(key)

    return comparator_lock


def verify_annotated_outputs(frozen):
    import pysam

    def find_annotated_vcf(prefix):
        candidates = [
            Path(str(prefix) + ".vcf.gz"),
            Path(str(prefix) + ".happy.vcf.gz"),
        ]
        candidates.extend(
            sorted(
                prefix.parent.glob(prefix.name + "*.vcf.gz")
            )
        )
        for candidate in candidates:
            if candidate.exists() and candidate.stat().st_size > 0:
                return candidate
        raise RuntimeError(
            f"No annotated VCF found for {prefix}"
        )

    annotation_gates = {}
    compact_dir = RESULTS_DIR / "comparison_outputs"
    compact_dir.mkdir(exist_ok=True)

    with stage_guard("annotated comparator output gate"):
        for key in frozen["run_keys"]:
            state = runs_state[key]
            annotated = find_annotated_vcf(state["prefix"])
            annotated_tbi = Path(str(annotated) + ".tbi")
            if not annotated_tbi.exists():
                run(
                    [
                        "bcftools",
                        "index",
                        "--tbi",
                        "--force",
                        str(annotated),
                    ]
                )

            metrics = [
                path
                for path in sorted(
                    state["run_dir"].glob(
                        state["prefix"].name + "*"
                    )
                )
                if (
                    path.is_file()
                    and path not in {annotated, annotated_tbi}
                    and any(
                        token in path.name
                        for token in (
                            "summary",
                            "extended",
                            "metrics",
                        )
                    )
                )
            ]
            if not metrics:
                raise RuntimeError(
                    f"Metrics output absent for {key}"
                )

            variant_file = pysam.VariantFile(str(annotated))
            samples = list(variant_file.header.samples)
            formats = set(variant_file.header.formats)
            record_count = sum(1 for _ in variant_file)
            variant_file.close()

            if not {"TRUTH", "QUERY"} <= set(samples):
                raise RuntimeError(
                    f"TRUTH/QUERY samples missing for {key}"
                )
            if not {"BD", "BK"} <= formats:
                raise RuntimeError(
                    f"BD/BK FORMAT fields missing for {key}"
                )
            if record_count <= 0:
                raise RuntimeError(
                    f"Annotated VCF is empty for {key}"
                )

            compact_vcf = compact_dir / f"{key}.annotated.vcf.gz"
            compact_tbi = Path(str(compact_vcf) + ".tbi")
            shutil.copy2(annotated, compact_vcf)
            shutil.copy2(annotated_tbi, compact_tbi)

            for log_path in (
                state["stdout"],
                state["stderr"],
                state["timing"],
            ):
                shutil.copy2(
                    log_path,
                    RESULTS_DIR / f"{key}.{log_path.name}",
                )

            state["annotated"] = annotated
            state["compact_annotated"] = compact_vcf
            state["compact_annotated_tbi"] = compact_tbi
            state["metrics"] = metrics

            annotation_gates[key] = {
                "run_id": state["run_id"],
                "samples": samples,
                "format_ids": sorted(formats),
                "record_count": record_count,
                "has_TRUTH": "TRUTH" in samples,
                "has_QUERY": "QUERY" in samples,
                "has_BD": "BD" in formats,
                "has_BK": "BK" in formats,
                "has_BS": "BS" in formats,
                "metrics": [path.name for path in metrics],
            }

        (
            RESULTS_DIR / "annotation_gates.json"
        ).write_text(
            json.dumps(
                annotation_gates,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    return annotation_gates


def parse_events_observations(frozen):
    import pysam

    decision_map = {
        "TP": "TP",
        "FP": "FP",
        "FN": "FN",
        "N": "N",
        "UNK": "UNK",
        "IGN": "IGN",
    }

    panel_merged = merge_intervals(frozen["panel_rows"])

    def region_status(chrom, start, end):
        if interval_fully_covered(
            panel_merged,
            chrom,
            start,
            end,
        ):
            return "INSIDE"
        if interval_any_overlap(
            panel_merged,
            chrom,
            start,
            end,
        ):
            return "BORDER"
        return "OUTSIDE"

    def value_text(value):
        if value is None:
            return "UNKNOWN"
        if isinstance(value, tuple):
            return "/".join(
                "." if item is None else str(item)
                for item in value
            )
        return str(value)

    def genotype_text(sample):
        gt = sample.get("GT")
        if gt is None:
            return None
        separator = (
            "|"
            if getattr(sample, "phased", False)
            else "/"
        )
        return separator.join(
            "." if item is None else str(item)
            for item in gt
        )

    def exact_lookup(contig, position, ref, alts):
        if len(alts) != 1:
            return None
        alt = alts[0]
        if not re.fullmatch(r"[ACGTN]+", ref, re.I):
            return None
        if not re.fullmatch(r"[ACGTN]+", alt, re.I):
            return None
        return (
            f"GRCh38|{contig}|{position}|"
            f"{ref.upper()}|{alt.upper()}"
        )

    events = []
    observations = []
    accounting_rows = []
    event_by_id = {}
    event_bounds = {}

    with stage_guard("Phase 2C event/observation parsing"):
        for key in frozen["run_keys"]:
            state = runs_state[key]
            run_id = state["run_id"]
            output_artifact_id = f"artifact-{key}-annotated-vcf"

            variant_file = pysam.VariantFile(
                str(state["annotated"])
            )
            has_bs = "BS" in variant_file.header.formats

            for ordinal, record in enumerate(variant_file, 1):
                start0 = record.pos - 1
                end0 = start0 + len(record.ref)
                alts = list(record.alts or [])
                raw_alt = ",".join(alts) if alts else "."

                bs_values = []
                if has_bs:
                    for side in ("TRUTH", "QUERY"):
                        bs = record.samples[side].get("BS")
                        if bs not in (None, ".", ""):
                            bs_values.append(value_text(bs))

                source_bs = (
                    bs_values[0]
                    if bs_values and len(set(bs_values)) == 1
                    else None
                )

                if source_bs:
                    safe_bs = re.sub(
                        r"[^A-Za-z0-9_.-]+",
                        "_",
                        source_bs,
                    )
                    event_id = (
                        f"event-{run_id}-{record.contig}-bs-{safe_bs}"
                    )
                    identity_scope = "COMPARATOR_SUPERLOCUS"
                    derivation = (
                        "hap.py BS scoped to one Phase 2C benchmark run"
                    )
                else:
                    event_id = (
                        f"event-{run_id}-{record.contig}-record-{ordinal}"
                    )
                    identity_scope = "SOURCE_RECORD_FALLBACK"
                    derivation = (
                        "deterministic source-record fallback because BS is absent"
                    )

                bounds = event_bounds.get(event_id)
                if bounds is None:
                    event_bounds[event_id] = {
                        "contig": record.contig,
                        "start": start0,
                        "end": end0,
                    }
                else:
                    if bounds["contig"] != record.contig:
                        raise RuntimeError(
                            f"One comparator event crossed contigs: {event_id}"
                        )
                    bounds["start"] = min(bounds["start"], start0)
                    bounds["end"] = max(bounds["end"], end0)

                record_inside = interval_fully_covered(
                    panel_merged,
                    record.contig,
                    start0,
                    end0,
                )

                if record_inside:
                    lookup_key = exact_lookup(
                        record.contig,
                        record.pos,
                        record.ref,
                        alts,
                    )

                    if event_id not in event_by_id:
                        event = {
                            "schema_version": "1.0.0",
                            "event_id": event_id,
                            "identity_scope": identity_scope,
                            "benchmark_run_id": run_id,
                            "reference_artifact_id": (
                                "artifact-reference-grch38-no-alt"
                            ),
                            "assembly": "GRCh38",
                            "contig": record.contig,
                            "start_0based": start0,
                            "end_0based": end0,
                            "source_event_id": source_bs,
                            "normalized_allele_lookup_key": lookup_key,
                            "derivation_method": derivation,
                            "derivation_version": "phase2c_actions/1.0.0",
                            "cross_run_equivalence_asserted": False,
                            "notes": (
                                "Run-scoped Phase 2C event; biological identity "
                                "is deferred to Phase 2D."
                            ),
                        }
                        events.append(event)
                        event_by_id[event_id] = event
                    else:
                        event = event_by_id[event_id]
                        event["start_0based"] = min(
                            event["start_0based"],
                            start0,
                        )
                        event["end_0based"] = max(
                            event["end_0based"],
                            end0,
                        )
                        if (
                            event["normalized_allele_lookup_key"]
                            != lookup_key
                        ):
                            event["normalized_allele_lookup_key"] = None

                    for side in ("TRUTH", "QUERY"):
                        sample_data = record.samples[side]
                        raw_bd = value_text(sample_data.get("BD"))
                        raw_bk = value_text(sample_data.get("BK"))
                        raw_bs = (
                            value_text(sample_data.get("BS"))
                            if has_bs
                            else "UNKNOWN"
                        )
                        formats = {
                            field: value_text(sample_data.get(field))
                            for field in sample_data.keys()
                        }

                        observations.append(
                            {
                                "schema_version": "1.0.0",
                                "observation_id": (
                                    f"obs-{run_id}-{ordinal}-{side.lower()}"
                                ),
                                "benchmark_run_id": run_id,
                                "event_id": event_id,
                                "side": side,
                                "observation_origin": "REGENERATED",
                                "raw_decision": raw_bd,
                                "normalized_decision": decision_map.get(
                                    raw_bd,
                                    "OTHER",
                                ),
                                "raw_match_kind": raw_bk,
                                "raw_engine_detail": json.dumps(
                                    {
                                        "BS": raw_bs,
                                        "all_format_values": formats,
                                    },
                                    sort_keys=True,
                                ),
                                "raw_variant_type": (
                                    value_text(sample_data.get("BVT"))
                                    if "BVT" in sample_data
                                    else None
                                ),
                                "raw_location_type": (
                                    value_text(sample_data.get("BLT"))
                                    if "BLT" in sample_data
                                    else None
                                ),
                                "region_status": region_status(
                                    record.contig,
                                    start0,
                                    end0,
                                ),
                                "source_output_artifact_id": output_artifact_id,
                                "source_record_ordinal": ordinal,
                                "source_contig": record.contig,
                                "source_pos_1based": record.pos,
                                "source_ref": record.ref,
                                "source_alt": raw_alt,
                                "source_genotype": genotype_text(sample_data),
                                "source_filter": (
                                    list(record.filter.keys()) or ["."]
                                ),
                                "quality_score": (
                                    float(record.qual)
                                    if record.qual is not None
                                    else None
                                ),
                                "normalization_method": (
                                    "source representation retained; exact lookup "
                                    "emitted only when single-allele unambiguous"
                                ),
                                "normalization_version": "phase2c_actions/1.0.0",
                                "normalized_start_0based": start0,
                                "normalized_end_0based": end0,
                                "normalized_ref": (
                                    record.ref if len(alts) == 1 else None
                                ),
                                "normalized_alt": (
                                    alts[0] if len(alts) == 1 else None
                                ),
                                "notes": (
                                    "Phase 2C observation fully inside frozen "
                                    "assessable panel."
                                ),
                            }
                        )

                accounting_rows.append(
                    {
                        "benchmark_run_id": run_id,
                        "source_record_ordinal": ordinal,
                        "chromosome": record.contig,
                        "position_1based": record.pos,
                        "ref": record.ref,
                        "alt": raw_alt,
                        "truth_raw_decision": value_text(
                            record.samples["TRUTH"].get("BD")
                        ),
                        "query_raw_decision": value_text(
                            record.samples["QUERY"].get("BD")
                        ),
                        "benchmark_region_status": region_status(
                            record.contig,
                            start0,
                            end0,
                        ),
                        "classification": (
                            "CORE_EXPORTED"
                            if record_inside
                            else (
                                "PANEL_BOUNDARY_DIAGNOSTIC"
                                if interval_any_overlap(
                                    panel_merged,
                                    record.contig,
                                    start0,
                                    end0,
                                )
                                else "OUTSIDE_PANEL_DIAGNOSTIC"
                            )
                        ),
                        "event_id": event_id,
                    }
                )

            variant_file.close()

        exportable = set()
        for event_id, bounds in event_bounds.items():
            if interval_fully_covered(
                panel_merged,
                bounds["contig"],
                bounds["start"],
                bounds["end"],
            ):
                exportable.add(event_id)

        events[:] = [
            event
            for event in events
            if event["event_id"] in exportable
        ]
        observations[:] = [
            observation
            for observation in observations
            if observation["event_id"] in exportable
        ]

        for event in events:
            bounds = event_bounds[event["event_id"]]
            event["start_0based"] = bounds["start"]
            event["end_0based"] = bounds["end"]

        for row in accounting_rows:
            if row["event_id"] not in exportable:
                row["classification"] = "BOUNDARY_EVENT_DIAGNOSTIC"

        write_tsv(
            RESULTS_DIR / "annotated_record_accounting.tsv",
            accounting_rows,
        )

    return events, observations, accounting_rows


def construct_registry_entities(
    frozen,
    runtime,
    padded_panel_sha,
    events,
    observations,
):
    experiments = []
    benchmark_runs = []

    with stage_guard("Phase 2C provenance construction"):
        for key in frozen["run_keys"]:
            cfg = frozen["runs"][key]
            metadata = frozen["submission_metadata"][
                cfg["source_submission_id"]
            ]

            experiments.append(
                {
                    "schema_version": "1.0.0",
                    "experiment_id": cfg["experiment_id"],
                    "source_corpus": cfg["source_corpus"],
                    "source_submission_id": cfg["source_submission_id"],
                    "sample_id": cfg["sample_id"],
                    "technology": cfg["technology"],
                    "platform": cfg["platform"],
                    "coverage": cfg["coverage"],
                    "library_preparation": "UNKNOWN",
                    "basecaller": (
                        "Guppy"
                        if cfg["technology"] == "ONT"
                        else "UNKNOWN"
                    ),
                    "basecaller_version": (
                        "3.6"
                        if cfg["technology"] == "ONT"
                        else "UNKNOWN"
                    ),
                    "aligner_names": metadata[
                        "aligner_names"
                    ].split(";"),
                    "aligner_versions": metadata[
                        "aligner_versions"
                    ].split(";"),
                    "pipeline_name": cfg["pipeline_name"],
                    "pipeline_version": "UNKNOWN",
                    "caller_names": metadata[
                        "caller_names"
                    ].split(";"),
                    "caller_versions": metadata[
                        "caller_versions"
                    ].split(";"),
                    "reference_assembly": "GRCh38",
                    "metadata_artifact_ids": [
                        "artifact-phase2-admitted-sources",
                        "artifact-submission-method-template",
                    ],
                    "selection_basis": cfg["selection_basis"],
                    "performance_consulted_for_selection": False,
                    "notes": (
                        "Submission-level pipeline metadata is inherited from "
                        "the same precisionFDA V2 submission family; unknown "
                        "versions remain UNKNOWN."
                    ),
                }
            )

            for metadata_id in (
                "artifact-phase2-admitted-sources",
                "artifact-submission-method-template",
            ):
                add_link(
                    "SOURCE_ARTIFACT",
                    metadata_id,
                    "EXPERIMENT",
                    cfg["experiment_id"],
                    "DESCRIBES",
                    "frozen source-selection and submission-method metadata",
                    "project003_phase2c_actions",
                    "1.0.0",
                )

        for key in frozen["run_keys"]:
            cfg = frozen["runs"][key]
            state = runs_state[key]
            generated_ids = []

            products = [
                (
                    f"artifact-{key}-annotated-vcf",
                    state["compact_annotated"],
                    "COMPARATOR_OUTPUT",
                    "hap.py 0.3.15 annotated VCF",
                ),
                (
                    f"artifact-{key}-annotated-vcf-tbi",
                    state["compact_annotated_tbi"],
                    "OTHER",
                    "tabix index for annotated VCF",
                ),
                (
                    f"artifact-{key}-stdout",
                    RESULTS_DIR / f"{key}.{state['stdout'].name}",
                    "RUN_LOG",
                    "hap.py stdout",
                ),
                (
                    f"artifact-{key}-stderr",
                    RESULTS_DIR / f"{key}.{state['stderr'].name}",
                    "RUN_LOG",
                    "hap.py stderr",
                ),
                (
                    f"artifact-{key}-timing",
                    RESULTS_DIR / f"{key}.{state['timing'].name}",
                    "RUN_LOG",
                    "GNU time report",
                ),
            ]

            for metric_index, metric in enumerate(
                state["metrics"],
                1,
            ):
                metric_dest = (
                    RESULTS_DIR
                    / "comparison_outputs"
                    / f"{key}.{metric.name}"
                )
                shutil.copy2(metric, metric_dest)
                products.append(
                    (
                        f"artifact-{key}-metric-{metric_index}",
                        metric_dest,
                        "COMPARATOR_OUTPUT",
                        "hap.py metrics output",
                    )
                )

            for artifact_id, path, role, note in products:
                make_derived_artifact(
                    artifact_id,
                    path,
                    role,
                    "Phase 2C regenerated",
                    note,
                )
                generated_ids.append(artifact_id)
                add_link(
                    "BENCHMARK_RUN",
                    cfg["run_id"],
                    "SOURCE_ARTIFACT",
                    artifact_id,
                    "GENERATED",
                    note,
                    "hap.py",
                    "0.3.15",
                )

            truth_slice_id = (
                cfg["truth_artifact_id"] + "-phase2c-padded"
            )
            query_slice_id = (
                cfg["query_artifact_id"] + "-phase2c-padded"
            )

            benchmark_runs.append(
                {
                    "schema_version": "2.0.0",
                    "benchmark_run_id": cfg["run_id"],
                    "experiment_id": cfg["experiment_id"],
                    "observation_origin": "REGENERATED",
                    "query_artifact_id": cfg["query_artifact_id"],
                    "truth_artifact_id": cfg["truth_artifact_id"],
                    "benchmark_region_set_artifact_id": (
                        "artifact-phase2-frozen-panel"
                    ),
                    "benchmark_region_set_sha256": frozen[
                        "compute_lock"
                    ]["selected_assessable_segments_sha256"],
                    "retrieval_region_set_artifact_id": (
                        "artifact-phase2-padded-retrieval-panel"
                    ),
                    "retrieval_region_set_sha256": padded_panel_sha,
                    "reference_artifact_id": (
                        "artifact-reference-grch38-no-alt"
                    ),
                    "reference_assembly": "GRCh38",
                    "benchmark_region_set": {
                        "assembly": "GRCh38",
                        "coordinate_system": "0-based half-open",
                        "selected_window_count": 50,
                        "segment_count": 541,
                        "context_count": 5,
                        "chromosome_count": 19,
                        "chromosomes": frozen["panel_chromosomes"],
                        "excluded_chromosomes": ["chr20"],
                        "assessable_bases": 1162571,
                    },
                    "retrieval_padding_bp": 1000,
                    "comparator": "hap.py",
                    "comparator_version": "0.3.15",
                    "engine": "vcfeval",
                    "engine_version": "3.12.1",
                    "environment_lock_id": runtime[
                        "comparator_lock"
                    ]["lock_id"],
                    "runtime_image_digest": runtime_identity[
                        "hap_py_container_digest"
                    ],
                    "command_argv": state["command_argv"],
                    "parameters": {
                        "threads": 2,
                        "annotated_vcf": True,
                        "retrieval_padding_bp": 1000,
                        "benchmark_panel_sha256": frozen[
                            "compute_lock"
                        ]["selected_assessable_segments_sha256"],
                        "immutable_args": runtime[
                            "comparator_lock"
                        ]["comparison"]["immutable_args"],
                    },
                    "run_status": "SUCCEEDED",
                    "started_at": state["started_at"],
                    "completed_at": state["completed_at"],
                    "output_artifact_ids": generated_ids,
                    "failure_reason": None,
                    "notes": (
                        "OmicsEdge regenerated Phase 2C run; not an original "
                        "precisionFDA event result."
                    ),
                }
            )

            used_inputs = [
                cfg["query_artifact_id"],
                query_slice_id,
                cfg["truth_artifact_id"],
                truth_slice_id,
                cfg["benchmark_bed_artifact_id"],
                "artifact-phase2-frozen-panel",
                "artifact-phase2-padded-retrieval-panel",
                "artifact-reference-grch38-no-alt",
                "artifact-reference-phase2c-chromosomes",
                "artifact-reference-phase2c-sdf",
                "artifact-happy-container",
                "artifact-rtg-tools-3121",
                "artifact-phase2-compute-protocol",
                "artifact-phase2-run-schema",
            ]

            for input_id in used_inputs:
                add_link(
                    "SOURCE_ARTIFACT",
                    input_id,
                    "BENCHMARK_RUN",
                    cfg["run_id"],
                    "USED",
                    (
                        "scientific input, derived runtime input, or frozen "
                        "configuration used by Phase 2C"
                    ),
                    "project003_phase2c_actions",
                    "1.0.0",
                )

        for observation in observations:
            add_link(
                "SOURCE_ARTIFACT",
                observation["source_output_artifact_id"],
                "OBSERVATION",
                observation["observation_id"],
                "NORMALIZED_FROM",
                (
                    "side-specific benchmark observation parsed from "
                    "annotated hap.py VCF"
                ),
                "project003_phase2c_actions",
                "1.0.0",
                {
                    "source_record_ordinal": observation[
                        "source_record_ordinal"
                    ],
                    "side": observation["side"],
                },
            )

        for event in events:
            add_link(
                "BENCHMARK_RUN",
                event["benchmark_run_id"],
                "EVENT",
                event["event_id"],
                "GENERATED",
                event["derivation_method"],
                "hap.py",
                "0.3.15",
            )

    return experiments, benchmark_runs


def validate_and_write_entities(
    paths,
    events,
    experiments,
    benchmark_runs,
    observations,
):
    import jsonschema
    import pyarrow as pa
    import pyarrow.parquet as pq

    source_artifacts = list(artifact_records.values())

    collections = {
        "events": events,
        "experiments": experiments,
        "benchmark_runs": benchmark_runs,
        "observations": observations,
        "source_artifacts": source_artifacts,
        "provenance_links": provenance_links,
    }

    schema_paths = {
        "events": paths["event_schema"],
        "experiments": paths["experiment_schema"],
        "benchmark_runs": paths["run_schema"],
        "observations": paths["observation_schema"],
        "source_artifacts": paths["source_artifact_schema"],
        "provenance_links": paths["provenance_schema"],
    }

    schema_errors = []

    with stage_guard("entity schema validation and typed export"):
        for name, rows in collections.items():
            schema = json.loads(
                schema_paths[name].read_text(encoding="utf-8")
            )
            validator = jsonschema.Draft202012Validator(schema)
            for ordinal, row in enumerate(rows):
                for error in validator.iter_errors(row):
                    schema_errors.append(
                        f"{name}[{ordinal}]: {error.message}"
                    )

        if schema_errors:
            raise RuntimeError(
                "Schema validation failed:\n"
                + "\n".join(schema_errors[:50])
            )

        for name, rows in collections.items():
            write_tsv(
                RESULTS_DIR / f"{name}.tsv",
                rows,
            )
            parquet_path = RESULTS_DIR / f"{name}.parquet"
            pq.write_table(
                pa.Table.from_pylist(rows),
                parquet_path,
                compression="zstd",
            )
            returned = pq.read_table(parquet_path).to_pylist()
            if len(returned) != len(rows):
                raise RuntimeError(
                    f"Parquet row-count mismatch for {name}"
                )

    return collections, schema_errors


def run_example_query(collections):
    import duckdb

    duckdb_path = WORK_ROOT / "phase2c.duckdb"
    if duckdb_path.exists():
        duckdb_path.unlink()

    with stage_guard("Phase 2C DuckDB evidence query"):
        con = duckdb.connect(str(duckdb_path))
        for name in collections:
            parquet_path = RESULTS_DIR / f"{name}.parquet"
            escaped = str(parquet_path).replace("'", "''")
            con.execute(
                f"CREATE VIEW {name} AS "
                f"SELECT * FROM read_parquet('{escaped}')"
            )

        if not collections["events"]:
            raise RuntimeError("No Phase 2C events available")

        example_event_id = collections["events"][0]["event_id"]
        query = """
        SELECT
            e.event_id,
            e.benchmark_run_id,
            br.experiment_id,
            x.sample_id,
            x.technology,
            x.source_submission_id,
            o.observation_id,
            o.side,
            o.raw_decision,
            o.raw_match_kind,
            o.source_contig,
            o.source_pos_1based,
            o.source_ref,
            o.source_alt
        FROM events e
        JOIN observations o
          ON e.event_id = o.event_id
        JOIN benchmark_runs br
          ON e.benchmark_run_id = br.benchmark_run_id
        JOIN experiments x
          ON br.experiment_id = x.experiment_id
        WHERE e.event_id = ?
        ORDER BY o.side
        """
        query_df = con.execute(
            query,
            [example_event_id],
        ).fetchdf()
        if query_df.empty:
            raise RuntimeError(
                "Example Phase 2C evidence query returned zero rows"
            )
        query_df.to_csv(
            RESULTS_DIR / "example_phase2c_event_query.tsv",
            sep="\t",
            index=False,
        )

        duck_counts = {
            name: con.execute(
                f"SELECT count(*) FROM {name}"
            ).fetchone()[0]
            for name in collections
        }
        con.close()

    return duck_counts


def validate_phase2c(
    frozen,
    specs,
    annotation_gates,
    collections,
    schema_errors,
    padded_panel_sha,
    duck_counts,
):
    events = collections["events"]
    experiments = collections["experiments"]
    benchmark_runs = collections["benchmark_runs"]
    observations = collections["observations"]
    source_artifacts = collections["source_artifacts"]

    artifact_ids = {
        row["source_artifact_id"]
        for row in source_artifacts
    }
    event_ids = {row["event_id"] for row in events}
    run_ids = {
        row["benchmark_run_id"]
        for row in benchmark_runs
    }
    experiment_ids = {
        row["experiment_id"]
        for row in experiments
    }
    observation_ids = {
        row["observation_id"]
        for row in observations
    }

    entity_maps = {
        "EVENT": event_ids,
        "EXPERIMENT": experiment_ids,
        "BENCHMARK_RUN": run_ids,
        "OBSERVATION": observation_ids,
        "SOURCE_ARTIFACT": artifact_ids,
        "PROVENANCE_LINK": {
            row["provenance_link_id"]
            for row in provenance_links
        },
    }

    endpoints_resolve = all(
        link["source_entity_id"]
        in entity_maps[link["source_entity_type"]]
        and link["target_entity_id"]
        in entity_maps[link["target_entity_type"]]
        for link in provenance_links
    )

    run_event_counts = {run_id: 0 for run_id in run_ids}
    run_observation_counts = {run_id: 0 for run_id in run_ids}
    for event in events:
        run_event_counts[event["benchmark_run_id"]] += 1
    for observation in observations:
        run_observation_counts[
            observation["benchmark_run_id"]
        ] += 1

    variant_pairs = [
        (
            observation["normalized_ref"],
            observation["normalized_alt"],
        )
        for observation in observations
        if (
            observation["normalized_ref"] is not None
            and observation["normalized_alt"] is not None
        )
    ]
    has_snv = any(
        len(ref) == 1 and len(alt) == 1
        for ref, alt in variant_pairs
    )
    has_indel = any(
        len(ref) != len(alt)
        for ref, alt in variant_pairs
    )

    technology_by_sample = {}
    for experiment in experiments:
        technology_by_sample.setdefault(
            experiment["sample_id"],
            set(),
        ).add(experiment["technology"])

    retrieval_by_id = {
        row["source_artifact_id"]: row
        for row in retrieval_rows
    }
    query_ids = {
        cfg["query_artifact_id"]
        for cfg in frozen["runs"].values()
    }
    query_integrity_ok = all(
        retrieval_by_id[query_id]["computed_sha256"]
        == specs[query_id]["expected_sha256"]
        for query_id in query_ids
    )

    forbidden_keys = {
        "reliability_score",
        "trust_score",
        "confidence_score",
        "technology_rank",
        "consensus_label",
        "trusted_label",
    }

    def contains_forbidden(value):
        if isinstance(value, dict):
            if forbidden_keys & set(value):
                return True
            return any(
                contains_forbidden(item)
                for item in value.values()
            )
        if isinstance(value, list):
            return any(
                contains_forbidden(item)
                for item in value
            )
        return False

    panel_merged = merge_intervals(frozen["panel_rows"])

    checks = {
        "C01_protocol_lock": (
            sha256_file(
                CONFIG_DIR
                / "docs/phase2/phase2c_compute_protocol.md"
            )
            == frozen["compute_lock"]["protocol_sha256"]
        ),
        "C02_panel_lock": (
            sha256_file(
                CONFIG_DIR
                / "data/phase2/selected_assessable_segments.bed"
            )
            == frozen["compute_lock"][
                "selected_assessable_segments_sha256"
            ]
        ),
        "C03_panel_geometry": (
            len(frozen["panel_rows"]) == 541
            and frozen["panel_bases"] == 1162571
            and len(frozen["panel_chromosomes"]) == 19
            and "chr20" not in frozen["panel_chromosomes"]
        ),
        "C04_four_runs": (
            len(benchmark_runs) == 4
            and len(run_ids) == 4
        ),
        "C05_query_integrity": query_integrity_ok,
        "C06_comparator_identity": (
            runtime_identity["hap_py_container_digest"]
            == (
                "sha256:"
                "d63b963a6cb01b4830393b22369e7b91"
                "d298e4156dde353739e74e4cfa4f96d0"
            )
            and "3.12.1"
            in runtime_identity["rtg_version_output"]
        ),
        "C07_all_runs_succeeded": all(
            state["exit_code"] == 0
            for state in runs_state.values()
        ),
        "C08_annotation_gate": all(
            gate["has_TRUTH"]
            and gate["has_QUERY"]
            and gate["has_BD"]
            and gate["has_BK"]
            and gate["record_count"] > 0
            for gate in annotation_gates.values()
        ),
        "C09_nonempty_evidence": all(
            run_event_counts[run_id] > 0
            and run_observation_counts[run_id] > 0
            for run_id in run_ids
        ),
        "C10_run_scoped_events": all(
            event["benchmark_run_id"] in run_ids
            and event["cross_run_equivalence_asserted"] is False
            for event in events
        ),
        "C11_panel_containment": all(
            event["contig"] != "chr20"
            and interval_fully_covered(
                panel_merged,
                event["contig"],
                event["start_0based"],
                event["end_0based"],
            )
            for event in events
        ),
        "C12_schema_validation": not schema_errors,
        "C13_provenance_endpoints": endpoints_resolve,
        "C14_snv_and_indel": has_snv and has_indel,
        "C15_samples_and_technologies": (
            set(technology_by_sample) == {"HG003", "HG004"}
            and all(
                technologies == {"ILLUMINA", "ONT"}
                for technologies in technology_by_sample.values()
            )
        ),
        "C16_no_forced_scoring": (
            not contains_forbidden(collections)
        ),
        "C17_multi_region_schema": all(
            run_record["schema_version"] == "2.0.0"
            and run_record["benchmark_region_set_sha256"]
            == frozen["compute_lock"][
                "selected_assessable_segments_sha256"
            ]
            and run_record["retrieval_padding_bp"] == 1000
            and run_record["retrieval_region_set_sha256"]
            == padded_panel_sha
            for run_record in benchmark_runs
        ),
        "C18_no_phase2d_identity": all(
            event["cross_run_equivalence_asserted"] is False
            for event in events
        ),
        "C19_duckdb_counts": all(
            duck_counts[name] == len(collections[name])
            for name in collections
        ),
    }

    rows = [
        {
            "validation_id": key,
            "status": "PASS" if result else "FAIL",
        }
        for key, result in checks.items()
    ]
    write_tsv(
        RESULTS_DIR / "phase2c_validation_results.tsv",
        rows,
        ["validation_id", "status"],
    )

    failed = [
        key
        for key, result in checks.items()
        if not result
    ]
    if failed:
        raise RuntimeError(
            "Phase 2C validation failed: " + ", ".join(failed)
        )

    return checks


def write_final_report(
    frozen,
    collections,
    checks,
    padded_panel_sha,
):
    run_manifest = {
        "project": "OmicsEdgeBio Project 003",
        "phase": "2C",
        "status": "PHASE2C_COMPUTE_PASS",
        "observation_origin": "REGENERATED",
        "created_at": now_iso(),
        "samples": ["HG003", "HG004"],
        "technologies": ["ILLUMINA", "ONT"],
        "run_ids": sorted(
            row["benchmark_run_id"]
            for row in collections["benchmark_runs"]
        ),
        "assembly": "GRCh38",
        "truth_version": "GIAB v4.2.1",
        "benchmark_panel_sha256": frozen["compute_lock"][
            "selected_assessable_segments_sha256"
        ],
        "benchmark_panel_segments": 541,
        "benchmark_panel_bases": 1162571,
        "benchmark_panel_chromosomes": frozen[
            "panel_chromosomes"
        ],
        "retrieval_padding_bp": 1000,
        "retrieval_panel_sha256": padded_panel_sha,
        "comparator": {
            "hap_py": "0.3.15",
            "rtg_vcfeval": "3.12.1",
            "container_digest": runtime_identity[
                "hap_py_container_digest"
            ],
        },
        "runtime_identity": runtime_identity,
        "counts": {
            name: len(rows)
            for name, rows in collections.items()
        },
        "phase2c_validation": checks,
        "phase2d_biological_identity_applied": False,
    }

    (
        RESULTS_DIR / "run_manifest.json"
    ).write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    report = f"""# Project 003 Phase 2C compute report

- Status: PHASE2C_COMPUTE_PASS
- Scope: benchmark expansion only
- Samples: HG003, HG004
- Technologies: Illumina, Oxford Nanopore
- Benchmark runs: {len(collections["benchmark_runs"])}
- Assembly: GRCh38
- Truth: GIAB v4.2.1
- hap.py: 0.3.15
- RTG vcfeval: 3.12.1
- Frozen windows: 50
- Frozen assessable segments: 541
- Frozen assessable bases: 1,162,571
- Chromosomes represented: 19
- chr20: excluded
- Events: {len(collections["events"])}
- Observations: {len(collections["observations"])}
- Biological identity expansion: not performed in Phase 2C

## Limitations

- Phase 2C does not assert cross-run biological identity.
- Representation equivalence remains unresolved.
- GIAB truth is benchmark truth, not biological or clinical truth.
- Evidence aggregation is not a reliability or trust score.
- No technology ranking or forced consensus is produced.
- Dataset scope remains limited to the frozen public Phase 2 sources.
"""
    (
        RESULTS_DIR / "phase2c_compute_report.md"
    ).write_text(report, encoding="utf-8")


def forbid_large_sources_in_results(specs):
    forbidden_names = {
        spec["name"]
        for spec in specs.values()
        if spec["role"] in {
            "QUERY_VCF",
            "TRUTH_VCF",
            "REFERENCE_FASTA",
        }
    }
    forbidden_suffixes = (
        ".fasta",
        ".fasta.gz",
        ".fa",
        ".fa.gz",
        ".bam",
        ".cram",
        ".fastq",
        ".fq",
    )

    for path in RESULTS_DIR.rglob("*"):
        if not path.is_file():
            continue
        if path.name in forbidden_names:
            raise RuntimeError(
                f"Source genomic input leaked into results: {path}"
            )
        if path.name.endswith(forbidden_suffixes):
            raise RuntimeError(
                f"Large reference/read artifact leaked into results: {path}"
            )


def main():
    paths = require_config_paths()

    with stage_guard("frozen configuration validation"):
        frozen = validate_frozen_configuration(paths)
        register_embedded_artifacts(paths)

    runtime = install_runtime(paths)

    specs, downloaded = download_genomic_sources(frozen)

    with stage_guard("Phase 2 panel/retrieval preparation"):
        padded_panel, padded_panel_sha, padded_segments = (
            build_padded_panel(
                frozen,
                downloaded,
            )
        )
        print(
            json.dumps(
                {
                    "padded_retrieval_segments": len(padded_segments),
                    "padded_panel_sha256": padded_panel_sha,
                },
                indent=2,
            )
        )

    query_ready = prepare_query_vcfs(
        frozen,
        downloaded,
    )

    truth_slices, query_slices = slice_vcfs(
        frozen,
        downloaded,
        padded_panel,
        query_ready,
    )

    reference_subset, reference_sdf = prepare_reference(
        frozen,
        downloaded,
        runtime,
    )

    run_benchmarks(
        frozen,
        paths,
        runtime,
        truth_slices,
        query_slices,
        reference_subset,
        reference_sdf,
    )

    annotation_gates = verify_annotated_outputs(frozen)

    events, observations, accounting_rows = (
        parse_events_observations(frozen)
    )

    experiments, benchmark_runs = construct_registry_entities(
        frozen,
        runtime,
        padded_panel_sha,
        events,
        observations,
    )

    collections, schema_errors = validate_and_write_entities(
        paths,
        events,
        experiments,
        benchmark_runs,
        observations,
    )

    duck_counts = run_example_query(collections)

    checks = validate_phase2c(
        frozen,
        specs,
        annotation_gates,
        collections,
        schema_errors,
        padded_panel_sha,
        duck_counts,
    )

    write_final_report(
        frozen,
        collections,
        checks,
        padded_panel_sha,
    )

    forbid_large_sources_in_results(specs)

    archive_sha = package_archive()
    if archive_sha is None:
        raise RuntimeError(
            "Compact Phase 2C archive creation failed"
        )

    emit_status_once("PHASE2C_COMPUTE_PASS")


if __name__ == "__main__":
    try:
        main()
    except Phase2CAbort:
        package_archive()
        raise
    except Exception as exc:
        diagnostic = {
            "status": "PHASE2C_COMPUTE_FAIL",
            "captured_at": now_iso(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "runtime_identity": runtime_identity,
            "pipeline_abort_stage": PIPELINE_ABORT_STAGE,
        }
        (
            RESULTS_DIR / "blocked_or_failed_diagnostics.json"
        ).write_text(
            json.dumps(diagnostic, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        package_archive()
        emit_status_once("PHASE2C_COMPUTE_FAIL")
        raise
