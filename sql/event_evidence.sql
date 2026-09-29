-- Phase 1A event-level evidence query contract.
-- Bind $event_id to one run-scoped EVENT identifier.
SELECT
    e.event_id,
    e.identity_scope,
    e.assembly,
    e.contig,
    e.start_0based,
    e.end_0based,
    e.source_event_id,
    o.observation_id,
    o.side,
    o.raw_decision,
    o.normalized_decision,
    o.raw_match_kind,
    o.region_status,
    o.source_contig,
    o.source_pos_1based,
    o.source_ref,
    o.source_alt,
    o.source_genotype,
    o.source_filter,
    r.benchmark_run_id,
    r.observation_origin,
    r.comparator,
    r.comparator_version,
    r.engine,
    r.engine_version,
    r.environment_lock_id,
    r.runtime_image_digest,
    r.query_artifact_id,
    r.truth_artifact_id,
    r.benchmark_bed_artifact_id,
    r.reference_artifact_id,
    x.experiment_id,
    x.source_submission_id,
    x.sample_id,
    x.technology,
    x.platform,
    x.coverage,
    x.pipeline_name,
    x.caller_names,
    x.caller_versions,
    p.provenance_link_id AS raw_record_provenance_link_id,
    a.source_artifact_id AS annotated_output_artifact_id,
    a.uri AS annotated_output_uri,
    a.checksums AS annotated_output_checksums
FROM events AS e
JOIN observations AS o
  ON o.event_id = e.event_id
 AND o.benchmark_run_id = e.benchmark_run_id
JOIN benchmark_runs AS r
  ON r.benchmark_run_id = e.benchmark_run_id
JOIN experiments AS x
  ON x.experiment_id = r.experiment_id
JOIN provenance_links AS p
  ON p.target_entity_type = 'OBSERVATION'
 AND p.target_entity_id = o.observation_id
 AND p.source_entity_type = 'SOURCE_ARTIFACT'
 AND p.relation = 'NORMALIZED_FROM'
JOIN source_artifacts AS a
  ON a.source_artifact_id = p.source_entity_id
WHERE e.event_id = $event_id
ORDER BY o.side, o.source_record_ordinal, o.observation_id;

