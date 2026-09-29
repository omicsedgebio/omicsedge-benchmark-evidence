#!/usr/bin/env python3

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]

PHASE1A = (
    PROJECT_ROOT
    / "data/phase1a/omicsedge_phase1a_results"
)

PHASE1B = (
    PROJECT_ROOT
    / "results/phase1b"
)

SQL_PATH = (
    PROJECT_ROOT
    / "sql/phase1b/variant_evidence.sql"
)

DB_PATH = (
    PHASE1B
    / "phase1b_registry.duckdb"
)

EXAMPLE_QUERY_PATH = (
    PHASE1B
    / "example_variant_evidence_query.tsv"
)

SUMMARY_PATH = (
    PHASE1B
    / "variant_query_summary.json"
)

CHECKSUMS_PATH = (
    PHASE1A
    / "checksums.sha256"
)


EXPECTED_VARIANTS_SHA256 = (
    "c08939e19a71f140dd7c1901df0a7eafd528a4d35c4808701c3282cb4a008968"
)

EXPECTED_LINKS_SHA256 = (
    "bd695855e3e9fb6c80bd5d16d93f1a64bffc25da71754614f640e225bdb1e76e"
)

EXPECTED_VARIANT_COUNT = 1666
EXPECTED_LINK_COUNT = 3332


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


def phase1a_checksums() -> dict[str, str]:

    result = {}

    for raw in CHECKSUMS_PATH.read_text(
        encoding="utf-8"
    ).splitlines():

        if not raw.strip():
            continue

        digest, relative = raw.split(
            "  ",
            1,
        )

        result[relative] = digest

    return result


def verify_phase1a_file(
    relative: str,
    checksums: dict[str, str],
) -> None:

    require(
        relative in checksums,
        (
            "missing detached Phase 1A checksum "
            f"for {relative}"
        ),
    )

    path = (
        PHASE1A
        / relative
    )

    require(
        path.is_file(),
        f"missing Phase 1A file: {path}",
    )

    observed = sha256_file(
        path
    )

    require(
        observed == checksums[relative],
        (
            f"Phase 1A checksum mismatch: {relative}\n"
            f"expected: {checksums[relative]}\n"
            f"observed: {observed}"
        ),
    )


def write_query_tsv(
    connection,
    variant_id: str,
) -> tuple[int, list[str]]:

    sql = SQL_PATH.read_text(
        encoding="utf-8"
    )

    relation = connection.execute(
        sql,
        [variant_id],
    )

    columns = [
        description[0]
        for description
        in relation.description
    ]

    rows = relation.fetchall()

    with EXAMPLE_QUERY_PATH.open(
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
            columns
        )

        for row in rows:
            normalized = []

            for value in row:

                if value is None:
                    normalized.append(
                        ""
                    )

                elif isinstance(
                    value,
                    (list, tuple),
                ):
                    normalized.append(
                        json.dumps(
                            value,
                            separators=(",", ":"),
                        )
                    )

                else:
                    normalized.append(
                        str(value)
                    )

            writer.writerow(
                normalized
            )

    return (
        len(rows),
        columns,
    )


def main() -> int:

    print("=" * 78)

    print(
        "PROJECT 003 — PHASE 1B "
        "VARIANT EVIDENCE QUERY"
    )

    print("=" * 78)

    PHASE1B.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Verify Phase 1B materialized entities.
    # --------------------------------------------------------

    variants_path = (
        PHASE1B
        / "variants.parquet"
    )

    links_path = (
        PHASE1B
        / "event_variant_links.parquet"
    )

    require(
        sha256_file(
            variants_path
        )
        == EXPECTED_VARIANTS_SHA256,
        "variants.parquet changed",
    )

    require(
        sha256_file(
            links_path
        )
        == EXPECTED_LINKS_SHA256,
        "event_variant_links.parquet changed",
    )

    print(
        "PASS  Phase 1B materialized entity checksums"
    )

    # --------------------------------------------------------
    # Verify Phase 1A query inputs.
    # --------------------------------------------------------

    checksums = phase1a_checksums()

    for relative in (
        "events.parquet",
        "observations.parquet",
        "experiments.tsv",
        "benchmark_runs.tsv",
    ):
        verify_phase1a_file(
            relative,
            checksums,
        )

    print(
        "PASS  Phase 1A query-input checksums"
    )

    # --------------------------------------------------------
    # Build database from immutable artifacts.
    # --------------------------------------------------------

    if DB_PATH.exists():
        DB_PATH.unlink()

    con = duckdb.connect(
        str(DB_PATH)
    )

    con.execute(
        """
        CREATE TABLE variants AS
        SELECT *
        FROM read_parquet(?)
        """,
        [str(variants_path)],
    )

    con.execute(
        """
        CREATE TABLE event_variant_links AS
        SELECT *
        FROM read_parquet(?)
        """,
        [str(links_path)],
    )

    con.execute(
        """
        CREATE TABLE phase1a_events AS
        SELECT *
        FROM read_parquet(?)
        """,
        [
            str(
                PHASE1A
                / "events.parquet"
            )
        ],
    )

    con.execute(
        """
        CREATE TABLE phase1a_observations AS
        SELECT *
        FROM read_parquet(?)
        """,
        [
            str(
                PHASE1A
                / "observations.parquet"
            )
        ],
    )

    con.execute(
        """
        CREATE TABLE experiments AS
        SELECT *
        FROM read_csv(
            ?,
            delim = '\t',
            header = true,
            all_varchar = true
        )
        """,
        [
            str(
                PHASE1A
                / "experiments.tsv"
            )
        ],
    )

    con.execute(
        """
        CREATE TABLE benchmark_runs AS
        SELECT *
        FROM read_csv(
            ?,
            delim = '\t',
            header = true,
            all_varchar = true
        )
        """,
        [
            str(
                PHASE1A
                / "benchmark_runs.tsv"
            )
        ],
    )

    print(
        "PASS  DuckDB registry created"
    )

    # --------------------------------------------------------
    # Reconcile entity counts.
    # --------------------------------------------------------

    variant_count = con.execute(
        "SELECT count(*) FROM variants"
    ).fetchone()[0]

    link_count = con.execute(
        "SELECT count(*) FROM event_variant_links"
    ).fetchone()[0]

    event_count = con.execute(
        "SELECT count(*) FROM phase1a_events"
    ).fetchone()[0]

    observation_count = con.execute(
        "SELECT count(*) FROM phase1a_observations"
    ).fetchone()[0]

    experiment_count = con.execute(
        "SELECT count(*) FROM experiments"
    ).fetchone()[0]

    benchmark_run_count = con.execute(
        "SELECT count(*) FROM benchmark_runs"
    ).fetchone()[0]


    require(
        variant_count
        == EXPECTED_VARIANT_COUNT,
        (
            "DuckDB VARIANT count mismatch: "
            f"{variant_count}"
        ),
    )

    require(
        link_count
        == EXPECTED_LINK_COUNT,
        (
            "DuckDB EVENT_VARIANT_LINK "
            f"count mismatch: {link_count}"
        ),
    )

    require(
        event_count == 3602,
        (
            "Phase 1A EVENT count mismatch: "
            f"{event_count}"
        ),
    )

    require(
        observation_count == 7204,
        (
            "Phase 1A OBSERVATION count mismatch: "
            f"{observation_count}"
        ),
    )

    require(
        experiment_count == 2,
        (
            "EXPERIMENT count mismatch: "
            f"{experiment_count}"
        ),
    )

    require(
        benchmark_run_count == 2,
        (
            "BENCHMARK_RUN count mismatch: "
            f"{benchmark_run_count}"
        ),
    )

    print(
        "PASS  DuckDB row-count reconciliation"
    )

    # --------------------------------------------------------
    # Select a deterministic example VARIANT.
    #
    # This is not selected by performance or outcome.
    # Lexicographic variant_id order is used only for a stable
    # reproducible demonstration query.
    # --------------------------------------------------------

    example_variant = con.execute(
        """
        SELECT variant_id
        FROM variants
        ORDER BY variant_id
        LIMIT 1
        """
    ).fetchone()[0]

    print(
        "example variant:",
        example_variant,
    )

    # --------------------------------------------------------
    # Execute product-style query.
    # --------------------------------------------------------

    (
        query_row_count,
        query_columns,
    ) = write_query_tsv(
        con,
        example_variant,
    )

    require(
        query_row_count > 0,
        "example variant query returned zero rows",
    )

    required_columns = {
        "variant_id",
        "event_variant_link_id",
        "event_id",
        "benchmark_run_id",
        "experiment_id",
        "technology",
        "observation_id",
        "side",
        "raw_decision",
        "raw_match_kind",
        "comparator",
        "comparator_version",
        "truth_artifact_id",
        "phase1b_identity_provenance",
    }

    require(
        required_columns
        <= set(query_columns),
        (
            "variant query missing required columns: "
            f"{sorted(required_columns - set(query_columns))}"
        ),
    )

    print(
        "PASS  product query returns evidence"
    )

    # --------------------------------------------------------
    # Validate preservation of run/event context.
    # --------------------------------------------------------

    query_stats = con.execute(
        """
        WITH q AS (
            SELECT
                v.variant_id,
                evl.event_variant_link_id,
                e.event_id,
                br.benchmark_run_id,
                ex.experiment_id,
                ex.technology,
                o.observation_id,
                o.side,
                o.raw_decision
            FROM variants v
            JOIN event_variant_links evl
              ON evl.variant_id = v.variant_id
            JOIN phase1a_events e
              ON e.event_id = evl.event_id
            JOIN phase1a_observations o
              ON o.event_id = e.event_id
             AND o.benchmark_run_id = e.benchmark_run_id
            JOIN benchmark_runs br
              ON br.benchmark_run_id = e.benchmark_run_id
            JOIN experiments ex
              ON ex.experiment_id = br.experiment_id
            WHERE v.variant_id = ?
        )
        SELECT
            count(*) AS rows,
            count(DISTINCT event_id) AS events,
            count(DISTINCT benchmark_run_id) AS runs,
            count(DISTINCT experiment_id) AS experiments,
            count(DISTINCT technology) AS technologies,
            count(DISTINCT observation_id) AS observations
        FROM q
        """,
        [example_variant],
    ).fetchone()

    (
        rows_count,
        distinct_events,
        distinct_runs,
        distinct_experiments,
        distinct_technologies,
        distinct_observations,
    ) = query_stats


    require(
        distinct_events == 2,
        (
            "example variant should preserve "
            f"2 run-scoped events; observed "
            f"{distinct_events}"
        ),
    )

    require(
        distinct_runs == 2,
        (
            "example variant should preserve "
            f"2 benchmark runs; observed "
            f"{distinct_runs}"
        ),
    )

    require(
        distinct_experiments == 2,
        (
            "example variant should preserve "
            f"2 experiments; observed "
            f"{distinct_experiments}"
        ),
    )

    require(
        distinct_technologies == 2,
        (
            "example variant should expose "
            f"2 technologies; observed "
            f"{distinct_technologies}"
        ),
    )

    require(
        distinct_observations >= 2,
        (
            "example variant returned too few "
            "observations"
        ),
    )

    print(
        "PASS  variant query preserves "
        "2 events / 2 runs / 2 experiments / 2 technologies"
    )

    # --------------------------------------------------------
    # Verify that querying a biological variant never forces
    # consensus across technologies.
    #
    # The query contains raw observation decisions as separate
    # rows. No consensus/reliability/trust column is generated.
    # --------------------------------------------------------

    forbidden_columns = {
        "consensus",
        "consensus_decision",
        "reliability_score",
        "confidence_score",
        "trust_score",
        "trusted",
        "technology_winner",
    }

    require(
        not (
            forbidden_columns
            & set(query_columns)
        ),
        (
            "forbidden consensus/reliability field "
            "found in product query"
        ),
    )

    print(
        "PASS  no forced consensus or reliability score"
    )

    # --------------------------------------------------------
    # Check that the entire linked registry remains queryable,
    # not merely the example record.
    # --------------------------------------------------------

    global_stats = con.execute(
        """
        SELECT
            count(DISTINCT v.variant_id),
            count(DISTINCT evl.event_variant_link_id),
            count(DISTINCT e.event_id),
            count(DISTINCT br.benchmark_run_id),
            count(DISTINCT ex.experiment_id)
        FROM variants v
        JOIN event_variant_links evl
          ON evl.variant_id = v.variant_id
        JOIN phase1a_events e
          ON e.event_id = evl.event_id
        JOIN benchmark_runs br
          ON br.benchmark_run_id = e.benchmark_run_id
        JOIN experiments ex
          ON ex.experiment_id = br.experiment_id
        """
    ).fetchone()

    require(
        global_stats
        == (
            1666,
            3332,
            3332,
            2,
            2,
        ),
        (
            "global linked-registry reconciliation "
            f"failed: {global_stats}"
        ),
    )

    print(
        "PASS  global linked-registry reconciliation"
    )

    con.close()

    # --------------------------------------------------------
    # Output identities.
    # --------------------------------------------------------

    db_sha = sha256_file(
        DB_PATH
    )

    query_sha = sha256_file(
        EXAMPLE_QUERY_PATH
    )

    sql_sha = sha256_file(
        SQL_PATH
    )

    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    summary = {
        "project":
            "Project 003",

        "phase":
            "1B",

        "operation":
            "VARIANT_EVIDENCE_PRODUCT_QUERY",

        "duckdb_version":
            duckdb.__version__,

        "variant_count":
            variant_count,

        "event_variant_link_count":
            link_count,

        "phase1a_event_count":
            event_count,

        "phase1a_observation_count":
            observation_count,

        "experiment_count":
            experiment_count,

        "benchmark_run_count":
            benchmark_run_count,

        "example_variant_id":
            example_variant,

        "example_query_row_count":
            query_row_count,

        "example_distinct_events":
            distinct_events,

        "example_distinct_runs":
            distinct_runs,

        "example_distinct_experiments":
            distinct_experiments,

        "example_distinct_technologies":
            distinct_technologies,

        "example_distinct_observations":
            distinct_observations,

        "consensus_generated":
            False,

        "reliability_score_generated":
            False,

        "phase1a_entities_modified":
            False,

        "sql_path":
            str(
                SQL_PATH.relative_to(
                    PROJECT_ROOT
                )
            ),

        "sql_sha256":
            sql_sha,

        "database_path":
            str(
                DB_PATH.relative_to(
                    PROJECT_ROOT
                )
            ),

        "database_sha256":
            db_sha,

        "example_query_path":
            str(
                EXAMPLE_QUERY_PATH.relative_to(
                    PROJECT_ROOT
                )
            ),

        "example_query_sha256":
            query_sha,
    }

    SUMMARY_PATH.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print()

    print(
        "example query rows:",
        query_row_count,
    )

    print(
        "SQL SHA-256:",
        sql_sha,
    )

    print(
        "DuckDB SHA-256:",
        db_sha,
    )

    print(
        "example query SHA-256:",
        query_sha,
    )

    print(
        "summary SHA-256:",
        sha256_file(
            SUMMARY_PATH
        ),
    )

    print()

    print(
        "PHASE1B_VARIANT_EVIDENCE_QUERY_PASS"
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
            "PHASE1B_VARIANT_EVIDENCE_QUERY_FAIL"
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        sys.exit(1)
