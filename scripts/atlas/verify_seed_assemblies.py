#!/usr/bin/env python3
"""Verify seed organisms and assemblies against NCBI / UCSC (metadata only).

For every organism in ``config/atlas/organisms_assemblies.json`` this queries
the NCBI Datasets v2 taxonomy endpoint and checks the taxonomy ID, scientific
name, rank and (where declared) that the parent taxon is the immediate
ancestor in the NCBI lineage.

For every assembly in ``config/atlas/organisms_assemblies.json`` this queries
the NCBI Datasets v2 ``dataset_report`` endpoint for the INSDC (GCA) and
RefSeq (GCF) accessions, and checks that:

* NCBI returns exactly one report for the exact accession.version;
* the assembly name and taxonomy ID match the seed entry;
* the GCA and GCF accessions are each other's ``paired_accession``;
* the UCSC database name (``ucsc_db``), if given, is listed by the UCSC
  Genome Browser API for the same taxonomy ID and the same GCA accession.

Only JSON metadata reports are retrieved; no sequence data is downloaded.
Each raw response is stored under ``config/atlas/provenance/ncbi_datasets/``
and summarised, with its SHA-256 and retrieval time, in
``config/atlas/provenance/assembly_verification.json``.

The script never edits the controlled vocabulary itself: an accession is only
marked verified in ``organisms_assemblies.json`` by a reviewed change that
cites the verification record.

Usage (from the repository root):

    python scripts/atlas/verify_seed_assemblies.py
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "config" / "atlas" / "organisms_assemblies.json"
PROVENANCE_DIR = REPO_ROOT / "config" / "atlas" / "provenance"
SNAPSHOT_DIR = PROVENANCE_DIR / "ncbi_datasets"
RECORD = PROVENANCE_DIR / "assembly_verification.json"

ENDPOINT = (
    "https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{acc}/dataset_report"
    "?filters.assembly_version=all_assemblies"
)
TAXON_ENDPOINT = "https://api.ncbi.nlm.nih.gov/datasets/v2/taxonomy/taxon/{taxid}"
UCSC_ENDPOINT = "https://api.genome.ucsc.edu/list/ucscGenomes"
# Stay well under the anonymous E-utilities/Datasets rate limit.
REQUEST_INTERVAL_S = 0.5


def fetch(accession: str) -> tuple[str, bytes, str]:
    return fetch_url(ENDPOINT.format(acc=accession))


def fetch_url(url: str) -> tuple[str, bytes, str]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    retrieved_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return url, body, retrieved_at


def check_organism(organism: dict, body: bytes) -> dict:
    nodes = json.loads(body).get("taxonomy_nodes", [])
    failures: list[str] = []
    observed = None
    if len(nodes) != 1 or "taxonomy" not in nodes[0]:
        failures.append(f"expected one taxonomy node for {organism['ncbi_taxonomy_id']}")
    else:
        tax = nodes[0]["taxonomy"]
        lineage = tax.get("lineage") or []
        observed = {
            "tax_id": tax.get("tax_id"),
            "organism_name": tax.get("organism_name"),
            "rank": tax.get("rank"),
            "immediate_parent": lineage[-1] if lineage else None,
        }
        if observed["tax_id"] != organism["ncbi_taxonomy_id"]:
            failures.append(f"tax_id {observed['tax_id']} != {organism['ncbi_taxonomy_id']}")
        if observed["organism_name"] != organism["scientific_name"]:
            failures.append(f"name {observed['organism_name']!r} != {organism['scientific_name']!r}")
        if (observed["rank"] or "").lower() != organism["rank"].lower():
            failures.append(f"rank {observed['rank']} != {organism['rank']}")
        parent = organism.get("parent_ncbi_taxonomy_id")
        if parent is not None and observed["immediate_parent"] != parent:
            failures.append(f"immediate parent {observed['immediate_parent']} != {parent}")
    return {"observed": observed, "failures": failures}


def check_ucsc(assembly: dict, genomes: dict) -> dict:
    db = assembly["ucsc_db"]
    entry = genomes.get(db)
    failures: list[str] = []
    observed = None
    if entry is None:
        failures.append(f"UCSC database {db} not listed")
    else:
        observed = {k: entry.get(k) for k in ("description", "scientificName", "taxId", "sourceName")}
        if entry.get("taxId") != assembly["ncbi_taxonomy_id"]:
            failures.append(f"UCSC {db} taxId {entry.get('taxId')} != {assembly['ncbi_taxonomy_id']}")
        if f"({assembly['insdc_accession']})" not in (entry.get("sourceName") or ""):
            failures.append(f"UCSC {db} sourceName does not cite {assembly['insdc_accession']}")
    return {"ucsc_db": db, "observed": observed, "failures": failures}


def check(assembly: dict, accession: str, expected_pair: str | None, body: bytes) -> dict:
    payload = json.loads(body)
    reports = [r for r in payload.get("reports", []) if r.get("accession") == accession]
    observed: dict = {"report_count": len(reports)}
    failures: list[str] = []
    if len(reports) != 1:
        failures.append(f"expected exactly one report for {accession}, got {len(reports)}")
    else:
        report = reports[0]
        info = report.get("assembly_info", {})
        observed.update(
            assembly_name=info.get("assembly_name"),
            tax_id=report.get("organism", {}).get("tax_id"),
            organism_name=report.get("organism", {}).get("organism_name"),
            paired_accession=report.get("paired_accession"),
            current_accession=report.get("current_accession"),
            ncbi_assembly_status=info.get("assembly_status"),
            release_date=info.get("release_date"),
        )
        if observed["assembly_name"] != assembly["assembly_name"]:
            failures.append(
                f"assembly_name {observed['assembly_name']!r} != {assembly['assembly_name']!r}"
            )
        if observed["tax_id"] != assembly["ncbi_taxonomy_id"]:
            failures.append(f"tax_id {observed['tax_id']} != {assembly['ncbi_taxonomy_id']}")
        if expected_pair is not None and observed["paired_accession"] != expected_pair:
            failures.append(f"paired_accession {observed['paired_accession']} != {expected_pair}")
    return {"observed": observed, "failures": failures}


def main() -> int:
    registry = json.loads(REGISTRY.read_text())
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ucsc_url, ucsc_body, ucsc_retrieved_at = fetch_url(UCSC_ENDPOINT)
    genomes = json.loads(ucsc_body)["ucscGenomes"]
    ucsc_dbs = sorted(a["ucsc_db"] for a in registry["assemblies"] if "ucsc_db" in a)
    # The full UCSC list is large and changes often; keep the relevant
    # entries verbatim plus the SHA-256 of the full response.
    ucsc_extract = SNAPSHOT_DIR.parent / "ucsc_genomes_extract.json"
    ucsc_extract.write_text(
        json.dumps({db: genomes.get(db) for db in ucsc_dbs}, indent=2, sort_keys=True) + "\n"
    )
    organism_results = []
    for organism in registry["organisms"]:
        taxid = organism["ncbi_taxonomy_id"]
        url, body, retrieved_at = fetch_url(TAXON_ENDPOINT.format(taxid=taxid))
        snapshot = SNAPSHOT_DIR / f"taxon_{taxid}.json"
        snapshot.write_bytes(body)
        outcome = check_organism(organism, body)
        organism_results.append(
            {
                "ncbi_taxonomy_id": taxid,
                "scientific_name": organism["scientific_name"],
                "verdict": "VERIFIED" if not outcome["failures"] else "FAILED",
                "endpoint": url,
                "retrieved_at": retrieved_at,
                "response_sha256": hashlib.sha256(body).hexdigest(),
                "response_snapshot": str(snapshot.relative_to(REPO_ROOT)),
                **outcome,
            }
        )
        print(f"taxon {taxid:<8d} {organism_results[-1]['verdict']}")
        time.sleep(REQUEST_INTERVAL_S)

    results = []
    for assembly in registry["assemblies"]:
        pairs = [(assembly["insdc_accession"], assembly.get("refseq_accession"))]
        if "refseq_accession" in assembly:
            pairs.append((assembly["refseq_accession"], assembly["insdc_accession"]))
        checks = []
        for accession, expected_pair in pairs:
            url, body, retrieved_at = fetch(accession)
            snapshot = SNAPSHOT_DIR / f"{accession}.dataset_report.json"
            snapshot.write_bytes(body)
            outcome = check(assembly, accession, expected_pair, body)
            checks.append(
                {
                    "accession": accession,
                    "endpoint": url,
                    "retrieved_at": retrieved_at,
                    "response_sha256": hashlib.sha256(body).hexdigest(),
                    "response_snapshot": str(snapshot.relative_to(REPO_ROOT)),
                    **outcome,
                }
            )
            time.sleep(REQUEST_INTERVAL_S)
        ucsc = check_ucsc(assembly, genomes) if "ucsc_db" in assembly else None
        verified = all(not c["failures"] for c in checks) and not (ucsc and ucsc["failures"])
        results.append(
            {
                "assembly_id": assembly["assembly_id"],
                "assembly_name": assembly["assembly_name"],
                "ncbi_taxonomy_id": assembly["ncbi_taxonomy_id"],
                "verdict": "VERIFIED" if verified else "FAILED",
                "checks": checks,
                "ucsc_check": ucsc,
            }
        )
        print(f"{assembly['assembly_id']:14s} {results[-1]['verdict']}")

    record = {
        "verification_method": (
            "NCBI Datasets v2 taxonomy taxon report: taxonomy ID, scientific name, "
            "rank and immediate parent; NCBI Datasets v2 genome dataset_report (JSON metadata only): exact "
            "accession.version, assembly name, taxonomy ID and GCA/GCF pairing; "
            "UCSC Genome Browser API ucscGenomes list: database name, taxonomy ID "
            "and cited GCA accession"
        ),
        "script": "scripts/atlas/verify_seed_assemblies.py",
        "ucsc_source": {
            "endpoint": ucsc_url,
            "retrieved_at": ucsc_retrieved_at,
            "response_sha256": hashlib.sha256(ucsc_body).hexdigest(),
            "extract": str(ucsc_extract.relative_to(REPO_ROOT)),
        },
        "sequence_data_downloaded": False,
        "organism_results": organism_results,
        "results": results,
    }
    RECORD.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    failed = [r["assembly_id"] for r in results if r["verdict"] != "VERIFIED"] + [
        f"taxon:{r['ncbi_taxonomy_id']}" for r in organism_results if r["verdict"] != "VERIFIED"
    ]
    print("ASSEMBLY_VERIFICATION_PASS" if not failed else f"ASSEMBLY_VERIFICATION_FAIL {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
