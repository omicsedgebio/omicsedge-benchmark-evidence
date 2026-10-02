# Evidence Atlas — Source Strategy

Status: FROZEN / APPROVED (`FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION`, 2026-10-01). Locked by [`m0_expansion_protocol.lock`](m0_expansion_protocol.lock). Nothing is ingested in M0.

Machine-readable: [`config/atlas/sources.json`](../../config/atlas/sources.json)

## Roles

| Role | Meaning |
|---|---|
| `DISCOVERY_AND_METADATA` | Feeds the Public Data Catalog. On its own, it never makes a record evidence. |
| `REFERENCE_VOCABULARY` | Supplies identities such as taxonomy and assembly accessions. |
| `TRUTH_AND_EVIDENCE` | Can supply truth/comparator resources or evidence-grade outputs, subject to eligibility. |
| `DISCOVERY_ONLY_UNTIL_TERMS_REVIEWED` | May be catalogued. Cannot pass E10 until its terms are read and snapshotted. |

## Initial sources

| Source | Contributes | Canonical identifiers | Duplication risk | Dedup strategy | Role |
|---|---|---|---|---|---|
| NCBI SRA | run/experiment metadata, instrument string, INSDC platform term, library fields, base/read counts, links | run, experiment, study accessions | INSDC mirroring; replaced/suppressed runs | key on `run_accession` in the INSDC group; record suppression | Discovery |
| ENA | same, plus file URLs with MD5 and sizes, taxonomy ID | run, experiment, study, sample accessions | INSDC mirroring | same run key; may be preferred for file checksums; never adds to counts | Discovery |
| DDBJ DRA | same | run accession | INSDC mirroring | same run key | Discovery |
| NCBI BioProject | study identity and hierarchy | BioProject accession | umbrella projects | count leaf projects | Discovery |
| NCBI BioSample | sample identity, taxonomy, strain/line, aliases | BioSample accession | one biological source registered as several BioSamples | BioSample is the key; source equivalence only via a curated alias table | Discovery |
| NCBI Taxonomy | taxonomy IDs, ranks, merges | taxonomy ID | merged IDs | resolve to current ID; keep reported ID | Vocabulary |
| NCBI Datasets (Assembly) | assembly accession.version, GCA/GCF pairing | `GCA_` accession | GCA vs GCF; patch versions | explicit pairing; versions distinct | Vocabulary |
| Genome in a Bottle | truth VCF/BED by sample, version and assembly; stratifications; reference sets; data indexes | sample, release version, file checksum | data also in INSDC; mirrored hosts | truth keyed by (sample, version, assembly, checksum); reads keyed by INSDC run | Truth & evidence |
| precisionFDA Truth Challenge V2 | submission VCFs, pipeline metadata | submission id + sample | already in v1.0.0 | reference existing v1 records; never re-add | Truth & evidence |
| Vendor public datasets | runs and sometimes VCFs on reference samples; rich chemistry/basecaller detail | vendor dataset id, file checksum, INSDC run if present | also in INSDC; re-basecalled versions of one raw signal | link to INSDC run; re-basecalls are derived artifacts | Discovery until terms reviewed |
| Europe PMC / PubMed | DOI/PMID/PMCID, dataset mentions | DOI | preprint vs journal version | key on DOI; link versions | Discovery |

## INSDC mirroring: never triple-count

NCBI SRA, ENA and DDBJ exchange records under INSDC. One run appears in all
three, with the **same** run accession. The accession prefix (`SRR`/`ERR`/`DRR`)
shows where the run was submitted. It does not create a separate dataset.

Rules:

1. The independent unit for counting is the distinct `run_accession` within
   the `insdc` mirror group.
2. Each archive response is kept as its own SOURCE_RECORD, because snapshots
   and file checksums can differ. All of them share one `canonical_accession`
   and link to one CATALOG_RECORD.
3. Benchmark resources that point to INSDC runs, such as GIAB data indexes,
   **link to** the INSDC record. They are not counted again.
4. Derived artifacts (VCF, BAM, CRAM, re-basecalled reads) never increase the
   dataset count of their source run.
5. Any aggregate count published anywhere states its counting unit and the
   layer it counts. Example: "N distinct INSDC runs catalogued", which is
   different from "N validated records released".

## Licensing and source terms

- Every SOURCE_RECORD and TRUTH_SOURCE carries a `source_terms` object.
  Marking terms `COMPATIBLE` or `INCOMPATIBLE` requires a snapshot hash and a
  retrieval timestamp of the terms text. Records with `UNREVIEWED` terms
  cannot leave the catalog layer (schema-enforced).
- **Controlled-access data** (e.g. dbGaP, EGA) is out of scope. Criterion E03
  makes it INELIGIBLE. At most its public study-level metadata may be
  catalogued.
- Public availability is not the same as permission to redistribute. The
  Atlas references source-hosted files by URI and checksum. It redistributes
  only its own compact derived artifacts, and only where source terms allow.
- The `terms_review` entries in `sources.json` are pointers for review. They
  are not legal conclusions.

## M1 boundary

M1 implements metadata discovery for a bounded subset of these sources (see
[../roadmap.md](../roadmap.md)). Adding a source requires an entry in
`sources.json` with all required fields, which tests enforce.
