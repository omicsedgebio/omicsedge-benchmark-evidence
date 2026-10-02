# M1A — Bounded Public Data Catalog Pilot

Status: **IMPLEMENTATION READY / CANONICAL CLOUD PILOT PENDING REVIEW**

M1A builds and validates the metadata-discovery core of the M1 Public Data
Catalog against a small ENA pilot. It is not an Evidence Atlas release, does
not validate evidence, and does not ingest the complete public archive. The
local live pilot used during development was a proof only: its generated data
and reports were removed and are not canonical M1A results.

## Canonical-run policy

- The canonical M1A pilot must be produced by manually dispatching
  `.github/workflows/m1a_catalog_discovery.yml` on its GitHub-hosted runner.
- From this policy onward, live catalog discovery and normalization run
  off-Mac. Live expansion data and catalog-compute outputs do not persist on
  a developer machine.
- Local development and testing use only the captured offline fixtures under
  `tests/fixtures/catalog/ena/`.
- The CLI refuses live mode unless it detects a GitHub-hosted Linux Actions
  environment. Local use requires `--offline`.
- No mode downloads raw sequencing payloads. Source-hosted file URLs,
  publisher checksums and sizes are metadata only.

## Scientific boundary

- Metadata only. FASTQ, BAM, CRAM and other sequencing file payloads are not
  downloaded. ENA file URLs, publisher checksums and sizes may be recorded.
- Rules only. No ML model is trained or used.
- Every lifecycle record remains `CATALOGUED` in `PUBLIC_DATA_CATALOG`.
  No record is made `ELIGIBLE`, `VALIDATED` or `RELEASED`.
- Evidence Atlas v1.0.0 and the locked M0 protocol remain unchanged.

## Source and identity

The first adapter uses the public ENA Portal API `read_run` result. It checks
the API's own `returnFields` and `searchFields` responses before selecting a
fixed list of metadata fields. It obtains archive-scale run counts from the
official `/count` aggregate endpoint and fetches at most 100 metadata rows for
each pilot taxon.

NCBI SRA, ENA and DDBJ DRA exchange records through INSDC. A run visible at
several partners is therefore one dataset, keyed by its canonical SRR, ERR or
DRR accession. Source snapshots remain independently attributable, but a
mirror never increases the distinct-run count.

ENA Portal search supports bounded `limit` queries and documents `limit=0` to
request all matching records. M1A intentionally uses a bounded limit of at
most 100 rows per pilot taxon and never uses `limit=0`. Offset pagination is
not an M1A requirement.

Full or incremental M1 ingestion will not request millions of records as one
monolithic response. Before M1B can ingest larger result sets, it must validate
a deterministic query-partition/window method using searchable temporal fields
such as `first_public` or `last_updated`. Each window must record and reconcile
its `/count` aggregate, retain request provenance, and deduplicate across
windows by canonical INSDC run accession. M1A does not prescribe or guess
date-query syntax that has not been separately validated.

Two further live response quirks were observed. Introspection rows with an
empty description omit the middle TSV cell, leaving an unambiguous
`columnId<TAB>type` row under a three-column header. ENA also intermittently
returned an error payload with HTTP 200 during pilot probes. The adapter
handles the former only in the introspection parser and validates/retries the
latter; ordinary search-result TSV remains strict.

## Pilot scope

| Taxon | NCBI Taxonomy ID | Query |
|---|---:|---|
| *Homo sapiens* | 9606 | `tax_eq(9606)` |
| *Mus musculus* | 10090 | `tax_eq(10090)` |
| *Saccharomyces cerevisiae* | 4932 | `tax_tree(4932)` |
| *Danio rerio* | 7955 | `tax_eq(7955)` |

The yeast subtree query keeps strain-level records in scope. These taxa are a
validation pilot, not a statement of the catalog's eventual supported
universe. The adapter contract and NCBI Taxonomy identity model are
species-agnostic.

## Multi-sample catalog relationships

ENA can report more than one sample accession for one run. The M1 catalog
transport preserves every source-reported BioSample and INSDC sample accession
as a `SOURCE_REPORTED_SAMPLE` relationship to that run. It does not select the
first accession or collapse several source samples into one normalized sample
identity.

The frozen M0 `SEQUENCING_RUN` schema has a singular `sample_id`. For a
multi-sample catalog run, M1 therefore uses a deterministic unresolved sample
reference only to satisfy the frozen entity shape, records
`MULTIPLE_SOURCE_SAMPLES`, lists all source relationships separately, and
keeps the lifecycle state `CATALOGUED`. A reviewed, versioned schema amendment
is required before such a record could move beyond the catalog layer.

## Assembly and unresolved instruments

Reference assembly may legitimately be `UNKNOWN` at catalog stage because ENA
`read_run` metadata does not necessarily report a reference assembly. M1A
never invents one. Unknown assembly is valid for a `CATALOGUED` record, while
the frozen eligibility policy still requires assembly resolution before a
record can become `ELIGIBLE`.

The development proof observed `Illumina HiSeq 1500` and
`Illumina HiSeq 3000`. M1A keeps both instrument families/models unresolved.
They are vocabulary-extension candidates requiring authoritative verification
and a reviewed, versioned amendment; the frozen M0 technology vocabulary is
not modified.

## Reproduction

Install the project and development dependencies. Local execution is offline:

```bash
python -m pytest tests/catalog
python scripts/atlas/catalog_discover.py --source ena --offline --limit 2
```

Offline CLI outputs default to an operating-system temporary directory. Local
live commands are rejected. Canonical compact outputs are created only inside
the manual GitHub Actions job and retained as its artifact, not as local
working-tree data. `SOURCE_REPORTED_DISCOVERED`, `NORMALIZED` and `UNRESOLVED`
counts remain distinct, and archive-scale counts identify the ENA aggregate
API rather than full enumeration.

## Automation boundary

`.github/workflows/m1a_catalog_discovery.yml` is manual-only
(`workflow_dispatch`). It uses a standard GitHub-hosted Linux runner, needs no
secrets, runs the offline catalog tests, performs the bounded discovery, and
checks the M0 lock and v1 freeze before and after. It has no cron schedule and
does not deploy anything. It writes a concise job summary and uploads one
size-checked metadata-only artifact containing the pilot manifest, captured
metadata responses, normalized catalog outputs, provenance metadata, summary
JSON/TSV and unresolved-metadata TSV. FASTQ, BAM, CRAM and other sequencing
payloads are forbidden from the artifact.
