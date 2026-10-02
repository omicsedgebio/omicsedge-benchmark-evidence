# Evidence Atlas expansion schemas

JSON Schema draft 2020-12, schema family `atlas-0.1.0`. These schemas sit
beside the frozen v1 registry schemas in `schemas/` (version `1.0.0`) and do
not replace them.

- `0.1.0/*.schema.json`: entity schemas (organism, reference assembly,
  reference sequence set, study, sample, sequencing run, source record,
  publication, truth source, derived artifact, provenance activity, catalog
  record, eligibility assessment, release manifest) and
  `common.defs.schema.json`.
- `0.1.0/config/*.config.schema.json`: schemas for `config/atlas/*.json`.

Design and rationale: [`docs/atlas/entity_model.md`](../../docs/atlas/entity_model.md).

A schema change creates a new version directory with migration notes. A
frozen version directory is never edited.
