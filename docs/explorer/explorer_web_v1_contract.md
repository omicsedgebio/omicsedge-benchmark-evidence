# OmicsEdge Benchmark Evidence Explorer
## Web Delivery v1 Contract

Status: FROZEN_BEFORE_IMPLEMENTATION

Scientific source:
Project 003 Evidence Explorer v1 canonical export

Canonical implementation commit:
77d9293d50ce79b83c585f0b5ba56a596ac71bef

Scientific release:
v1.0.0

Zenodo DOI:
10.5281/zenodo.23085673

## Purpose

This layer converts the validated canonical Explorer export into static,
browser-friendly files for omicsedge.bio.

It is a delivery transformation only.

It must not:

- recompute benchmark outcomes;
- infer biological identity;
- merge EVENT records;
- change identity states;
- generate consensus;
- generate reliability or trust scores;
- rank technologies or callers;
- add clinical interpretation;
- rewrite provenance.

The canonical Explorer export remains scientifically authoritative.

## Canonical inputs

The web bundle may read only:

results/explorer_v1/explorer_manifest.json
results/explorer_v1/variants.json
results/explorer_v1/events.json
results/explorer_v1/evidence.json
results/explorer_v1/unresolved_events.json
results/explorer_v1/checksums.sha256

The input checksum manifest must validate before web outputs are generated.

## Delivery model

The browser must not download the complete canonical evidence.json.

The web bundle will contain:

results/explorer_web_v1/manifest.json
results/explorer_web_v1/search_index.json
results/explorer_web_v1/shard_index.json
results/explorer_web_v1/evidence/
results/explorer_web_v1/checksums.sha256

## Search index

search_index.json must contain sufficient information to perform browser-side
discovery without loading observation-level evidence.

Each record represents one run-scoped EVENT.

It may expose only fields derived directly from the canonical Explorer export,
including:

- event_id
- variant_id
- identity_state
- phase_origin
- assembly
- contig
- start_0based
- end_0based
- sample_id
- technology
- raw_decisions
- raw_variant_types
- observation_count
- evidence_shard

For resolved events, normalized biological variant coordinates and alleles may
also be copied from the canonical variant record:

- normalized_start_0based
- normalized_end_0based
- normalized_ref
- normalized_alt

No new identity inference is permitted.

## Search behavior

The web UI must be able to discover evidence by:

- exact variant_id
- exact event_id
- chromosome
- chromosome + position
- chromosome + position + REF + ALT where biological identity exists
- sample
- technology
- identity state
- raw comparator decision
- raw variant type

Search results are evidence retrieval results, not ranking results.

No search result may be ordered by a hidden trust, confidence, reliability,
technology, or caller score.

## Evidence shards

Observation-level canonical evidence must be split into deterministic static
JSON shards.

Sharding must be based only on stable identifiers.

Use the first two hexadecimal characters of a SHA-256 digest derived from the
EVENT identifier as the shard key.

This creates at most 256 evidence shards:

00 through ff.

All observations for one EVENT must remain in the same shard.

Shard assignment must not depend on:

- benchmark outcome;
- sample;
- technology;
- caller;
- truth/query side;
- variant type.

This prevents the delivery partition from encoding a scientific preference.

Each shard contains complete canonical evidence records for its assigned
EVENTs.

Records inside each shard must have deterministic ordering.

## Shard index

shard_index.json maps each EVENT identifier to exactly one shard path.

Every EVENT in search_index.json must have exactly one shard assignment.

No EVENT may appear in more than one shard.

## Manifest

manifest.json must contain:

- web_bundle_schema_version
- canonical_explorer_schema_version
- canonical Explorer manifest SHA-256
- canonical input file SHA-256 values
- scientific release
- Zenodo DOI
- event count
- observation count
- variant count
- identity-state counts
- shard count
- maximum shard byte size
- search index SHA-256
- shard index SHA-256
- scientific-boundary flags

## Scientific-state preservation

The web bundle must preserve exactly:

EXACT_NORMALIZED_ALLELE
UNRESOLVED
NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY

UNRESOLVED events must retain null variant_id.

NOT_EVALUATED_FOR_CROSS_RUN_IDENTITY events must not be relabeled UNRESOLVED.

## Genomic context

The web bundle must not generate per-variant genomic-context labels.

The canonical Explorer intentionally does not expose such labels because
window context is not automatically equivalent to per-base variant context.

## Coordinates

Registry coordinates:

GRCh38
0-based half-open

Source VCF positions remain 1-based where displayed from evidence records.

The website must label these conventions.

## Determinism

Two independent builds from the same canonical Explorer v1 export must be
byte-identical.

JSON output requirements:

- UTF-8
- deterministic key ordering
- deterministic record ordering
- compact separators
- exactly one trailing newline
- no generated timestamps in content

## File-size requirement

No generated individual web-delivery JSON file may exceed 20 MiB.

The implementation should normally produce evidence shards far below this
limit.

If any shard exceeds 20 MiB, the build must fail rather than silently produce
an unsuitable website artifact.

## Validation

The implementation must prove:

1. canonical Explorer checksum manifest validates;
2. canonical manifest reports 11,553 events;
3. canonical manifest reports 23,106 observations;
4. search_index contains exactly 11,553 EVENT records;
5. every canonical EVENT occurs exactly once in search_index;
6. every EVENT has exactly one shard assignment;
7. every canonical observation occurs exactly once across all evidence shards;
8. total sharded observations equal 23,106;
9. all observations for one EVENT are in one shard;
10. unresolved events preserve null variant_id;
11. identity-state counts remain unchanged;
12. sample values remain HG002/HG003/HG004;
13. technology values remain ILLUMINA/ONT;
14. raw decisions are preserved;
15. raw variant types are preserved;
16. no forbidden scoring/ranking/consensus fields are generated;
17. no per-variant genomic-context field is generated;
18. no output JSON file exceeds 20 MiB;
19. all generated checksums validate;
20. two independent builds are byte-identical.

## Forbidden fields

The web bundle must not generate:

- reliability_score
- trust_score
- confidence_score
- consensus
- consensus_decision
- trusted
- technology_winner
- caller_winner
- preferred_technology
- pathogenicity
- clinical_significance

## Website integration

omicsedge.bio will consume this web bundle as static data.

The website may:

- filter;
- search;
- display;
- group observations visually;
- expose provenance.

The website must not independently derive scientific identity or benchmark
interpretation.

Scientific logic remains in the Project 003 repository.
