# DuckDB query contract

`event_evidence.sql` defines the Phase 1A retrieval shape after the six Parquet
entities are loaded as DuckDB tables/views with plural lowercase names. It is a
contract only; no scientific database exists during bootstrap.

The query accepts a run-scoped `event_id`. Candidate searches by coordinate or
normalized allele are deliberately separate and must not merge event IDs.

