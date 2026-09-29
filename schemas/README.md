# Registry schemas

These JSON Schemas use draft 2020-12 and version `1.0.0` for the Phase 1A
conceptual contract:

- `event.schema.json`
- `experiment.schema.json`
- `benchmark_run.schema.json`
- `observation.schema.json`
- `source_artifact.schema.json`
- `provenance_link.schema.json`

An event is run-scoped. A provenance link is lineage only and cannot be used to
assert cross-run biological equivalence. Schema changes require a version bump
and migration notes before scientific records are generated.

