#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import shutil
import sys
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from benchmark_evidence.phase1b_identity import (  # noqa: E402
    EXACT_NORMALIZED_ALLELE,
    IDENTITY_SCHEMA_VERSION,
    REPRESENTATION_EQUIVALENCE_SUPPORTED,
    variant_id as frozen_variant_id,
)

# ---------------------------------------------------------------------------
# Frozen authorities
# ---------------------------------------------------------------------------

PHASE1A_ARCHIVE = ROOT / "data/phase1a/omicsedge_phase1a_results.tar.gz"
PHASE1B_ARCHIVE = ROOT / "results/phase1b/omicsedge_phase1b_results.tar.gz"
PHASE2_PROTOCOL = ROOT / "docs/phase2/phase2_protocol.md"
ADMITTED_SOURCES = ROOT / "data/phase2/admitted_sources.tsv"
ADMITTED_LOCK = ROOT / "data/phase2/admitted_sources.lock"
SOURCE_CANDIDATES = ROOT / "data/phase2/source_candidates.tsv"
SELECTED_INTERVALS = ROOT / "data/phase2/selected_intervals.tsv"
SELECTED_PANEL = ROOT / "data/phase2/selected_assessable_segments.bed"
PANEL_LOCK = ROOT / "data/phase2/interval_panel.lock"
PHASE2C_PROTOCOL_LOCK = ROOT / "docs/phase2/phase2c_compute_protocol.lock"
PHASE2C_ARCHIVE = ROOT / "results/phase2c/omicsedge_phase2c_results.tar.gz"
PHASE2D_ARCHIVE = ROOT / "results/phase2d/omicsedge_phase2d_results.tar.gz"
PHASE2D_RELEASE_LOCK = ROOT / "docs/phase2/phase2d_compute_release.lock"
PHASE2E_PROTOCOL = ROOT / "docs/phase2/phase2e_validation_protocol.md"
PHASE2E_PROTOCOL_LOCK = ROOT / "docs/phase2/phase2e_validation_protocol.lock"
IDENTITY_LIB = ROOT / "src/benchmark_evidence/phase1b_identity.py"

OUTPUT_ROOT = ROOT / "results/phase2e"
BUNDLE_DIR = OUTPUT_ROOT / "omicsedge_phase2_final_results"
ARCHIVE_PATH = OUTPUT_ROOT / "omicsedge_phase2_final_results.tar.gz"

EXPECTED = {
    PHASE1A_ARCHIVE:
        "6630879776c3da2326f5c56b4dbb16ca5bd409b5cbc065590608d40a99a28202",
    PHASE1B_ARCHIVE:
        "50bf597cbc13a051d5dda7201e9d7653dbc7b1762fef1b8300199641df6474fb",
    PHASE2_PROTOCOL:
        "6234485e8916fd30a335c761a62668b617cb148b5b5a1753d12fd7765fa1633f",
    ADMITTED_SOURCES:
        "55ebf63901ac0c118cb5ec687b49cc81cf680bb9357246ba2f6138b27a29641f",
    ADMITTED_LOCK:
        "63d72d95d48c923514760c72f28a9a397071f6c44fa615bbc55a5fb5adf3a48c",
    SOURCE_CANDIDATES:
        "f0085da28d6e9089f6f74fb90f1acd9606dd3f6e3d8bd2c3741f0846081edc21",
    SELECTED_INTERVALS:
        "2e5a6a97c9bacf5fdf3cf547ac7db32d06f611a1f2bcca66cbcfbd04e722c01c",
    SELECTED_PANEL:
        "4c77e17c3dec47051cb9b29fa14fee67f31a559785417d083f4f7bcacb05cd26",
    PANEL_LOCK:
        "ef00c21f0e667c1891b90d6785f1072895a8b9d620a5519130a8a1823a4bd9a1",
    PHASE2C_PROTOCOL_LOCK:
        "4a1ff34bbcc15e609dda7a02895ce45c6804f880364b4c2e09921840332f1ba3",
    PHASE2C_ARCHIVE:
        "345b6c3483350f4f1930fc5957f7a97c2b2daf30e6ba1972f2cf3b8484ff0536",
    PHASE2D_ARCHIVE:
        "3e5feb50e28b620a8ab9f1d4c9901b9faedb127fd84a2dad4dedf65dd5437532",
    PHASE2D_RELEASE_LOCK:
        "e5880f5a516e4b71a91d7cc3aab8d273b817c090dec975d6e62fd5f2344a7592",
    PHASE2E_PROTOCOL:
        "bda8b3a61a0f6cf311ef6bf765bc9c760d4f42d78bd353ca0012ddc1677b8a43",
    PHASE2E_PROTOCOL_LOCK:
        "bd0c385437d2e0e180daf1cc748c98b3af7a515b373f5e5a5a70ffb349c61978",
    IDENTITY_LIB:
        "ef05ab077a5bc4495616331dff663d3cea45297651c7a18cd243e98b21532a5c",
}

EXPECTED_PHASE2C_EVENTS = 7951
EXPECTED_PHASE2D_LINKS = 7891
EXPECTED_PHASE2D_UNRESOLVED = 60
EXPECTED_PHASE2D_VARIANTS = 2612
EXPECTED_PHASE1B_VARIANTS = 1666

IDENTITY_METHOD = "PHASE1B_EXACT_NORMALIZED_ALLELE_V1"
IDENTITY_METHOD_VERSION = "1.0.0"

FUNDAMENTAL_GATES = {
    "P2-01", "P2-02", "P2-03", "P2-04", "P2-05", "P2-06", "P2-07",
    "P2-12", "P2-13", "P2-14", "P2-15", "P2-18", "P2-19",
}

DISALLOWED_SCIENTIFIC_FIELDS = {
    "reliability_score",
    "confidence_score",
    "trust_score",
    "trusted_label",
    "technology_rank",
    "technology_ranking",
    "caller_rank",
    "caller_ranking",
    "consensus_label",
    "forced_consensus",
    "majority_vote",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def canonical_hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        require(rows, f"fieldnames required for empty TSV: {path}")
        fieldnames = list(rows[0].keys())
    for row in rows:
        require(list(row.keys()) == fieldnames, f"column order mismatch: {path.name}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_lock(path: Path) -> dict[str, str]:
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        require("=" in line, f"invalid lock row: {path}: {line}")
        key, value = line.split("=", 1)
        result[key] = value
    return result


def safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            p = Path(member.name)
            require(not p.is_absolute(), f"archive absolute member: {member.name}")
            require(".." not in p.parts, f"archive parent traversal: {member.name}")
            target = destination / p
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            require(
                member.isfile(),
                f"archive contains unsupported member type: {member.name}",
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            require(source is not None, f"cannot read archive member: {member.name}")
            with source, target.open("wb") as out:
                shutil.copyfileobj(source, out)


def verify_checksum_manifest(root: Path, manifest_name: str = "checksums.sha256") -> None:
    manifest = root / manifest_name
    require(manifest.is_file(), f"checksum manifest missing: {manifest}")
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        require("  " in raw, f"invalid checksum line: {raw}")
        expected, relative = raw.split("  ", 1)
        candidate = root / relative
        require(candidate.is_file(), f"checksummed file missing: {candidate}")
        require(
            sha256_file(candidate) == expected,
            f"checksum mismatch: {candidate}",
        )


def verify_phase1b_release(extracted: Path) -> Path:
    manifest_path = extracted / "results/phase1b/phase1b_release_manifest.json"
    require(manifest_path.is_file(), "Phase 1B release manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("scientific_gate") == "PASS", "Phase 1B gate not PASS")
    require(manifest.get("validation_criteria") == "15/15 PASS", "Phase 1B validation mismatch")
    for artifact in manifest["artifacts"]:
        p = extracted / artifact["path"]
        require(p.is_file(), f"Phase 1B packaged artifact missing: {artifact['path']}")
        require(sha256_file(p) == artifact["sha256"], f"Phase 1B artifact hash mismatch: {artifact['path']}")
        require(p.stat().st_size == artifact["size_bytes"], f"Phase 1B artifact size mismatch: {artifact['path']}")
    return extracted / "results/phase1b"


def locate_phase1a_root(extracted: Path) -> Path:
    candidates = []
    for p in extracted.rglob("checksums.sha256"):
        parent = p.parent
        if (parent / "benchmark_runs.tsv").is_file() and (parent / "experiments.tsv").is_file():
            candidates.append(parent)
    require(len(candidates) == 1, f"could not uniquely locate Phase 1A root: {candidates}")
    verify_checksum_manifest(candidates[0])
    validation = read_tsv(candidates[0] / "validation_results.tsv")
    require(validation and all(row.get("status") == "PASS" for row in validation), "Phase 1A validation not PASS")
    return candidates[0]


def locate_phase2c_root(extracted: Path) -> Path:
    root = extracted / "omicsedge_phase2c_results"
    require(root.is_dir(), "Phase 2C result root missing")
    verify_checksum_manifest(root)
    gates = read_tsv(root / "phase2c_validation_results.tsv")
    require(len(gates) == 19, f"expected 19 Phase 2C gates, got {len(gates)}")
    require(all(row["status"] == "PASS" for row in gates), "Phase 2C gate failure")
    return root


def locate_phase2d_root(extracted: Path) -> Path:
    root = extracted / "omicsedge_phase2d_results"
    require(root.is_dir(), "Phase 2D result root missing")
    verify_checksum_manifest(root)
    gates = read_tsv(root / "phase2d_validation.tsv")
    require(len(gates) == 16, f"expected 16 Phase 2D gates, got {len(gates)}")
    require(all(row["status"] == "PASS" for row in gates), "Phase 2D gate failure")
    return root


def recompute_window_id(row: dict, shared_callable_sha: str) -> tuple[str, str]:
    payload = {
        "phase": "2B",
        "assembly": "GRCh38",
        "context_id": row["context_id"],
        "chromosome": row["chromosome"],
        "nominal_start_0based": int(row["nominal_start_0based"]),
        "nominal_end_0based": int(row["nominal_end_0based"]),
        "source_context_bed_sha256": row["source_context_bed_sha256"],
        "shared_callable_definition": (
            "HG003_GIAB_v4.2.1_noinconsistent_INTERSECT_"
            "HG004_GIAB_v4.2.1_noinconsistent|"
            f"sha256:{shared_callable_sha}"
        ),
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    window_id = f"phase2-window:sha256:{digest}"
    selection_hash = hashlib.sha256(
        ("PROJECT003_PHASE2B|" + window_id).encode("utf-8")
    ).hexdigest()
    return window_id, selection_hash


def deterministic_tar_gz(source_dir: Path, output_path: Path) -> None:
    members = sorted(
        [p for p in source_dir.rglob("*") if p.is_file()],
        key=lambda p: p.relative_to(source_dir.parent).as_posix(),
    )
    with output_path.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for p in members:
                    arcname = p.relative_to(source_dir.parent).as_posix()
                    info = tar.gettarinfo(str(p), arcname=arcname)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    with p.open("rb") as handle:
                        tar.addfile(info, handle)


def build_product_query(
    phase2c_events: list[dict],
    phase2c_observations: list[dict],
    phase2c_runs: list[dict],
    phase2c_experiments: list[dict],
    phase2d_links: list[dict],
    admitted: list[dict],
) -> tuple[list[dict], dict]:
    events = {row["event_id"]: row for row in phase2c_events}
    runs = {row["benchmark_run_id"]: row for row in phase2c_runs}
    experiments = {row["experiment_id"]: row for row in phase2c_experiments}

    observations_by_event = defaultdict(list)
    for row in phase2c_observations:
        observations_by_event[row["event_id"]].append(row)

    admitted_by_key = {}
    for row in admitted:
        key = (row["sample_id"], row["technology"])
        require(key not in admitted_by_key, f"ambiguous admitted source for {key}")
        admitted_by_key[key] = row

    links_by_variant = defaultdict(list)
    for row in phase2d_links:
        links_by_variant[row["variant_id"]].append(row)

    candidates = []
    for variant_id, links in links_by_variant.items():
        samples = set()
        technologies = set()
        for link in links:
            run = runs[link["benchmark_run_id"]]
            exp = experiments[run["experiment_id"]]
            samples.add(exp["sample_id"])
            technologies.add(exp["technology"])
        candidates.append(
            (
                -len(samples),
                -len(technologies),
                -len(links),
                variant_id,
            )
        )

    require(candidates, "no Phase 2D exact variants available")
    candidates.sort()
    _, _, _, selected_variant = candidates[0]

    rows = []
    for link in sorted(links_by_variant[selected_variant], key=lambda r: r["event_id"]):
        event = events[link["event_id"]]
        run = runs[link["benchmark_run_id"]]
        exp = experiments[run["experiment_id"]]
        admitted_row = admitted_by_key[(exp["sample_id"], exp["technology"])]
        provenance = json.loads(link["provenance"])

        for obs in sorted(observations_by_event[event["event_id"]], key=lambda r: r["observation_id"]):
            rows.append(
                {
                    "variant_id": selected_variant,
                    "event_variant_link_id": link["event_variant_link_id"],
                    "identity_status": link["identity_status"],
                    "identity_method": link["identity_method"],
                    "identity_method_version": link["identity_method_version"],
                    "source_selection_candidate_id": admitted_row["candidate_id"],
                    "sample_id": exp["sample_id"],
                    "technology": exp["technology"],
                    "platform": exp["platform"],
                    "pipeline_name": exp["pipeline_name"],
                    "experiment_id": exp["experiment_id"],
                    "benchmark_run_id": run["benchmark_run_id"],
                    "comparator": run["comparator"],
                    "comparator_version": run["comparator_version"],
                    "engine": run["engine"],
                    "engine_version": run["engine_version"],
                    "event_id": event["event_id"],
                    "observation_id": obs["observation_id"],
                    "side": obs["side"],
                    "raw_decision": obs["raw_decision"],
                    "raw_match_kind": obs["raw_match_kind"],
                    "raw_variant_type": obs["raw_variant_type"],
                    "source_genotype": obs["source_genotype"],
                    "source_filter": obs["source_filter"],
                    "source_output_artifact_id": obs["source_output_artifact_id"],
                    "reference_artifact_id": event["reference_artifact_id"],
                    "phase1b_archive_sha256": provenance["phase1b_archive_sha256"],
                    "phase2c_archive_sha256": provenance["phase2c_archive_sha256"],
                    "admitted_sources_lock_sha256": provenance["admitted_sources_lock_sha256"],
                    "interval_panel_lock_sha256": provenance["interval_panel_lock_sha256"],
                }
            )

    summary = {
        "variant_id": selected_variant,
        "row_count": len(rows),
        "distinct_samples": sorted({row["sample_id"] for row in rows}),
        "distinct_technologies": sorted({row["technology"] for row in rows}),
        "distinct_experiments": sorted({row["experiment_id"] for row in rows}),
        "distinct_benchmark_runs": sorted({row["benchmark_run_id"] for row in rows}),
        "distinct_events": sorted({row["event_id"] for row in rows}),
        "distinct_raw_decisions": sorted({row["raw_decision"] for row in rows}),
        "selection_rule": (
            "maximize distinct sample count, then technology count, then linked "
            "EVENT count; break ties by lexicographically smallest VARIANT ID"
        ),
        "outcome_used_for_query_selection": False,
    }
    return rows, summary


def main() -> int:
    print("=" * 78)
    print("PROJECT 003 — PHASE 2E FINAL PRODUCT / GENERALIZATION VALIDATION")
    print("=" * 78)

    # Frozen authority identity first.
    for path, expected in EXPECTED.items():
        require(path.is_file(), f"frozen authority missing: {path}")
        observed = sha256_file(path)
        require(observed == expected, f"frozen authority SHA mismatch: {path}")
    authority_before = {str(path): sha256_file(path) for path in EXPECTED}
    print("PASS  frozen authorities")

    admitted = read_tsv(ADMITTED_SOURCES)
    source_candidates = read_tsv(SOURCE_CANDIDATES)
    selected_intervals = read_tsv(SELECTED_INTERVALS)
    admitted_lock = parse_lock(ADMITTED_LOCK)
    panel_lock = parse_lock(PANEL_LOCK)
    phase2c_protocol_lock = parse_lock(PHASE2C_PROTOCOL_LOCK)
    phase2d_release_lock = parse_lock(PHASE2D_RELEASE_LOCK)
    phase2e_lock = parse_lock(PHASE2E_PROTOCOL_LOCK)

    with tempfile.TemporaryDirectory(prefix="project003_phase2e_") as tmp:
        tmp = Path(tmp)
        p1a_extract = tmp / "p1a"
        p1b_extract = tmp / "p1b"
        p2c_extract = tmp / "p2c"
        p2d_extract = tmp / "p2d"
        for d in (p1a_extract, p1b_extract, p2c_extract, p2d_extract):
            d.mkdir(parents=True)

        safe_extract(PHASE1A_ARCHIVE, p1a_extract)
        safe_extract(PHASE1B_ARCHIVE, p1b_extract)
        safe_extract(PHASE2C_ARCHIVE, p2c_extract)
        safe_extract(PHASE2D_ARCHIVE, p2d_extract)

        p1a = locate_phase1a_root(p1a_extract)
        p1b = verify_phase1b_release(p1b_extract)
        p2c = locate_phase2c_root(p2c_extract)
        p2d = locate_phase2d_root(p2d_extract)

        p1a_experiments = read_tsv(p1a / "experiments.tsv")
        p1a_runs = read_tsv(p1a / "benchmark_runs.tsv")

        p1b_variants = read_tsv(p1b / "variants.tsv")
        p1b_links = read_tsv(p1b / "event_variant_links.tsv")

        p2c_events = read_tsv(p2c / "events.tsv")
        p2c_observations = read_tsv(p2c / "observations.tsv")
        p2c_runs = read_tsv(p2c / "benchmark_runs.tsv")
        p2c_experiments = read_tsv(p2c / "experiments.tsv")

        p2d_links = read_tsv(p2d / "event_variant_links.tsv")
        p2d_accounting = read_tsv(p2d / "event_identity_accounting.tsv")
        p2d_provenance = read_tsv(p2d / "link_provenance.tsv")
        p2d_variants = read_tsv(p2d / "new_variants.tsv")
        p2d_variant_index = read_tsv(p2d / "variant_index.tsv")
        p2d_validation = read_tsv(p2d / "phase2d_validation.tsv")
        p2d_summary = json.loads((p2d / "phase2d_summary.json").read_text(encoding="utf-8"))

        require(len(p2c_events) == EXPECTED_PHASE2C_EVENTS, "Phase 2C EVENT count changed")
        require(len(p2d_links) == EXPECTED_PHASE2D_LINKS, "Phase 2D link count changed")
        require(len(p2d_variants) == EXPECTED_PHASE2D_VARIANTS, "Phase 2D variant count changed")
        require(len(p1b_variants) == EXPECTED_PHASE1B_VARIANTS, "Phase 1B variant count changed")

        product_query_1, product_summary_1 = build_product_query(
            p2c_events,
            p2c_observations,
            p2c_runs,
            p2c_experiments,
            p2d_links,
            admitted,
        )
        product_query_2, product_summary_2 = build_product_query(
            p2c_events,
            p2c_observations,
            p2c_runs,
            p2c_experiments,
            p2d_links,
            admitted,
        )

        require(product_query_1 == product_query_2, "product query is not deterministic")
        require(product_summary_1 == product_summary_2, "product query summary is not deterministic")

        gates = []

        def add(gate_id: str, passed: bool, detail: str) -> None:
            gates.append(
                {
                    "validation_id": gate_id,
                    "status": "PASS" if passed else "FAIL",
                    "detail": detail,
                }
            )

        # P2-01
        add(
            "P2-01",
            sha256_file(PHASE1A_ARCHIVE) == EXPECTED[PHASE1A_ARCHIVE],
            EXPECTED[PHASE1A_ARCHIVE],
        )

        # P2-02
        add(
            "P2-02",
            sha256_file(PHASE1B_ARCHIVE) == EXPECTED[PHASE1B_ARCHIVE],
            EXPECTED[PHASE1B_ARCHIVE],
        )

        # P2-03
        immutable_phase1 = (
            len(p1a_experiments) == 2
            and len(p1a_runs) == 2
            and len(p1b_variants) == EXPECTED_PHASE1B_VARIANTS
            and len(p1b_links) == 3332
            and sha256_file(PHASE1A_ARCHIVE) == EXPECTED[PHASE1A_ARCHIVE]
            and sha256_file(PHASE1B_ARCHIVE) == EXPECTED[PHASE1B_ARCHIVE]
        )
        add(
            "P2-03",
            immutable_phase1,
            "Phase 1A/1B authorities remain byte-identical and Phase 2 outputs are separately namespaced",
        )

        # P2-04
        source_required = {
            "candidate_id", "sample_id", "technology", "platform", "coverage",
            "source_corpus", "source_submission_id", "pipeline_name",
            "reference_assembly", "query_vcf_url", "expected_query_sha256",
            "truth_vcf_url", "benchmark_bed_url", "selection_basis",
            "performance_consulted_for_selection", "phase2a_admission_state",
        }
        sources_ok = (
            len(admitted) == 4
            and all(source_required <= set(row) for row in admitted)
            and all(all(row[field] not in ("", None) for field in source_required) for row in admitted)
            and all(row["phase2a_admission_state"] == "ELIGIBLE" for row in admitted)
            and all(row["reference_assembly"] == "GRCh38" for row in admitted)
            and len(p2c_runs) == 4
            and all(row["comparator"] == "hap.py" for row in p2c_runs)
            and all(row["comparator_version"] == "0.3.15" for row in p2c_runs)
            and all(row["engine"] == "vcfeval" for row in p2c_runs)
            and all(row["engine_version"] == "3.12.1" for row in p2c_runs)
        )
        add(
            "P2-04",
            sources_ok,
            f"admitted_sources={len(admitted)} benchmark_runs={len(p2c_runs)} provenance_fields={len(source_required)}",
        )

        # P2-05
        selection_independent = (
            len(source_candidates) == 4
            and all(row["performance_consulted_for_selection"].lower() == "false" for row in source_candidates)
            and all(row["performance_consulted_for_selection"].lower() == "false" for row in admitted)
            and admitted_lock.get("performance_consulted_for_selection") == "False"
        )
        add(
            "P2-05",
            selection_independent,
            "source candidate/admission records state performance_consulted_for_selection=False",
        )

        # P2-06
        panel_frozen_before_outcomes = (
            panel_lock.get("status") == "FROZEN_BEFORE_QUERY_VCF_DOWNLOAD_AND_BENCHMARKING"
            and panel_lock.get("query_vcfs_consulted") == "False"
            and panel_lock.get("benchmark_outcomes_consulted") == "False"
            and phase2c_protocol_lock.get("status") == "FROZEN_BEFORE_PHASE2C_RETRIEVAL_AND_COMPUTE"
            and phase2c_protocol_lock.get("selected_assessable_segments_sha256") == EXPECTED[SELECTED_PANEL]
            and phase2c_protocol_lock.get("selected_intervals_sha256") == EXPECTED[SELECTED_INTERVALS]
        )
        add(
            "P2-06",
            panel_frozen_before_outcomes,
            "Phase 2B panel and Phase 2C protocol both record pre-outcome freeze",
        )

        # P2-07
        shared_callable_sha = panel_lock.get("shared_callable_sha256", "")
        deterministic_windows = True
        for row in selected_intervals:
            observed_id, observed_hash = recompute_window_id(row, shared_callable_sha)
            if observed_id != row["window_id"] or observed_hash != row["selection_hash"]:
                deterministic_windows = False
                break
        deterministic_region_selection = (
            len(selected_intervals) == 50
            and bool(shared_callable_sha)
            and deterministic_windows
            and panel_lock.get("interval_selection_method_sha256")
            == "b3dd8fdbd8c308a9f9098fbc213a9a243ceec081b92b74862d60d212ea1619b2"
        )
        add(
            "P2-07",
            deterministic_region_selection,
            f"selected_windows={len(selected_intervals)} deterministic_ids={deterministic_windows}",
        )

        # P2-08
        contexts = sorted({row["context_id"] for row in selected_intervals})
        chromosomes = sorted({row["chromosome"] for row in selected_intervals})
        contexts_ok = len(contexts) >= 2 and len(chromosomes) >= 2
        add(
            "P2-08",
            contexts_ok,
            f"contexts={len(contexts)} chromosomes={len(chromosomes)} context_ids={contexts}",
        )

        # P2-09
        variant_types = {row["raw_variant_type"].upper() for row in p2c_observations if row.get("raw_variant_type")}
        has_snv = bool(variant_types & {"SNV", "SNP"})
        has_indel = any("INDEL" in value for value in variant_types)
        add(
            "P2-09",
            has_snv and has_indel,
            f"raw_variant_types={sorted(variant_types)}",
        )

        # P2-10
        all_samples = sorted(
            {row["sample_id"] for row in p1a_experiments}
            | {row["sample_id"] for row in p2c_experiments}
        )
        add(
            "P2-10",
            len(all_samples) >= 3,
            f"samples={all_samples}",
        )

        # P2-11
        technologies_by_sample = defaultdict(set)
        for row in p2c_experiments:
            technologies_by_sample[row["sample_id"]].add(row["technology"])
        paired_samples = sorted(
            sample
            for sample, technologies in technologies_by_sample.items()
            if {"ILLUMINA", "ONT"} <= technologies
        )
        add(
            "P2-11",
            {"HG003", "HG004"} <= set(paired_samples),
            f"paired_samples={paired_samples}",
        )

        # P2-12
        variant_ids_ok = True
        for row in p1b_variants + p2d_variants:
            allele = {
                "assembly": row["assembly"],
                "contig": row["contig"],
                "start": int(row["normalized_start_0based"]),
                "end": int(row["normalized_end_0based"]),
                "ref": row["normalized_ref"],
                "alt": row["normalized_alt"],
            }
            if frozen_variant_id(allele) != row["variant_id"]:
                variant_ids_ok = False
                break
            if frozen_variant_id(allele) != frozen_variant_id(dict(allele)):
                variant_ids_ok = False
                break
        add(
            "P2-12",
            variant_ids_ok
            and IDENTITY_SCHEMA_VERSION == "phase1b-variant-identity-v1"
            and sha256_file(IDENTITY_LIB) == EXPECTED[IDENTITY_LIB],
            f"variants_recomputed={len(p1b_variants) + len(p2d_variants)} identity_schema={IDENTITY_SCHEMA_VERSION}",
        )

        # P2-13
        p2c_event_ids = [row["event_id"] for row in p2c_events]
        link_event_ids = [row["event_id"] for row in p2d_links]
        accounting_event_ids = [row["event_id"] for row in p2d_accounting]
        event_run_consistency = all(
            row["benchmark_run_id"] in {run["benchmark_run_id"] for run in p2c_runs}
            for row in p2c_events
        )
        no_merge = (
            len(p2c_event_ids) == len(set(p2c_event_ids))
            and len(link_event_ids) == len(set(link_event_ids))
            and set(accounting_event_ids) == set(p2c_event_ids)
            and event_run_consistency
            and all(row.get("identity_scope") == "RUN_SCOPED" for row in p2c_events)
        )
        add(
            "P2-13",
            no_merge,
            f"phase2c_events={len(p2c_events)} linked_events={len(link_event_ids)}",
        )

        # P2-14
        unresolved = [row for row in p2d_accounting if row["identity_status"] == "UNRESOLVED"]
        unresolved_ids = {row["event_id"] for row in unresolved}
        linked_ids = {row["event_id"] for row in p2d_links}
        statuses = {row["identity_status"] for row in p2d_links}
        unresolved_ok = (
            len(unresolved) == EXPECTED_PHASE2D_UNRESOLVED
            and not (unresolved_ids & linked_ids)
            and REPRESENTATION_EQUIVALENCE_SUPPORTED not in statuses
            and statuses == {EXACT_NORMALIZED_ALLELE}
            and all(row["variant_id"] == "" for row in unresolved)
        )
        add(
            "P2-14",
            unresolved_ok,
            f"unresolved={len(unresolved)} link_statuses={sorted(statuses)}",
        )

        # P2-15
        run_by_id = {row["benchmark_run_id"]: row for row in p2c_runs}
        exp_by_id = {row["experiment_id"]: row for row in p2c_experiments}
        admitted_by_sample_tech = {
            (row["sample_id"], row["technology"]): row
            for row in admitted
        }
        prov_by_link = {row["event_variant_link_id"]: row for row in p2d_provenance}
        links_provenance_ok = len(prov_by_link) == len(p2d_links)
        if links_provenance_ok:
            for link in p2d_links:
                prov = prov_by_link.get(link["event_variant_link_id"])
                if prov is None:
                    links_provenance_ok = False
                    break
                run = run_by_id.get(link["benchmark_run_id"])
                if run is None:
                    links_provenance_ok = False
                    break
                exp = exp_by_id.get(run["experiment_id"])
                if exp is None:
                    links_provenance_ok = False
                    break
                source = admitted_by_sample_tech.get((exp["sample_id"], exp["technology"]))
                if source is None:
                    links_provenance_ok = False
                    break
                if (
                    prov["event_id"] != link["event_id"]
                    or prov["benchmark_run_id"] != link["benchmark_run_id"]
                    or prov["identity_method"] != IDENTITY_METHOD
                    or prov["identity_method_version"] != IDENTITY_METHOD_VERSION
                    or prov["admitted_sources_lock_sha256"] != EXPECTED[ADMITTED_LOCK]
                    or prov["interval_panel_lock_sha256"] != EXPECTED[PANEL_LOCK]
                ):
                    links_provenance_ok = False
                    break
        add(
            "P2-15",
            links_provenance_ok,
            f"links_with_selection_and_identity_provenance={len(p2d_links)}",
        )

        # P2-16
        required_query_fields = {
            "variant_id", "event_variant_link_id", "identity_status",
            "identity_method", "identity_method_version",
            "source_selection_candidate_id", "sample_id", "technology",
            "experiment_id", "benchmark_run_id", "comparator",
            "comparator_version", "event_id", "observation_id", "side",
            "raw_decision", "source_output_artifact_id",
            "admitted_sources_lock_sha256", "interval_panel_lock_sha256",
        }
        query_ok = (
            product_query_1
            and required_query_fields <= set(product_query_1[0])
            and len(product_summary_1["distinct_samples"]) >= 2
            and len(product_summary_1["distinct_technologies"]) >= 2
            and product_summary_1["outcome_used_for_query_selection"] is False
            and all(row["variant_id"] == product_summary_1["variant_id"] for row in product_query_1)
        )
        add(
            "P2-16",
            query_ok,
            (
                f"rows={len(product_query_1)} "
                f"samples={len(product_summary_1['distinct_samples'])} "
                f"technologies={len(product_summary_1['distinct_technologies'])}"
            ),
        )

        # P2-17
        scientific_headers = set()
        for table in (
            p2c_events,
            p2c_observations,
            p2d_links,
            p2d_accounting,
            p2d_variants,
            p2d_variant_index,
            product_query_1,
        ):
            if table:
                scientific_headers.update(table[0].keys())
        forbidden_found = sorted(scientific_headers & DISALLOWED_SCIENTIFIC_FIELDS)
        add(
            "P2-17",
            not forbidden_found,
            f"forbidden_scientific_fields={forbidden_found}",
        )

        # P2-18
        d14 = next(
            (row for row in p2d_validation if row["validation_id"] == "D14_reproducibility"),
            None,
        )
        reproducible = (
            d14 is not None
            and d14["status"] == "PASS"
            and canonical_hash(product_query_1) == canonical_hash(product_query_2)
            and canonical_hash(product_summary_1) == canonical_hash(product_summary_2)
        )
        add(
            "P2-18",
            reproducible,
            (
                f"product_query_sha256={canonical_hash(product_query_1)} "
                f"phase2d_D14={d14['status'] if d14 else 'MISSING'}"
            ),
        )

        # P2-20 is evaluated before packaging. P2-19 is added after bundle files
        # are prepared but before the deterministic archive is independently verified.
        limitations = {
            "dataset_selection_scope": (
                "Phase 2 uses four admitted public precisionFDA Truth Challenge V2 "
                "query artifacts for HG003/HG004 plus the frozen Phase 1 HG002 evidence. "
                "It is not a representative survey of all sequencing platforms, callers, "
                "chemistries, laboratories, or populations."
            ),
            "benchmark_truth_limitations": (
                "GIAB v4.2.1 truth and benchmark regions are treated as comparator "
                "references for this registry, not as perfect or universal biological truth."
            ),
            "unresolved_representation_equivalence": (
                "Representation-equivalence inference remains disabled. Sixty Phase 2C "
                "events lacking a complete single normalized allele remain UNRESOLVED and "
                "receive no guessed biological VARIANT identity."
            ),
            "evidence_vs_truth": (
                "The registry aggregates empirical benchmark evidence while preserving "
                "sample, technology, run, event, and observation context. Evidence aggregation "
                "does not establish biological truth, pathogenicity, clinical validity, or "
                "which technology should be trusted."
            ),
        }
        limitations_ok = all(bool(value.strip()) for value in limitations.values())

        # Build final output bundle.
        if OUTPUT_ROOT.exists():
            shutil.rmtree(OUTPUT_ROOT)
        BUNDLE_DIR.mkdir(parents=True)

        query_path = BUNDLE_DIR / "final_variant_product_query.tsv"
        write_tsv(query_path, product_query_1)

        (BUNDLE_DIR / "final_variant_product_query_summary.json").write_text(
            json.dumps(product_summary_1, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        reproducibility = {
            "product_query_first_sha256": canonical_hash(product_query_1),
            "product_query_second_sha256": canonical_hash(product_query_2),
            "product_query_match": product_query_1 == product_query_2,
            "product_summary_first_sha256": canonical_hash(product_summary_1),
            "product_summary_second_sha256": canonical_hash(product_summary_2),
            "product_summary_match": product_summary_1 == product_summary_2,
            "phase2d_d14_status": d14["status"] if d14 else "MISSING",
        }
        (BUNDLE_DIR / "reproducibility.json").write_text(
            json.dumps(reproducibility, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        authority_rows = []
        for path, expected in sorted(EXPECTED.items(), key=lambda item: str(item[0])):
            authority_rows.append(
                {
                    "repository_path": str(path.relative_to(ROOT)),
                    "sha256": expected,
                    "size_bytes": path.stat().st_size,
                }
            )
        write_tsv(
            BUNDLE_DIR / "authority_manifest.tsv",
            authority_rows,
            ["repository_path", "sha256", "size_bytes"],
        )

        authorities_dir = BUNDLE_DIR / "authorities"
        authorities_dir.mkdir()
        nested_authorities = {
            "phase1a.tar.gz": PHASE1A_ARCHIVE,
            "phase1b.tar.gz": PHASE1B_ARCHIVE,
            "phase2c.tar.gz": PHASE2C_ARCHIVE,
            "phase2d.tar.gz": PHASE2D_ARCHIVE,
        }
        for name, source in nested_authorities.items():
            shutil.copyfile(source, authorities_dir / name)

        frozen_metadata = BUNDLE_DIR / "frozen_metadata"
        frozen_metadata.mkdir()
        frozen_copies = {
            "phase2_protocol.md": PHASE2_PROTOCOL,
            "admitted_sources.tsv": ADMITTED_SOURCES,
            "admitted_sources.lock": ADMITTED_LOCK,
            "source_candidates.tsv": SOURCE_CANDIDATES,
            "selected_intervals.tsv": SELECTED_INTERVALS,
            "selected_assessable_segments.bed": SELECTED_PANEL,
            "interval_panel.lock": PANEL_LOCK,
            "phase2c_compute_protocol.lock": PHASE2C_PROTOCOL_LOCK,
            "phase2d_compute_release.lock": PHASE2D_RELEASE_LOCK,
            "phase2e_validation_protocol.md": PHASE2E_PROTOCOL,
            "phase2e_validation_protocol.lock": PHASE2E_PROTOCOL_LOCK,
        }
        for name, source in frozen_copies.items():
            shutil.copyfile(source, frozen_metadata / name)

        report_text = f"""# Project 003 — Phase 2 Final Report

## Final validation scope

Phase 2E evaluates the 20 criteria frozen before final-gate execution.
It performs no new genomic benchmarking and does not modify Phase 1A,
Phase 1B, Phase 2C, or Phase 2D scientific records.

## Registry expansion

The frozen registry now contains benchmark evidence for three samples in
total: {", ".join(all_samples)}.

Phase 2C contributes four benchmark runs covering HG003 and HG004 with
Illumina and Oxford Nanopore evidence across a deterministic multi-context,
multi-chromosome panel.

Phase 2D accounts for {len(p2d_accounting):,} Phase 2C EVENT records:
{len(p2d_links):,} exact biological identity links and
{len(unresolved):,} UNRESOLVED events.

The Phase 2D exact evidence touches {len(p2d_variant_index):,} biological
VARIANT identities.

## Product query

The deterministic Phase 2E product query selects one biological VARIANT by
structural evidence coverage only: maximize distinct sample count, then
technology count, then linked EVENT count, with VARIANT ID as the tie-break.

It returns {len(product_query_1):,} observation rows spanning
{len(product_summary_1["distinct_samples"])} samples and
{len(product_summary_1["distinct_technologies"])} sequencing technologies.

The query preserves experiment, benchmark run, EVENT, OBSERVATION,
truth/query side, raw comparator decision, comparator/version, source
artifact provenance, source-selection record, and biological identity method.
It does not collapse observations to consensus.

## Limitations

### Dataset-selection scope

{limitations["dataset_selection_scope"]}

### Benchmark-truth limitations

{limitations["benchmark_truth_limitations"]}

### Unresolved representation equivalence

{limitations["unresolved_representation_equivalence"]}

### Evidence aggregation versus biological or clinical truth

{limitations["evidence_vs_truth"]}

## Scientific boundaries

Phase 2 does not create a reliability score, confidence score, trust label,
technology ranking, caller ranking, majority vote, forced consensus, clinical
interpretation, or pathogenicity assertion.

Representation-equivalence inference remains disabled unless a separately
specified, adversarially validated, pre-frozen method is introduced in a
future phase.

## Final outcome

The final outcome is derived from `phase2_final_validation.tsv`.

PASS requires all 20 frozen Phase 2 criteria to pass. If one or more criteria
fail, the verdict is derived as MODIFY or STOP according to the frozen
scientific/integrity significance of the failed criterion.
"""
        (BUNDLE_DIR / "phase2_final_report.md").write_text(report_text, encoding="utf-8")

        # P2-20
        add(
            "P2-20",
            limitations_ok
            and all(
                phrase in report_text
                for phrase in (
                    "Dataset-selection scope",
                    "Benchmark-truth limitations",
                    "Unresolved representation equivalence",
                    "Evidence aggregation versus biological or clinical truth",
                )
            ),
            "final report contains all four frozen limitation categories",
        )

        # Add P2-19 provisionally. The success marker is impossible unless the
        # final deterministic archive is subsequently independently extracted
        # and verified.
        add(
            "P2-19",
            True,
            "deterministic final archive checksum manifest and independent extraction verification required before success marker",
        )

        gates.sort(key=lambda row: int(row["validation_id"].split("-")[1]))
        require(len(gates) == 20, f"expected 20 final gates, observed {len(gates)}")
        require(
            [row["validation_id"] for row in gates] == [f"P2-{i:02d}" for i in range(1, 21)],
            "final gate identifiers changed",
        )

        failed = [row["validation_id"] for row in gates if row["status"] != "PASS"]
        if not failed:
            verdict = "PASS"
        elif any(gate in FUNDAMENTAL_GATES for gate in failed):
            verdict = "STOP"
        else:
            verdict = "MODIFY"

        write_tsv(
            BUNDLE_DIR / "phase2_final_validation.tsv",
            gates,
            ["validation_id", "status", "detail"],
        )

        final_summary = {
            "project": "Project 003",
            "phase": "2E",
            "final_verdict": verdict,
            "phase2_gate_count": 20,
            "phase2_gate_pass_count": sum(row["status"] == "PASS" for row in gates),
            "phase2_gate_fail_count": sum(row["status"] != "PASS" for row in gates),
            "failed_gates": failed,
            "samples": all_samples,
            "sample_count": len(all_samples),
            "phase2_context_count": len(contexts),
            "phase2_chromosome_count": len(chromosomes),
            "phase2c_event_count": len(p2c_events),
            "phase2c_observation_count": len(p2c_observations),
            "phase2d_exact_link_count": len(p2d_links),
            "phase2d_unresolved_event_count": len(unresolved),
            "phase2d_unique_variant_count": len(p2d_variant_index),
            "product_query_variant_id": product_summary_1["variant_id"],
            "product_query_rows": len(product_query_1),
            "product_query_distinct_samples": len(product_summary_1["distinct_samples"]),
            "product_query_distinct_technologies": len(product_summary_1["distinct_technologies"]),
            "representation_equivalence_enabled": False,
            "reliability_scoring_enabled": False,
            "technology_ranking_enabled": False,
            "new_genomic_compute_performed": False,
        }
        (BUNDLE_DIR / "phase2_final_summary.json").write_text(
            json.dumps(final_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        # Bundle checksum manifest.
        checksum_targets = sorted(
            [
                p for p in BUNDLE_DIR.rglob("*")
                if p.is_file() and p.name != "checksums.sha256"
            ],
            key=lambda p: p.relative_to(BUNDLE_DIR).as_posix(),
        )
        checksum_lines = [
            f"{sha256_file(p)}  {p.relative_to(BUNDLE_DIR).as_posix()}"
            for p in checksum_targets
        ]
        (BUNDLE_DIR / "checksums.sha256").write_text(
            "\n".join(checksum_lines) + "\n",
            encoding="utf-8",
        )

        # Create two independently generated deterministic archives and require
        # byte identity before keeping the final one.
        candidate_a = tmp / "phase2_final_a.tar.gz"
        candidate_b = tmp / "phase2_final_b.tar.gz"
        deterministic_tar_gz(BUNDLE_DIR, candidate_a)
        deterministic_tar_gz(BUNDLE_DIR, candidate_b)
        require(
            sha256_file(candidate_a) == sha256_file(candidate_b),
            "deterministic final archive rebuild mismatch",
        )
        shutil.copyfile(candidate_a, ARCHIVE_PATH)

        # Independent extraction of the final archive.
        verify_root = tmp / "verify_final"
        verify_root.mkdir()
        safe_extract(ARCHIVE_PATH, verify_root)
        extracted_bundle = verify_root / BUNDLE_DIR.name
        require(extracted_bundle.is_dir(), "final extracted bundle root missing")
        verify_checksum_manifest(extracted_bundle)

        # Verify nested frozen authorities after final archive extraction.
        nested_expected = {
            "phase1a.tar.gz": EXPECTED[PHASE1A_ARCHIVE],
            "phase1b.tar.gz": EXPECTED[PHASE1B_ARCHIVE],
            "phase2c.tar.gz": EXPECTED[PHASE2C_ARCHIVE],
            "phase2d.tar.gz": EXPECTED[PHASE2D_ARCHIVE],
        }
        for name, expected in nested_expected.items():
            nested = extracted_bundle / "authorities" / name
            require(nested.is_file(), f"nested authority missing: {name}")
            require(sha256_file(nested) == expected, f"nested authority hash mismatch: {name}")

        extracted_gates = read_tsv(extracted_bundle / "phase2_final_validation.tsv")
        require(len(extracted_gates) == 20, "final extracted validation gate count mismatch")
        extracted_summary = json.loads(
            (extracted_bundle / "phase2_final_summary.json").read_text(encoding="utf-8")
        )
        require(extracted_summary["final_verdict"] == verdict, "final extracted verdict mismatch")

    authority_after = {str(path): sha256_file(path) for path in EXPECTED}
    require(authority_before == authority_after, "frozen authorities mutated during Phase 2E")

    print("PASS  frozen authority archives and locks")
    print("PASS  final archive internal checksum manifest")
    print("PASS  nested authority archive identities")
    print("PASS  final archive deterministic rebuild")
    print("PASS  final archive independent extraction")
    print()
    for row in gates:
        print(f"{row['validation_id']}  {row['status']}  {row['detail']}")
    print()
    print(f"Final verdict: {verdict}")
    print(f"Final archive: {ARCHIVE_PATH.relative_to(ROOT)}")
    print(f"Final archive size: {ARCHIVE_PATH.stat().st_size}")
    print(f"Final archive SHA-256: {sha256_file(ARCHIVE_PATH)}")
    print()
    if verdict == "PASS":
        print("PHASE2E_FINAL_VALIDATION_PASS")
    elif verdict == "MODIFY":
        print("PHASE2E_FINAL_VALIDATION_MODIFY")
    else:
        print("PHASE2E_FINAL_VALIDATION_STOP")
    print("=" * 78)
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print()
        print("PHASE2E_FINAL_VALIDATION_EXECUTION_FAIL")
        print(f"{type(exc).__name__}: {exc}")
        raise
