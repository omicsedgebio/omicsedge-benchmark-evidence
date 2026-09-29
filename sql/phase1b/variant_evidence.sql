SELECT
    v.variant_id,
    v.assembly,
    v.contig,
    v.normalized_start_0based,
    v.normalized_end_0based,
    v.normalized_ref,
    v.normalized_alt,

    evl.event_variant_link_id,
    evl.identity_status,
    evl.identity_method,
    evl.identity_method_version,
    evl.provenance AS phase1b_identity_provenance,

    e.event_id,
    e.identity_scope AS event_identity_scope,

    br.benchmark_run_id,
    br.observation_origin,
    br.comparator,
    br.comparator_version,
    br.engine,
    br.engine_version,
    br.truth_artifact_id,
    br.benchmark_bed_artifact_id,
    br.reference_artifact_id,

    ex.experiment_id,
    ex.source_corpus,
    ex.source_submission_id,
    ex.sample_id,
    ex.technology,
    ex.platform,
    ex.coverage,
    ex.pipeline_name,
    ex.pipeline_version,
    ex.caller_names,
    ex.caller_versions,

    o.observation_id,
    o.side,
    o.raw_decision,
    o.normalized_decision,
    o.raw_match_kind,
    o.raw_variant_type,
    o.raw_location_type,
    o.source_contig,
    o.source_pos_1based,
    o.source_ref,
    o.source_alt,
    o.source_genotype,
    o.source_filter,
    o.source_output_artifact_id,
    o.source_record_ordinal,
    o.normalization_method AS observation_normalization_method,
    o.normalization_version AS observation_normalization_version

FROM variants AS v

JOIN event_variant_links AS evl
    ON evl.variant_id = v.variant_id

JOIN phase1a_events AS e
    ON e.event_id = evl.event_id

JOIN phase1a_observations AS o
    ON o.event_id = e.event_id
   AND o.benchmark_run_id = e.benchmark_run_id

JOIN benchmark_runs AS br
    ON br.benchmark_run_id = e.benchmark_run_id

JOIN experiments AS ex
    ON ex.experiment_id = br.experiment_id

WHERE v.variant_id = ?

ORDER BY
    ex.technology,
    br.benchmark_run_id,
    e.event_id,
    o.side,
    o.source_record_ordinal;
