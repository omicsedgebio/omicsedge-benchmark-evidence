# Evidence Atlas — Technology Taxonomy

Status: FROZEN / APPROVED (`FROZEN_APPROVED_BEFORE_M1_IMPLEMENTATION`, 2026-10-01). Locked by [`m0_expansion_protocol.lock`](m0_expansion_protocol.lock).

Machine-readable: [`config/atlas/technology_taxonomy.json`](../../config/atlas/technology_taxonomy.json) (version 0.1.0)

## Hierarchy

```text
technology_family      measurement principle            e.g. nanopore
  └─ vendor            manufacturer                     e.g. Oxford Nanopore Technologies
      └─ instrument_family  product line                e.g. PromethION
          └─ instrument_model  specific instrument      e.g. PromethION 24
chemistry              pore / chemistry version         e.g. R10.4.1
read_mode              acquisition mode                 e.g. simplex, duplex, HiFi, CLR
basecaller             primary-analysis software        e.g. Dorado
library strategy       INSDC library_strategy           e.g. WGS
assay                  Atlas assay class                e.g. germline WGS
```

**NovaSeq, Revio and PromethION are instrument families, not technology
families.** A vendor is not a technology family either. Pacific Biosciences
sells SMRT instruments (Sequel, Revio, Vega) and a sequencing-by-binding
short-read instrument (Onso), and the taxonomy records both.

## Seed technology families

| id | Principle | Evidence scope |
|---|---|---|
| `short_read_sbs` | Short-read sequencing by synthesis, reversible terminator (Illumina) | RELEASED_IN_V1 |
| `nanopore` | Nanopore single-molecule (ONT) | RELEASED_IN_V1 |
| `smrt` | Single-molecule real-time (PacBio Sequel/Revio/Vega) | EXPANSION_TARGET |
| `short_read_sbb` | Sequencing by binding (PacBio Onso) | CATALOG_ONLY |
| `short_read_avidity` | Avidity sequencing (Element AVITI) | CATALOG_ONLY |
| `short_read_dnb` | DNA nanoball / cPAS (DNBSEQ) | CATALOG_ONLY |
| `short_read_flow_sbs` | Flow-based, mostly-natural SBS (Ultima) | CATALOG_ONLY |
| `semiconductor` | Ion-sensing (Ion Torrent) | CATALOG_ONLY |
| `pyrosequencing` | 454 (legacy) | CATALOG_ONLY |
| `capillary_electrophoresis` | Sanger | CATALOG_ONLY |

`evidence_scope` says how far that family is planned to go. It is a roadmap
statement, not an eligibility decision. `CATALOG_ONLY` families can be
recognised and catalogued, but no frozen evidence protocol exists for them
yet, so E11 fails for them.

### Why "HiFi" is a read mode, not a family

The brief suggested `pacbio_hifi` as a technology family. M0 instead uses the
`smrt` family with read modes `smrt_hifi` and `smrt_clr`. The reason is that
the same SMRT instruments (e.g. Sequel II) produced both HiFi and CLR data,
and the two have very different error profiles. Making HiFi a family would
either misfile CLR runs or force a guess. Treating HiFi as a read mode keeps
both representable and lets an evidence protocol admit HiFi only. This is
recorded as unresolved decision U10 for mapping to the v1 `PACBIO_HIFI` enum.

## Normalization rules

1. Technology family is derived from the instrument family or model, never
   from the vendor alone when that vendor operates several families. The
   INSDC term `PACBIO_SMRT` therefore maps to vendor `pacbio` with
   `technology_family_id: null`, and the instrument decides the family.
2. **A family-only source string never yields a model.** `"PromethION"`
   becomes family `ont_promethion`, model `UNSPECIFIED`. It is never
   `PromethION 24`. Family-level aliases are kept separate from model aliases,
   and tests enforce that they never collide.
3. Every alias (model labels, source aliases, family-level aliases) resolves
   to exactly one node, case-insensitively.
4. Chemistry and basecaller entries must pair a vendor with a technology
   family that vendor actually sells.
5. v1's source strings stay as recorded. For example, v1 records
   `"PromethION R9.4"`. R9.4 and R9.4.1 are distinct seed chemistries, and a
   string that does not distinguish them stays unresolved instead of being
   guessed.

## Seed instruments (non-exhaustive)

| Vendor | Instrument family → models |
|---|---|
| Illumina | HiSeq → 2000, 2500, 4000, X · MiSeq · NextSeq → 500, 550, 1000, 2000 · NovaSeq → 6000, X, X Plus · iSeq → 100 |
| Oxford Nanopore | MinION → Mk1B, Mk1C · GridION → Mk1 · PromethION → 24, 48, 2 Solo |
| Pacific Biosciences | PacBio RS → RS II · Sequel → Sequel, II, IIe · Revio · Vega · Onso (`short_read_sbb`) |
| Element Biosciences | AVITI |
| MGI / Complete Genomics | DNBSEQ → G400, T7 |
| Ultima Genomics | UG → UG 100 |
| Thermo Fisher (Ion Torrent) | Ion Torrent → PGM, Proton, GeneStudio S5 |

The `source_aliases` lists are **seed** forms. M1/M2 must check them against
the live INSDC instrument vocabulary before relying on them. Values are only
added when a source or vendor documentation supports them. None are invented
to fill the hierarchy.

## Extending the taxonomy

1. Add the node with all required fields, and cite the supporting source in
   the pull request.
2. Run `pytest tests/atlas`. The integrity checks reject dangling references,
   alias collisions and level conflation.
3. Bump `taxonomy_version`. Release manifests record the taxonomy version
   they used.
