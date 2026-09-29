from pathlib import Path
import base64
import hashlib
import json
import textwrap

ROOT = Path.cwd()
OUT = ROOT / "notebooks/project003_phase2c_colab.ipynb"
SHA_OUT = ROOT / "notebooks/project003_phase2c_colab.sha256"
RUNNER_PATH = ROOT / "scripts/phase2/run_phase2c_colab.py"
RUNNER_SHA_OUT = ROOT / "scripts/phase2/run_phase2c_colab.sha256"
EXPECTED_RUNNER_SHA256 = "eb1838e100e31cadbae052cc1f08c175208e9e6046ef4365efa36d4ba0b4a718"

required = [
    "environment/comparator-lock.yaml",
    "data/phase2/admitted_sources.tsv",
    "data/phase2/selected_assessable_segments.bed",
    "data/phase2/selected_intervals.tsv",
    "data/phase2/interval_panel.lock",
    "docs/phase2/phase2_protocol.md",
    "docs/phase2/phase2c_compute_protocol.md",
    "docs/phase2/phase2c_compute_protocol.lock",
    "docs/phase2/benchmark_run_schema_extension.lock",
    "data/manifests/selected_experiments.tsv",
    "schemas/event.schema.json",
    "schemas/observation.schema.json",
    "schemas/experiment.schema.json",
    "schemas/source_artifact.schema.json",
    "schemas/provenance_link.schema.json",
    "schemas/phase2/benchmark_run.schema.json",
]

missing = [rel for rel in required if not (ROOT / rel).exists()]
if not RUNNER_PATH.exists():
    missing.append(str(RUNNER_PATH.relative_to(ROOT)))
if missing:
    raise SystemExit("Missing required local files:\n" + "\n".join(missing))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse_lock(path):
    values = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            values[key] = value
    return values


compute_lock = parse_lock(ROOT / "docs/phase2/phase2c_compute_protocol.lock")
schema_lock = parse_lock(ROOT / "docs/phase2/benchmark_run_schema_extension.lock")

checks = {
    "compute_protocol": (
        ROOT / "docs/phase2/phase2c_compute_protocol.md",
        compute_lock["protocol_sha256"],
    ),
    "panel": (
        ROOT / "data/phase2/selected_assessable_segments.bed",
        compute_lock["selected_assessable_segments_sha256"],
    ),
    "phase2_run_schema": (
        ROOT / "schemas/phase2/benchmark_run.schema.json",
        schema_lock["schema_sha256"],
    ),
}

for name, (path, expected) in checks.items():
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{name} checksum mismatch: {actual} != {expected}")

runner_sha = sha256_file(RUNNER_PATH)
if runner_sha != EXPECTED_RUNNER_SHA256:
    raise RuntimeError(
        "Audited Phase 2C runner checksum mismatch: "
        f"{runner_sha} != {EXPECTED_RUNNER_SHA256}"
    )

# Syntax-check the exact runner bytes before embedding them.
runner_source = RUNNER_PATH.read_text(encoding="utf-8")
compile(runner_source, str(RUNNER_PATH), "exec")

RUNNER_SHA_OUT.parent.mkdir(parents=True, exist_ok=True)
RUNNER_SHA_OUT.write_text(
    f"{runner_sha}  {RUNNER_PATH.name}\n",
    encoding="utf-8",
)

embedded = {}
embedded_sha = {}
for rel in required:
    raw = (ROOT / rel).read_bytes()
    embedded[rel] = base64.b64encode(raw).decode("ascii")
    embedded_sha[rel] = hashlib.sha256(raw).hexdigest()

runner_b64 = base64.b64encode(RUNNER_PATH.read_bytes()).decode("ascii")


def lines(text):
    return [
        line + "\n"
        for line in textwrap.dedent(text).strip("\n").splitlines()
    ]


def md(text):
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": lines(text),
    }


def code(text):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": lines(text),
    }


cells = [
    md("""
    # OmicsEdgeBio Project 003 — Phase 2C Benchmark Expansion

    Frozen Phase 2C design:

    - HG003 + HG004
    - Illumina + Oxford Nanopore
    - 4 benchmark runs
    - 50 frozen windows
    - 541 assessable segments
    - 1,162,571 assessable bases
    - 19 chromosomes
    - chr20 excluded
    - hap.py 0.3.15 + RTG vcfeval 3.12.1

    Large genomic inputs remain in ephemeral Google Colab storage.

    The notebook embeds the frozen scientific configuration and the audited
    Phase 2C runner byte-for-byte. It does not require GitHub credentials or
    access to the private repository.

    **Safety gate:** `EXECUTE_COMPARISON` defaults to `False`.
    """),
    md("## 1. Runtime and execution gate"),
    code("""
    import base64
    import csv
    import hashlib
    import json
    import os
    import platform
    import shutil
    import subprocess
    import sys
    from pathlib import Path

    EXECUTE_COMPARISON = False

    WORK_ROOT = Path("/content/omicsedge_phase2c")
    CONFIG_DIR = WORK_ROOT / "authoritative_config"
    RUNNER_DIR = WORK_ROOT / "runner"
    RESULTS_DIR = Path("/content/omicsedge_phase2c_results")
    ARCHIVE_PATH = Path("/content/omicsedge_phase2c_results.tar.gz")

    for directory in (CONFIG_DIR, RUNNER_DIR, RESULTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)

    def mem_total_bytes():
        for raw in Path("/proc/meminfo").read_text().splitlines():
            if raw.startswith("MemTotal:"):
                return int(raw.split()[1]) * 1024
        return 0

    resources = {
        "architecture": platform.machine(),
        "logical_cpus": os.cpu_count() or 0,
        "ram_bytes": mem_total_bytes(),
        "free_bytes": shutil.disk_usage("/content").free,
        "python": sys.version,
    }
    print(json.dumps(resources, indent=2))

    errors = []
    if resources["architecture"] not in {"x86_64", "amd64"}:
        errors.append("requires linux/amd64")
    if resources["logical_cpus"] < 2:
        errors.append("requires at least 2 logical CPUs")
    if resources["ram_bytes"] < 7 * 1024**3:
        errors.append("requires at least 7 GiB RAM")
    if resources["free_bytes"] < 15 * 1024**3:
        errors.append("requires at least 15 GiB free temporary disk")
    if errors:
        raise RuntimeError("Phase 2C Colab preflight failed: " + "; ".join(errors))

    print("EXECUTE_COMPARISON =", EXECUTE_COMPARISON)
    """),
    md("## 2. Materialize and verify frozen Project 003 configuration"),
    code(f"""
    EMBEDDED_B64 = {embedded!r}
    EMBEDDED_SHA256 = {embedded_sha!r}

    for rel, payload in EMBEDDED_B64.items():
        raw = base64.b64decode(payload)
        actual = hashlib.sha256(raw).hexdigest()
        expected = EMBEDDED_SHA256[rel]
        if actual != expected:
            raise RuntimeError(f"embedded checksum mismatch: {{rel}}")
        target = CONFIG_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    def read_tsv(path):
        with open(path, newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle, delimiter="\\t"))

    admitted = read_tsv(CONFIG_DIR / "data/phase2/admitted_sources.tsv")
    if len(admitted) != 4:
        raise RuntimeError("Expected exactly four admitted Phase 2 sources")

    expected_candidates = {{
        "phase2-hg003-60z59",
        "phase2-hg003-ru88n",
        "phase2-hg004-60z59",
        "phase2-hg004-ru88n",
    }}
    observed_candidates = {{row["candidate_id"] for row in admitted}}
    if observed_candidates != expected_candidates:
        raise RuntimeError("Frozen Phase 2 admitted-source set changed")

    if any(
        row["performance_consulted_for_selection"].lower() != "false"
        for row in admitted
    ):
        raise RuntimeError("Outcome-independent source selection violated")

    if any(row["phase2a_admission_state"] != "ELIGIBLE" for row in admitted):
        raise RuntimeError("A non-eligible Phase 2 source is present")

    panel_path = CONFIG_DIR / "data/phase2/selected_assessable_segments.bed"
    panel = []
    for raw in panel_path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            fields = raw.split("\\t")
            panel.append((fields[0], int(fields[1]), int(fields[2])))

    panel_bases = sum(end - start for _, start, end in panel)
    chromosomes = sorted({{chrom for chrom, _, _ in panel}})

    if len(panel) != 541:
        raise RuntimeError(f"Expected 541 panel segments, found {{len(panel)}}")
    if panel_bases != 1162571:
        raise RuntimeError(
            f"Expected 1162571 assessable bases, found {{panel_bases}}"
        )
    if len(chromosomes) != 19:
        raise RuntimeError(f"Expected 19 chromosomes, found {{len(chromosomes)}}")
    if "chr20" in chromosomes:
        raise RuntimeError("chr20 is forbidden in Phase 2C")

    print("FROZEN_PHASE2C_CONFIGURATION_PASS")
    print(json.dumps({{
        "runs": len(admitted),
        "segments": len(panel),
        "assessable_bases": panel_bases,
        "chromosomes": chromosomes,
        "embedded_files": len(EMBEDDED_B64),
    }}, indent=2))
    """),
    md("""
    ## 3. Materialize the audited Phase 2C runner

    The runner is embedded in this notebook at generation time. Its SHA-256
    must match the locally audited runner before it can be written or executed.
    """),
    code(f"""
    RUNNER_B64 = {runner_b64!r}
    EXPECTED_RUNNER_SHA256 = {runner_sha!r}

    runner_bytes = base64.b64decode(RUNNER_B64)
    runner_sha = hashlib.sha256(runner_bytes).hexdigest()
    if runner_sha != EXPECTED_RUNNER_SHA256:
        raise RuntimeError(
            "Embedded Phase 2C runner checksum mismatch: "
            f"{{runner_sha}} != {{EXPECTED_RUNNER_SHA256}}"
        )

    RUNNER = RUNNER_DIR / "run_phase2c_colab.py"
    RUNNER.write_bytes(runner_bytes)
    RUNNER.chmod(0o755)

    compile(
        RUNNER.read_text(encoding="utf-8"),
        str(RUNNER),
        "exec",
    )

    print("RUNNER_MATERIALIZATION_PASS")
    print("runner:", RUNNER)
    print("runner SHA-256:", runner_sha)
    """),
    md("""
    ## 4. Execute Phase 2C

    This is the only cell that starts package installation, public genomic
    downloads, hap.py/vcfeval, evidence materialization, and result packaging.

    Leave `EXECUTE_COMPARISON = False` until the complete Phase 2C pre-compute
    package has been committed and pushed.
    """),
    code("""
    if not EXECUTE_COMPARISON:
        raise RuntimeError(
            "EXECUTE_COMPARISON is False. The frozen Phase 2C pre-compute "
            "package must be committed and pushed before genomic compute."
        )

    completed = subprocess.run(
        [sys.executable, str(RUNNER)],
        text=True,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            f"Phase 2C runner failed with exit code {completed.returncode}"
        )

    if not ARCHIVE_PATH.exists():
        raise RuntimeError(
            "Phase 2C runner completed without producing the compact archive"
        )

    archive_sha = hashlib.sha256(ARCHIVE_PATH.read_bytes()).hexdigest()
    print("PHASE2C_RUNNER_EXECUTION_PASS")
    print("archive:", ARCHIVE_PATH)
    print("archive size:", ARCHIVE_PATH.stat().st_size)
    print("archive SHA-256:", archive_sha)
    """),
    md("""
    ## 5. Download compact result archive

    Run only after the execution cell finishes with `PHASE2C_COMPUTE_PASS` and
    `PHASE2C_RUNNER_EXECUTION_PASS`.
    """),
    code("""
    if not EXECUTE_COMPARISON:
        raise RuntimeError("Phase 2C compute has not been enabled")
    if not ARCHIVE_PATH.exists():
        raise RuntimeError("Phase 2C compact result archive is absent")

    from google.colab import files
    files.download(str(ARCHIVE_PATH))
    """),
    md("""
    ## Scientific boundary

    Phase 2C creates run-scoped benchmark evidence only. It does not merge
    events across runs or assert biological identity. Phase 2D applies the
    frozen biological identity layer, and Phase 2E evaluates the final
    20-criterion Phase 2 gate.
    """),
]

for index, cell in enumerate(cells):
    if cell["cell_type"] == "code":
        compile(
            "".join(cell["source"]),
            f"<phase2c-cell-{index}>",
            "exec",
        )

notebook = {
    "cells": cells,
    "metadata": {
        "accelerator": "CPU",
        "colab": {
            "name": "project003_phase2c_colab.ipynb",
            "provenance": [],
        },
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    json.dumps(notebook, indent=1, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

loaded = json.loads(OUT.read_text(encoding="utf-8"))
if loaded["nbformat"] != 4:
    raise RuntimeError("Notebook JSON validation failed")
if len(loaded["cells"]) != len(cells):
    raise RuntimeError("Notebook cell-count validation failed")

notebook_text = "\n".join(
    "".join(cell.get("source", []))
    for cell in loaded["cells"]
)

notebook_code = "\n".join(
    "".join(cell.get("source", []))
    for cell in loaded["cells"]
    if cell.get("cell_type") == "code"
)

required_tokens = [
    "EXECUTE_COMPARISON = False",
    "phase2-hg003-60z59",
    "phase2-hg003-ru88n",
    "phase2-hg004-60z59",
    "phase2-hg004-ru88n",
    "selected_assessable_segments.bed",
    "run_phase2c_colab.py",
    "RUNNER_MATERIALIZATION_PASS",
    "PHASE2C_RUNNER_EXECUTION_PASS",
    EXPECTED_RUNNER_SHA256,
]
for token in required_tokens:
    if token not in notebook_text:
        raise RuntimeError("Missing notebook token: " + token)

for forbidden in [
    "run-phase1a-",
    "CORE =",
    "PADDED =",
    "cross_run_candidates.tsv",
    "PHASE2C_RUNNER_MISSING",
]:
    if forbidden in notebook_text:
        raise RuntimeError("Forbidden stale/Phase 1 token in notebook: " + forbidden)

if notebook_code.count("EXECUTE_COMPARISON = False") != 1:
    raise RuntimeError("Execution safety gate assignment is not unique in code cells")

if "EXECUTE_COMPARISON = True" in notebook_code:
    raise RuntimeError("Execution safety gate is enabled in generated notebook")

notebook_sha = sha256_file(OUT)
SHA_OUT.write_text(
    f"{notebook_sha}  {OUT.name}\n",
    encoding="utf-8",
)

print("=" * 78)
print("PROJECT 003 — PHASE 2C COLAB NOTEBOOK INTEGRATION BUILD")
print("=" * 78)
print("Notebook:", OUT)
print("Cells:", len(cells))
print("Notebook bytes:", OUT.stat().st_size)
print("Notebook SHA-256:", notebook_sha)
print("Notebook SHA manifest:", SHA_OUT)
print("Runner SHA-256:", runner_sha)
print("Runner SHA manifest:", RUNNER_SHA_OUT)
print("Embedded authoritative files:", len(embedded))
print("Frozen panel SHA-256:", checks["panel"][1])
print("Phase 2 run schema SHA-256:", checks["phase2_run_schema"][1])
print("Code-cell syntax validation: PASS")
print("Runner syntax validation: PASS")
print("Runner embedded byte-for-byte: PASS")
print("Execution gate default False: PASS")
print("No GitHub/private-repository dependency: PASS")
print("No stale runner-missing gate: PASS")
print("No Phase 1 single-interval contract: PASS")
print()
print("PHASE2C_COLAB_RUNNER_INTEGRATION_PASS")
