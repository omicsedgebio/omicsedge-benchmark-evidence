#!/usr/bin/env python3

from __future__ import annotations

import csv
import gzip
import hashlib
import heapq
import json
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

METHOD_PATH = ROOT / "docs/phase2/interval_selection_method.md"
CONTEXT_MANIFEST = ROOT / "data/phase2/context_beds_downloaded.tsv"
SHARED_CALLABLE_PATH = ROOT / "data/phase2/shared_callable.bed"

CANDIDATES_OUT = ROOT / "data/phase2/interval_candidates.tsv"
SELECTED_OUT = ROOT / "data/phase2/selected_intervals.tsv"
WINDOW_SEGMENTS_OUT = ROOT / "data/phase2/selected_window_segments.tsv"
PANEL_BED_OUT = ROOT / "data/phase2/selected_assessable_segments.bed"

SUMMARY_OUT = ROOT / "results/phase2/interval_selection_summary.json"
CHECKSUMS_OUT = ROOT / "data/phase2/interval_panel_checksums.tsv"
LOCK_OUT = ROOT / "data/phase2/interval_panel.lock"


EXPECTED_METHOD_SHA256 = (
    "b3dd8fdbd8c308a9f9098fbc213a9a243ceec081b92b74862d60d212ea1619b2"
)

EXPECTED_CONTEXT_MANIFEST_SHA256 = (
    "977bf8110db8e26486eaea51d138cd02264da4b26b29fd9c29c595e3bf405cc5"
)

EXPECTED_SHARED_CALLABLE_SHA256 = (
    "22abff164c57dc25327d5a395e5fc17d49f30cbde4b2d18cbc4748a52643c549"
)

CONTEXT_ORDER = [
    "NON_DIFFICULT",
    "HOMOPOLYMER",
    "TANDEM_REPEAT",
    "LOW_MAPPABILITY",
    "SEGMENTAL_DUPLICATION",
]

WINDOW_SIZE = 25_000
HALF_WINDOW = WINDOW_SIZE // 2
MIN_ASSESSABLE_BP = 5_000
WINDOWS_PER_CONTEXT = 10
MIN_CHROMS_PER_CONTEXT = 5
MAX_WINDOWS_PER_CHROM = 2
CROSS_CONTEXT_MAX_OVERLAP = WINDOW_SIZE // 2

ELIGIBLE_CHROMS = {
    f"chr{i}"
    for i in range(1, 23)
    if i != 20
}

SHARED_CALLABLE_DEFINITION = (
    "HG003_GIAB_v4.2.1_noinconsistent_INTERSECT_"
    "HG004_GIAB_v4.2.1_noinconsistent|"
    f"sha256:{EXPECTED_SHARED_CALLABLE_SHA256}"
)

INITIAL_FRONTIER_LIMIT = 10_000
MAX_FRONTIER_LIMIT = 320_000


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


def deterministic_id(prefix: str, payload: dict) -> str:
    digest = hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()

    return f"{prefix}:sha256:{digest}"


def chromosome_sort_key(chrom: str) -> tuple:
    value = chrom[3:] if chrom.startswith("chr") else chrom

    if value.isdigit():
        return (0, int(value))

    return (1, value)


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


def load_bed(path: Path) -> dict[str, list[tuple[int, int]]]:
    result = defaultdict(list)

    with path.open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as handle:
        for raw in handle:
            line = raw.strip()

            if not line or line.startswith(("#", "track", "browser")):
                continue

            fields = line.split()
            require(len(fields) >= 3, f"invalid BED row: {line}")

            chrom = fields[0]
            start = int(fields[1])
            end = int(fields[2])

            require(start >= 0 and end > start, f"invalid BED coordinates: {line}")

            result[chrom].append((start, end))

    for chrom in result:
        result[chrom].sort()

    return dict(result)


def merge_intervals(
    intervals: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    if not intervals:
        return []

    ordered = sorted(intervals)
    merged = [[ordered[0][0], ordered[0][1]]]

    for start, end in ordered[1:]:
        previous = merged[-1]

        if start <= previous[1]:
            previous[1] = max(previous[1], end)
        else:
            merged.append([start, end])

    return [(start, end) for start, end in merged]


def interval_overlap(
    a_start: int,
    a_end: int,
    b_start: int,
    b_end: int,
) -> int:
    return max(
        0,
        min(a_end, b_end) - max(a_start, b_start),
    )


def build_callable_index(
    callable_intervals: dict[str, list[tuple[int, int]]],
) -> dict:
    index = {}

    for chrom, intervals in callable_intervals.items():
        merged = merge_intervals(intervals)

        index[chrom] = {
            "intervals": merged,
            "ends": [end for _start, end in merged],
        }

    return index


def intersect_window(
    chrom: str,
    start: int,
    end: int,
    callable_index: dict,
) -> list[tuple[int, int]]:
    if chrom not in callable_index:
        return []

    record = callable_index[chrom]
    intervals = record["intervals"]
    ends = record["ends"]

    index = bisect_right(ends, start)

    output = []

    while index < len(intervals):
        interval_start, interval_end = intervals[index]

        if interval_start >= end:
            break

        clipped_start = max(start, interval_start)
        clipped_end = min(end, interval_end)

        if clipped_start < clipped_end:
            output.append((clipped_start, clipped_end))

        index += 1

    return output


def assessable_bp(segments: list[tuple[int, int]]) -> int:
    return sum(end - start for start, end in segments)


def iter_context_bed(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open

    with opener(
        path,
        "rt",
        encoding="utf-8",
        errors="replace",
    ) as handle:
        for raw in handle:
            line = raw.strip()

            if not line or line.startswith(("#", "track", "browser")):
                continue

            fields = line.split()

            if len(fields) < 3:
                continue

            chrom = fields[0]

            if chrom not in ELIGIBLE_CHROMS:
                continue

            try:
                start = int(fields[1])
                end = int(fields[2])
            except ValueError:
                continue

            if start < 0 or end <= start:
                continue

            yield chrom, start, end


def build_candidate(
    *,
    context_id: str,
    source_sha256: str,
    chrom: str,
    anchor_start: int,
    anchor_end: int,
    callable_index: dict,
):
    midpoint = (anchor_start + anchor_end) // 2

    nominal_start = max(
        0,
        midpoint - HALF_WINDOW,
    )

    nominal_end = nominal_start + WINDOW_SIZE

    segments = intersect_window(
        chrom,
        nominal_start,
        nominal_end,
        callable_index,
    )

    total_assessable = assessable_bp(segments)

    if total_assessable < MIN_ASSESSABLE_BP:
        return None

    payload = {
        "phase": "2B",
        "assembly": "GRCh38",
        "context_id": context_id,
        "chromosome": chrom,
        "nominal_start_0based": nominal_start,
        "nominal_end_0based": nominal_end,
        "source_context_bed_sha256": source_sha256,
        "shared_callable_definition": SHARED_CALLABLE_DEFINITION,
    }

    candidate_id = deterministic_id(
        "phase2-window",
        payload,
    )

    selection_hash = hashlib.sha256(
        (
            "PROJECT003_PHASE2B|"
            + candidate_id
        ).encode("utf-8")
    ).hexdigest()

    return {
        "candidate_id": candidate_id,
        "selection_hash": selection_hash,
        "context_id": context_id,
        "chromosome": chrom,
        "nominal_start_0based": nominal_start,
        "nominal_end_0based": nominal_end,
        "nominal_length_bp": WINDOW_SIZE,
        "source_anchor_start_0based": anchor_start,
        "source_anchor_end_0based": anchor_end,
        "source_anchor_midpoint_0based": midpoint,
        "source_context_bed_sha256": source_sha256,
        "assessable_bp": total_assessable,
        "assessable_segments": segments,
    }


def collect_frontier(
    *,
    context_id: str,
    context_path: Path,
    source_sha256: str,
    callable_index: dict,
    limit: int,
) -> tuple[list[dict], dict]:
    heap = []
    heap_ids = set()

    raw_anchors = 0
    eligible_anchors = 0

    for chrom, anchor_start, anchor_end in iter_context_bed(context_path):
        raw_anchors += 1

        candidate = build_candidate(
            context_id=context_id,
            source_sha256=source_sha256,
            chrom=chrom,
            anchor_start=anchor_start,
            anchor_end=anchor_end,
            callable_index=callable_index,
        )

        if candidate is None:
            continue

        eligible_anchors += 1

        candidate_id = candidate["candidate_id"]

        if candidate_id in heap_ids:
            continue

        hash_int = int(
            candidate["selection_hash"],
            16,
        )

        item = (
            -hash_int,
            candidate["selection_hash"],
            candidate_id,
            candidate,
        )

        if len(heap) < limit:
            heapq.heappush(heap, item)
            heap_ids.add(candidate_id)
            continue

        largest_hash_int = -heap[0][0]

        if hash_int < largest_hash_int:
            removed = heapq.heapreplace(heap, item)
            heap_ids.remove(removed[2])
            heap_ids.add(candidate_id)

    frontier = [
        item[3]
        for item in heap
    ]

    frontier.sort(
        key=lambda row: (
            row["selection_hash"],
            chromosome_sort_key(row["chromosome"]),
            row["nominal_start_0based"],
            row["candidate_id"],
        )
    )

    return (
        frontier,
        {
            "raw_eligible_chromosome_anchors": raw_anchors,
            "eligible_callable_anchors": eligible_anchors,
            "frontier_limit": limit,
            "frontier_unique_candidates": len(frontier),
        },
    )


def choose_windows(
    *,
    frontier: list[dict],
    prior_context_windows: list[dict],
) -> tuple[list[dict], list[dict]]:
    selected = []
    evaluated = []
    chromosome_counts = Counter()

    for evaluation_rank, candidate in enumerate(
        frontier,
        start=1,
    ):
        chrom = candidate["chromosome"]
        start = candidate["nominal_start_0based"]
        end = candidate["nominal_end_0based"]

        rejection_reason = ""

        if chromosome_counts[chrom] >= MAX_WINDOWS_PER_CHROM:
            rejection_reason = "MAX_WINDOWS_PER_CHROMOSOME"

        if not rejection_reason:
            for previous in selected:
                if previous["chromosome"] != chrom:
                    continue

                overlap = interval_overlap(
                    start,
                    end,
                    previous["nominal_start_0based"],
                    previous["nominal_end_0based"],
                )

                if overlap > 0:
                    rejection_reason = "WITHIN_CONTEXT_OVERLAP"
                    break

        if not rejection_reason:
            for previous in prior_context_windows:
                if previous["chromosome"] != chrom:
                    continue

                overlap = interval_overlap(
                    start,
                    end,
                    previous["nominal_start_0based"],
                    previous["nominal_end_0based"],
                )

                if overlap >= CROSS_CONTEXT_MAX_OVERLAP:
                    rejection_reason = "CROSS_CONTEXT_OVERLAP_GE_50_PERCENT"
                    break

        accepted = not rejection_reason

        audit_row = dict(candidate)
        audit_row["evaluation_rank"] = evaluation_rank
        audit_row["decision"] = (
            "SELECTED"
            if accepted
            else "REJECTED"
        )
        audit_row["rejection_reason"] = rejection_reason

        evaluated.append(audit_row)

        if not accepted:
            continue

        chromosome_counts[chrom] += 1

        chosen = dict(candidate)
        chosen["selection_rank"] = len(selected) + 1
        chosen["chromosome_selection_rank"] = chromosome_counts[chrom]

        selected.append(chosen)

        if len(selected) == WINDOWS_PER_CONTEXT:
            break

    return selected, evaluated


def scan_context_overlap(
    context_path: Path,
    selected_windows: list[dict],
) -> dict[str, dict[str, int]]:
    windows_by_chrom = defaultdict(list)

    for window in selected_windows:
        windows_by_chrom[
            window["chromosome"]
        ].append(window)

    fragments = defaultdict(list)

    for chrom, start, end in iter_context_bed(context_path):
        for window in windows_by_chrom.get(chrom, []):
            clipped_start = max(
                start,
                window["nominal_start_0based"],
            )

            clipped_end = min(
                end,
                window["nominal_end_0based"],
            )

            if clipped_start < clipped_end:
                fragments[
                    window["candidate_id"]
                ].append(
                    (
                        clipped_start,
                        clipped_end,
                    )
                )

    totals = {}

    for candidate_id, pieces in fragments.items():
        merged = merge_intervals(pieces)

        totals[candidate_id] = sum(
            end - start
            for start, end
            in merged
        )

    return totals


def main() -> int:
    print("=" * 78)
    print(
        "PROJECT 003 — PHASE 2B "
        "DETERMINISTIC INTERVAL SELECTION"
    )
    print("=" * 78)

    # --------------------------------------------------------
    # Verify frozen authorities.
    # --------------------------------------------------------

    require(
        sha256_file(METHOD_PATH)
        == EXPECTED_METHOD_SHA256,
        "interval-selection method changed",
    )

    require(
        sha256_file(CONTEXT_MANIFEST)
        == EXPECTED_CONTEXT_MANIFEST_SHA256,
        "context BED download manifest changed",
    )

    require(
        sha256_file(SHARED_CALLABLE_PATH)
        == EXPECTED_SHARED_CALLABLE_SHA256,
        "shared_callable.bed changed",
    )

    print("PASS  frozen interval-selection method")
    print("PASS  frozen context BED manifest")
    print("PASS  frozen shared-callable SHA-256")

    context_rows = read_tsv(
        CONTEXT_MANIFEST
    )

    context_index = {
        row["context_id"]: row
        for row in context_rows
    }

    require(
        set(context_index)
        == set(CONTEXT_ORDER),
        "unexpected frozen context set",
    )

    # --------------------------------------------------------
    # Shared callable index.
    # --------------------------------------------------------

    shared = load_bed(
        SHARED_CALLABLE_PATH
    )

    callable_index = build_callable_index(
        shared
    )

    require(
        "chr20" in callable_index,
        "source shared callable unexpectedly lacks chr20",
    )

    for chrom in ELIGIBLE_CHROMS:
        require(
            chrom in callable_index,
            f"shared callable missing {chrom}",
        )

    # --------------------------------------------------------
    # Select in frozen context order.
    # --------------------------------------------------------

    all_selected = []
    candidate_audit_rows = []
    context_summaries = {}

    for context_id in CONTEXT_ORDER:
        row = context_index[context_id]

        context_path = (
            ROOT
            / row["local_path"]
        )

        require(
            context_path.is_file(),
            f"missing context BED: {context_path}",
        )

        require(
            sha256_file(context_path)
            == row["sha256"],
            f"{context_id} BED SHA-256 changed",
        )

        print()
        print("Selecting:", context_id)

        limit = INITIAL_FRONTIER_LIMIT

        while True:
            frontier, generation_stats = collect_frontier(
                context_id=context_id,
                context_path=context_path,
                source_sha256=row["sha256"],
                callable_index=callable_index,
                limit=limit,
            )

            selected, evaluated = choose_windows(
                frontier=frontier,
                prior_context_windows=all_selected,
            )

            if len(selected) == WINDOWS_PER_CONTEXT:
                break

            require(
                limit < MAX_FRONTIER_LIMIT,
                (
                    f"{context_id}: unable to select "
                    f"{WINDOWS_PER_CONTEXT} windows "
                    f"within maximum deterministic frontier"
                ),
            )

            limit *= 2

        chrom_counts = Counter(
            item["chromosome"]
            for item in selected
        )

        require(
            len(selected) == WINDOWS_PER_CONTEXT,
            f"{context_id}: selection count != 10",
        )

        require(
            len(chrom_counts)
            >= MIN_CHROMS_PER_CONTEXT,
            (
                f"{context_id}: only "
                f"{len(chrom_counts)} chromosomes"
            ),
        )

        require(
            max(chrom_counts.values())
            <= MAX_WINDOWS_PER_CHROM,
            f"{context_id}: chromosome cap violated",
        )

        require(
            all(
                item["chromosome"] != "chr20"
                for item in selected
            ),
            f"{context_id}: chr20 entered selection",
        )

        all_selected.extend(
            selected
        )

        candidate_audit_rows.extend(
            evaluated
        )

        context_summaries[context_id] = {
            **generation_stats,
            "frontier_limit_used": limit,
            "evaluated_frontier_candidates": len(evaluated),
            "selected_windows": len(selected),
            "selected_chromosomes": sorted(
                chrom_counts,
                key=chromosome_sort_key,
            ),
            "selected_chromosome_count": len(chrom_counts),
            "max_windows_on_one_chromosome": max(
                chrom_counts.values()
            ),
        }

        print(
            "  selected:",
            len(selected),
        )
        print(
            "  chromosomes:",
            len(chrom_counts),
        )
        print(
            "  frontier evaluated:",
            len(evaluated),
        )

    # --------------------------------------------------------
    # Global panel validation.
    # --------------------------------------------------------

    require(
        len(all_selected) == 50,
        f"expected 50 selected windows; observed {len(all_selected)}",
    )

    require(
        len(
            {
                row["candidate_id"]
                for row in all_selected
            }
        )
        == 50,
        "duplicate selected candidate IDs",
    )

    require(
        all(
            row["assessable_bp"]
            >= MIN_ASSESSABLE_BP
            for row in all_selected
        ),
        "selected window below assessable threshold",
    )

    # Recheck cross-context overlap.
    for index_a, a in enumerate(all_selected):
        for b in all_selected[index_a + 1:]:
            if (
                a["context_id"] == b["context_id"]
                or a["chromosome"] != b["chromosome"]
            ):
                continue

            overlap = interval_overlap(
                a["nominal_start_0based"],
                a["nominal_end_0based"],
                b["nominal_start_0based"],
                b["nominal_end_0based"],
            )

            require(
                overlap < CROSS_CONTEXT_MAX_OVERLAP,
                "cross-context >=50% overlap survived selection",
            )

    print()
    print("PASS  selected windows: 50")
    print("PASS  10 windows per context")
    print("PASS  >=5 chromosomes per context")
    print("PASS  <=2 windows/chromosome/context")
    print("PASS  chr20 excluded")
    print("PASS  >=5,000 assessable bp/window")
    print("PASS  cross-context overlap constraint")

    # --------------------------------------------------------
    # Determine overlap with all five biological contexts.
    # This uses stratification membership only, not variants.
    # --------------------------------------------------------

    context_overlap_bp = {
        row["candidate_id"]: {}
        for row in all_selected
    }

    for context_id in CONTEXT_ORDER:
        context_path = (
            ROOT
            / context_index[context_id]["local_path"]
        )

        overlap_totals = scan_context_overlap(
            context_path,
            all_selected,
        )

        for window in all_selected:
            context_overlap_bp[
                window["candidate_id"]
            ][context_id] = int(
                overlap_totals.get(
                    window["candidate_id"],
                    0,
                )
            )

    # --------------------------------------------------------
    # Write candidate frontier audit.
    # --------------------------------------------------------

    candidate_fields = [
        "context_id",
        "candidate_id",
        "selection_hash",
        "evaluation_rank",
        "decision",
        "rejection_reason",
        "chromosome",
        "nominal_start_0based",
        "nominal_end_0based",
        "nominal_length_bp",
        "source_anchor_start_0based",
        "source_anchor_end_0based",
        "source_anchor_midpoint_0based",
        "source_context_bed_sha256",
        "assessable_bp",
    ]

    with CANDIDATES_OUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=candidate_fields,
            delimiter="\t",
            lineterminator="\n",
        )

        writer.writeheader()

        for row in candidate_audit_rows:
            writer.writerow(
                {
                    field: row[field]
                    for field in candidate_fields
                }
            )

    # --------------------------------------------------------
    # Selected intervals + per-window assessable segments.
    # --------------------------------------------------------

    selected_fields = [
        "window_id",
        "context_id",
        "selection_rank",
        "chromosome_selection_rank",
        "selection_hash",
        "chromosome",
        "nominal_start_0based",
        "nominal_end_0based",
        "nominal_length_bp",
        "assessable_bp",
        "assessable_segment_count",
        "assessable_segments_json",
        "source_anchor_start_0based",
        "source_anchor_end_0based",
        "source_anchor_midpoint_0based",
        "source_context_bed_sha256",
        "overlapping_context_ids",
        "context_overlap_bp_json",
    ]

    selected_rows = []
    window_segment_rows = []

    context_rank = {
        context_id: index
        for index, context_id
        in enumerate(CONTEXT_ORDER)
    }

    all_selected.sort(
        key=lambda row: (
            context_rank[row["context_id"]],
            row["selection_rank"],
        )
    )

    for row in all_selected:
        overlaps = context_overlap_bp[
            row["candidate_id"]
        ]

        other_contexts = [
            context_id
            for context_id in CONTEXT_ORDER
            if (
                context_id != row["context_id"]
                and overlaps.get(context_id, 0) > 0
            )
        ]

        segments = row[
            "assessable_segments"
        ]

        selected_rows.append(
            {
                "window_id": row["candidate_id"],
                "context_id": row["context_id"],
                "selection_rank": row["selection_rank"],
                "chromosome_selection_rank":
                    row["chromosome_selection_rank"],
                "selection_hash": row["selection_hash"],
                "chromosome": row["chromosome"],
                "nominal_start_0based":
                    row["nominal_start_0based"],
                "nominal_end_0based":
                    row["nominal_end_0based"],
                "nominal_length_bp":
                    row["nominal_length_bp"],
                "assessable_bp":
                    row["assessable_bp"],
                "assessable_segment_count":
                    len(segments),
                "assessable_segments_json":
                    canonical_json(
                        [
                            {
                                "start_0based": start,
                                "end_0based": end,
                            }
                            for start, end in segments
                        ]
                    ),
                "source_anchor_start_0based":
                    row["source_anchor_start_0based"],
                "source_anchor_end_0based":
                    row["source_anchor_end_0based"],
                "source_anchor_midpoint_0based":
                    row["source_anchor_midpoint_0based"],
                "source_context_bed_sha256":
                    row["source_context_bed_sha256"],
                "overlapping_context_ids":
                    ";".join(other_contexts),
                "context_overlap_bp_json":
                    canonical_json(overlaps),
            }
        )

        for segment_rank, (start, end) in enumerate(
            segments,
            start=1,
        ):
            window_segment_rows.append(
                {
                    "window_id": row["candidate_id"],
                    "context_id": row["context_id"],
                    "segment_rank": segment_rank,
                    "chromosome": row["chromosome"],
                    "start_0based": start,
                    "end_0based": end,
                    "length_bp": end - start,
                }
            )

    with SELECTED_OUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=selected_fields,
            delimiter="\t",
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(selected_rows)

    segment_fields = [
        "window_id",
        "context_id",
        "segment_rank",
        "chromosome",
        "start_0based",
        "end_0based",
        "length_bp",
    ]

    with WINDOW_SEGMENTS_OUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=segment_fields,
            delimiter="\t",
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(window_segment_rows)

    # --------------------------------------------------------
    # Final benchmark panel = union of all assessable segments.
    # --------------------------------------------------------

    segments_by_chrom = defaultdict(list)

    for row in window_segment_rows:
        segments_by_chrom[
            row["chromosome"]
        ].append(
            (
                int(row["start_0based"]),
                int(row["end_0based"]),
            )
        )

    merged_panel = {}

    for chrom, segments in segments_by_chrom.items():
        merged_panel[chrom] = merge_intervals(
            segments
        )

    with PANEL_BED_OUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        for chrom in sorted(
            merged_panel,
            key=chromosome_sort_key,
        ):
            for start, end in merged_panel[chrom]:
                handle.write(
                    f"{chrom}\t{start}\t{end}\n"
                )

    panel_intervals = sum(
        len(intervals)
        for intervals in merged_panel.values()
    )

    panel_bases = sum(
        end - start
        for intervals in merged_panel.values()
        for start, end in intervals
    )

    panel_chromosomes = sorted(
        merged_panel,
        key=chromosome_sort_key,
    )

    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    output_hashes = {
        "interval_candidates.tsv":
            sha256_file(CANDIDATES_OUT),

        "selected_intervals.tsv":
            sha256_file(SELECTED_OUT),

        "selected_window_segments.tsv":
            sha256_file(WINDOW_SEGMENTS_OUT),

        "selected_assessable_segments.bed":
            sha256_file(PANEL_BED_OUT),
    }

    summary = {
        "project": "Project 003",
        "phase": "2B",
        "operation": "DETERMINISTIC_INTERVAL_SELECTION",
        "status": "PASS",
        "interval_selection_method_sha256":
            EXPECTED_METHOD_SHA256,
        "context_beds_downloaded_manifest_sha256":
            EXPECTED_CONTEXT_MANIFEST_SHA256,
        "shared_callable_sha256":
            EXPECTED_SHARED_CALLABLE_SHA256,
        "query_vcfs_consulted": False,
        "benchmark_outcomes_consulted": False,
        "window_size_bp": WINDOW_SIZE,
        "minimum_assessable_bp": MIN_ASSESSABLE_BP,
        "selected_window_count": len(selected_rows),
        "contexts": context_summaries,
        "selected_panel": {
            "merged_interval_count": panel_intervals,
            "assessable_bases": panel_bases,
            "chromosome_count": len(panel_chromosomes),
            "chromosomes": panel_chromosomes,
            "chr20_present": "chr20" in panel_chromosomes,
        },
        "output_sha256": output_hashes,
    }

    SUMMARY_OUT.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Checksum manifest.
    # --------------------------------------------------------

    checksum_records = [
        (
            "data/phase2/interval_candidates.tsv",
            sha256_file(CANDIDATES_OUT),
        ),
        (
            "data/phase2/selected_intervals.tsv",
            sha256_file(SELECTED_OUT),
        ),
        (
            "data/phase2/selected_window_segments.tsv",
            sha256_file(WINDOW_SEGMENTS_OUT),
        ),
        (
            "data/phase2/selected_assessable_segments.bed",
            sha256_file(PANEL_BED_OUT),
        ),
        (
            "results/phase2/interval_selection_summary.json",
            sha256_file(SUMMARY_OUT),
        ),
    ]

    with CHECKSUMS_OUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.writer(
            handle,
            delimiter="\t",
            lineterminator="\n",
        )

        writer.writerow(
            [
                "path",
                "sha256",
            ]
        )

        for path, digest in checksum_records:
            writer.writerow(
                [
                    path,
                    digest,
                ]
            )

    checksums_sha = sha256_file(
        CHECKSUMS_OUT
    )

    # --------------------------------------------------------
    # Freeze final interval panel.
    # --------------------------------------------------------

    LOCK_OUT.write_text(
        "\n".join(
            [
                "project=Project 003",
                "phase=2B",
                (
                    "interval_selection_method_sha256="
                    f"{EXPECTED_METHOD_SHA256}"
                ),
                (
                    "context_beds_downloaded_manifest_sha256="
                    f"{EXPECTED_CONTEXT_MANIFEST_SHA256}"
                ),
                (
                    "shared_callable_sha256="
                    f"{EXPECTED_SHARED_CALLABLE_SHA256}"
                ),
                (
                    "selected_intervals_sha256="
                    f"{sha256_file(SELECTED_OUT)}"
                ),
                (
                    "selected_assessable_segments_sha256="
                    f"{sha256_file(PANEL_BED_OUT)}"
                ),
                (
                    "interval_panel_checksums_sha256="
                    f"{checksums_sha}"
                ),
                "selected_windows=50",
                "contexts=5",
                "windows_per_context=10",
                "excluded_chromosome=chr20",
                "query_vcfs_consulted=False",
                "benchmark_outcomes_consulted=False",
                (
                    "status="
                    "FROZEN_BEFORE_QUERY_VCF_DOWNLOAD_AND_BENCHMARKING"
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )

    print()
    print(
        "selected panel intervals:",
        panel_intervals,
    )
    print(
        "selected panel assessable bases:",
        panel_bases,
    )
    print(
        "selected panel chromosomes:",
        len(panel_chromosomes),
    )

    print()
    print(
        "interval candidates SHA-256:",
        sha256_file(CANDIDATES_OUT),
    )
    print(
        "selected intervals SHA-256:",
        sha256_file(SELECTED_OUT),
    )
    print(
        "panel BED SHA-256:",
        sha256_file(PANEL_BED_OUT),
    )
    print(
        "summary SHA-256:",
        sha256_file(SUMMARY_OUT),
    )
    print(
        "checksum manifest SHA-256:",
        checksums_sha,
    )
    print(
        "lock SHA-256:",
        sha256_file(LOCK_OUT),
    )

    print()
    print(
        "PHASE2_INTERVAL_PANEL_FREEZE_PASS"
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
            "PHASE2_INTERVAL_PANEL_FREEZE_FAIL"
        )
        print(
            f"{type(exc).__name__}: {exc}"
        )
        sys.exit(1)
