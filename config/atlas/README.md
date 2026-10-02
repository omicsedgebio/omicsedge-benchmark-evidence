# Evidence Atlas controlled configuration

| File | Content | Doc |
|---|---|---|
| `technology_taxonomy.json` | technology family → vendor → instrument family → model; chemistry, read mode, basecaller, INSDC platform terms | [technology_taxonomy.md](../../docs/atlas/technology_taxonomy.md) |
| `organisms_assemblies.json` | seed organisms (NCBI Taxonomy IDs), assemblies, reference sequence sets | [organism_assembly_model.md](../../docs/atlas/organism_assembly_model.md) |
| `sources.json` | sources, mirror groups, deduplication and terms review | [source_strategy.md](../../docs/atlas/source_strategy.md) |
| `eligibility_policy.json` | layers, states, transitions, criteria E01–E13 | [evidence_eligibility_policy.md](../../docs/atlas/evidence_eligibility_policy.md) |
| `ml_policy.json` | allowed tasks, prohibited decisions, thresholds, deployment gates | [ml_policy.md](../../docs/atlas/ml_policy.md) |

`provenance/` holds the metadata-only lookup record
(`assembly_verification.json`) and raw response snapshots that back every
identifier in `organisms_assemblies.json`. Regenerate it with
`python scripts/atlas/verify_seed_assemblies.py`.

Each file is validated against `schemas/atlas/0.1.0/config/` and against the
integrity checks in `src/evidence_atlas/protocol.py`. Run `pytest tests/atlas`
after any edit, and bump the file's version field.
