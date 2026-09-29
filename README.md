# OmicsEdgeBio Project 003 — Benchmark Evidence Registry

Project 003 is an independent, provenance-rich registry of empirical germline
small-variant benchmark observations. It is not part of Project 002/CrossCall
and has no Project 002 dependency.

## Phase 1A

Status: **READY_FOR_COMPUTE_POC**.

The locked proof of concept will regenerate event decisions for two public
precisionFDA Truth Challenge V2 HG002 query callsets against an explicitly
versioned GIAB truth VCF and benchmark BED, normalize the annotated hap.py
output, write Parquet, load DuckDB, and demonstrate a provenance-preserving
event query.

This bootstrap contains plans, contracts, manifests, and synthetic-only tests.
It contains no genomic data, no comparison output, and no scientific evidence
records. No hap.py/vcfeval comparison has been run.

Start with:

- [Scientific scope](docs/scientific_scope.md)
- [Evidence semantics](docs/evidence_semantics.md)
- [Conceptual schema](docs/conceptual_schema.md)
- [Compute and Colab plan](docs/phase1a_compute_plan.md)
- [Locked validation criteria](docs/phase1a_validation.md)
- [Unresolved scientific risks](docs/scientific_risks.md)
- [Phase 1A status](docs/phase1a_status.md)

Run the synthetic contract tests after installing the development dependency:

```bash
python -m pip install -e '.[dev]'
pytest
```
