# Evidence Atlas — Organism and Assembly Model

Status: FROZEN / APPROVED (`FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION`, 2026-10-01). Locked by [`m0_expansion_protocol.lock`](m0_expansion_protocol.lock).

Machine-readable: [`config/atlas/organisms_assemblies.json`](../../config/atlas/organisms_assemblies.json) (version 0.2.0)

## Identity rules

1. **Organism identity is the NCBI Taxonomy ID.** Scientific and common names
   are labels. Merged taxonomy IDs resolve to the current ID, and the
   source-reported ID is kept.
2. **An assembly is a separate entity** bound to exactly one taxonomy ID and
   identified by INSDC accession.version (`GCA_…`). The RefSeq accession
   (`GCF_…`) and UCSC names (`hg38`, `mm39`, `sacCer3`, `danRer11`) are
   aliases. The GCA and GCF accessions of one assembly share a numeric core,
   and tests check this.
3. **Patch releases are distinct assembly versions.** GRCh38 and GRCh38.p14
   carry different accession versions and are not interchangeable without
   evidence.
4. **A reference sequence set is not an assembly.** The concrete FASTA used
   in an analysis (e.g. the GRCh38 *no-alt analysis set* used by v1) depends
   on ALT/decoy inclusion and contig naming. Truth sources and Atlas-derived
   artifacts record both the assembly and the sequence set.
5. **Strain, breed, cultivar and cell line belong to the sample**, except
   where NCBI Taxonomy itself has a strain-ranked taxon. *S. cerevisiae*
   S288C (559292), the strain on which the R64 reference is built, is one
   such case and is linked to its species (4932) through
   `parent_ncbi_taxonomy_id`.

## Seed registry (non-exhaustive)

| Organism | Taxonomy ID | Assemblies (aliases) | Atlas scope |
|---|---|---|---|
| *Homo sapiens* | 9606 | GRCh37 (hg19) · **GRCh38 (hg38)** · T2T-CHM13v2.0 (hs1) | RELEASED_IN_V1 (GRCh38 only) |
| *Mus musculus* | 10090 | GRCm38 (mm10) · GRCm39 (mm39) | EXPANSION_TARGET |
| *Saccharomyces cerevisiae* | 4932 | — (strain-level assembly below) | EXPANSION_TARGET |
| *S. cerevisiae* S288C | 559292 | R64 (sacCer3) | EXPANSION_TARGET |
| *Danio rerio* | 7955 | GRCz10 (danRer10) · GRCz11 (danRer11) | EXPANSION_TARGET |

**This is not the supported universe.** Any organism with a stable NCBI
Taxonomy ID can be catalogued. The seed list only pre-registers likely
targets. Adding an organism or assembly is a data change validated by
`organism_registry_errors`, not a code change.

### Identifier verification

**Only verified identifiers are in the controlled vocabulary.** The config
schema allows a single verification status, `VERIFIED_AGAINST_NCBI`. Every
identifier was checked by metadata-only lookup on 2026-10-01 using
[`scripts/atlas/verify_seed_assemblies.py`](../../scripts/atlas/verify_seed_assemblies.py).
No sequence data was downloaded.

| What | Source | Checked |
|---|---|---|
| 5 taxonomy IDs | NCBI Datasets v2 `taxonomy/taxon/{id}` | ID, scientific name, rank, immediate parent (559292 → 4932) |
| 16 assembly accessions (8 GCA + 8 GCF) | NCBI Datasets v2 `genome/accession/{acc}/dataset_report` | exact accession.version, assembly name, taxonomy ID, GCA↔GCF pairing, NCBI status |
| 8 UCSC names | UCSC Genome Browser API `list/ucscGenomes` | name exists, same taxonomy ID, cites the same GCA accession |

Provenance is kept in
[`config/atlas/provenance/assembly_verification.json`](../../config/atlas/provenance/assembly_verification.json).
It records the endpoint, retrieval time and SHA-256 of each response, plus
what was observed. Raw responses are stored in `config/atlas/provenance/ncbi_datasets/`.
For UCSC, the relevant entries are stored verbatim along with the SHA-256 of
the full list. `identifier_verification_errors` re-checks every registry
identifier against this record offline. It fails if an identifier has no
VERIFIED lookup, if a snapshot no longer matches its recorded hash, or if an
observed value (name, taxon, NCBI status, UCSC name) disagrees.

**Removed because unverifiable by this method:** the alias `R64-1-1`, the
alias `CHM13v2.0` (the verified assembly name `T2T-CHM13v2.0` is kept),
and organism common names.

**Observed NCBI status, recorded as found:**

| Assembly | GCA status | GCF status | Meaning |
|---|---|---|---|
| GRCh37, GRCh38, GRCm38 | previous | previous | The base accession version; later patch versions exist. These are the exact versions named (v1 used `GCA_000001405.15`). |
| GRCz10 | previous | **suppressed** | NCBI has suppressed the RefSeq record. |
| GRCz11 | current | **suppressed** | NCBI has suppressed the RefSeq record. |
| T2T-CHM13v2.0, GRCm39, R64 | current | current | — |

A suppressed accession is kept only as a historical alias, so records that
cite it can be resolved. It is never canonical. The integrity check rejects a
suppressed INSDC (canonical) accession. Re-run the script, and update the
registry through review, whenever these statuses change.

GRCh38 also carries `used_in_v1: true`. Tests cross-check its accession
against the v1 reference artifact
`GCA_000001405.15_GRCh38_no_alt_analysis_set` in
`data/manifests/source_artifacts.tsv`.

The `includes_decoys` flag of the v1 GRCh38 sequence set is `null`, meaning
unverified. It is a property, not an identifier. M0 does not assert it, and it must be read from the FASTA
sequence names.

## Cross-assembly evidence

v1 evidence is native GRCh38. Whether liftover can ever be a "defensible
mapping path" under criterion E06 is unresolved (U3). Until then, records are
evaluated only against assemblies they were natively produced on.
