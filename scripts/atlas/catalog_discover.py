#!/usr/bin/env python3
"""Run the bounded M1A ENA metadata-discovery pilot.

No sequencing file URL returned by ENA is followed. The only network calls are
to ENA Portal API metadata/introspection/count/search endpoints. Live mode is
restricted to the canonical manual GitHub-hosted workflow; local use is
fixture-only through ``--offline``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from evidence_atlas.catalog.ena import EnaAdapter, FixtureTransport  # noqa: E402
from evidence_atlas.catalog.models import PilotTaxon  # noqa: E402
from evidence_atlas.catalog.pipeline import run_pilot  # noqa: E402


PILOT_TAXA = (
    PilotTaxon(9606, "Homo sapiens", "exact"),
    PilotTaxon(10090, "Mus musculus", "exact"),
    PilotTaxon(4932, "Saccharomyces cerevisiae", "tree"),
    PilotTaxon(7955, "Danio rerio", "exact"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["ena"], default="ena")
    execution = parser.add_mutually_exclusive_group(required=True)
    execution.add_argument(
        "--offline",
        action="store_true",
        help="Use captured fixtures; make no network calls. This is the only local execution mode.",
    )
    execution.add_argument(
        "--cloud-live",
        action="store_true",
        help="Run bounded live discovery on a GitHub-hosted Actions runner only.",
    )
    parser.add_argument(
        "--taxon",
        type=int,
        action="append",
        help="NCBI Taxonomy ID; repeat for multiple taxa. Omit for the four-taxon M1A pilot.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--tax-tree", action="store_true", help="Use tax_tree(ID) for supplied --taxon values.")
    mode.add_argument("--exact", action="store_true", help="Use tax_eq(ID), the default for supplied --taxon values.")
    parser.add_argument("--limit", type=int, default=100, help="Maximum run rows per taxon (M1A maximum: 100).")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--results-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=REPO_ROOT / "tests" / "fixtures" / "catalog" / "ena",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Explicit live smoke check: force a one-record limit per taxon.",
    )
    return parser.parse_args()


def selected_taxa(args: argparse.Namespace) -> tuple[PilotTaxon, ...]:
    if not args.taxon:
        return PILOT_TAXA
    names = {taxon.taxon_id: taxon.scientific_name for taxon in PILOT_TAXA}
    query_mode = "tree" if args.tax_tree else "exact"
    return tuple(PilotTaxon(value, names.get(value, "UNKNOWN"), query_mode) for value in args.taxon)


def cloud_live_allowed(environment: dict[str, str]) -> bool:
    """Live catalog discovery is restricted to a GitHub-hosted Linux runner."""

    return (
        environment.get("GITHUB_ACTIONS") == "true"
        and environment.get("RUNNER_ENVIRONMENT") == "github-hosted"
        and environment.get("RUNNER_OS") == "Linux"
    )


def main() -> int:
    args = parse_args()
    limit = 1 if args.smoke else args.limit
    if not 1 <= limit <= 100:
        raise SystemExit("--limit must be between 1 and 100")
    taxa = selected_taxa(args)
    if len(taxa) * limit > 400:
        raise SystemExit("requested pilot exceeds the M1A maximum of approximately 400 records")
    if args.offline and args.smoke:
        raise SystemExit("--smoke is cloud-live only and cannot be combined with --offline")
    if args.cloud_live and not cloud_live_allowed(dict(os.environ)):
        raise SystemExit(
            "live catalog discovery is disabled outside a GitHub-hosted Linux Actions runner; use --offline locally"
        )

    transport = FixtureTransport(args.fixture_dir) if args.offline else None
    if args.offline:
        offline_root = Path(tempfile.gettempdir()) / "omicsedge-m1a-offline"
        output_dir = args.output_dir or offline_root / "data" / "catalog" / "m1a"
        results_dir = args.results_dir or offline_root / "results" / "catalog"
    else:
        output_dir = args.output_dir or REPO_ROOT / "data" / "catalog" / "m1a"
        results_dir = args.results_dir or REPO_ROOT / "results" / "catalog"
    adapter = EnaAdapter(
        timeout=args.timeout,
        max_retries=args.max_retries,
        min_interval_seconds=0 if args.offline else 0.25,
        transport=transport,
    )
    summary = run_pilot(
        adapter=adapter,
        taxa=taxa,
        limit=limit,
        output_dir=output_dir,
        results_dir=results_dir,
        technology_taxonomy_path=REPO_ROOT / "config" / "atlas" / "technology_taxonomy.json",
    )
    print(json.dumps(summary["counts"], indent=2, sort_keys=True))
    print(f"output_dir={output_dir}")
    print(f"results_dir={results_dir}")
    print("M1A_CATALOG_DISCOVERY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
