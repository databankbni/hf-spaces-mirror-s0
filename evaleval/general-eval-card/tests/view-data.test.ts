import { mkdir, mkdtemp, rm, writeFile } from "fs/promises"
import os from "os"
import path from "path"

import { DuckDBConnection } from "@duckdb/node-api"
import { describe, expect, it } from "vitest"

function sqlString(value: string) {
  return `'${value.replace(/'/g, "''")}'`
}

async function copyParquet(connection: DuckDBConnection, sql: string, outputPath: string) {
  await connection.run(`COPY (${sql}) TO ${sqlString(outputPath)} (FORMAT parquet)`)
}

async function writeSyntheticStageJSnapshot(snapshotDir: string) {
  await mkdir(snapshotDir, { recursive: true })
  const connection = await DuckDBConnection.create()

  await copyParquet(
    connection,
    `
      SELECT
        TIMESTAMP '2026-05-03 00:00:00' AS snapshot_id,
        'openai/gpt-5' AS model_key,
        'openai/gpt-5' AS model_id,
        'openai/gpt-5' AS id,
        'openai%2Fgpt-5' AS route_id,
        'openai%2Fgpt-5' AS model_route_id,
        'openai/gpt-5' AS model_group_id,
        'GPT 5' AS model_name,
        'GPT 5' AS canonical_model_name,
        'GPT 5' AS model_family_name,
        'OpenAI' AS developer,
        DATE '2026-01-01' AS release_date,
        'https://example.test/model' AS model_url,
        'transformer' AS architecture,
        '100B' AS params,
        100.0 AS params_billions,
        ['text']::VARCHAR[] AS input_modalities,
        ['text']::VARCHAR[] AS output_modalities,
        'engine' AS inference_engine,
        'platform' AS inference_platform,
        1::BIGINT AS evaluations_count,
        1::BIGINT AS benchmarks_count,
        1::INTEGER AS variant_count,
        1::BIGINT AS evaluator_count,
        ['OpenAI']::VARCHAR[] AS evaluator_names,
        ['OpenAI']::VARCHAR[] AS verified_evaluator_names,
        1::INTEGER AS source_type_count,
        ['documentation']::VARCHAR[] AS source_types,
        0::BIGINT AS third_party_eval_count,
        0.0 AS independent_verification_ratio,
        1::BIGINT AS evidence_count,
        0::INTEGER AS missing_generation_config_count,
        TIMESTAMP '2026-05-03 00:00:00' AS latest_timestamp,
        'OpenAI' AS latest_source_name,
        ['MMLU']::VARCHAR[] AS benchmark_names,
        ['applied_reasoning']::VARCHAR[] AS derived_tags,
        '{"applied_reasoning":1}'::JSON AS tag_stats,
        'complete' AS reproducibility_status,
        struct_pack(results_total := 1, has_reproducibility_gap_count := 0, populated_ratio_avg := 1.0) AS reproducibility_summary,
        struct_pack(
          total_results := 1,
          total_groups := 1,
          multi_source_groups := 0,
          first_party_only_groups := 1,
          source_type_distribution := struct_pack(first_party := 1, third_party := 0, collaborative := 0, unspecified := 0)
        ) AS provenance_summary,
        struct_pack(
          total_groups := 1,
          groups_with_variant_check := 0,
          groups_with_cross_party_check := 0,
          variant_divergent_count := 0,
          cross_party_divergent_count := 0
        ) AS comparability_summary,
        [struct_pack(name := 'openai-evals', version := '1.0', fork := NULL::VARCHAR)] AS eval_libraries,
        struct_pack(count := 1, min := 0.8, max := 0.8, average := 0.8) AS score_summary,
        [struct_pack(benchmark := 'MMLU', benchmarkKey := 'mmlu', score := 0.8, metric := 'accuracy')] AS top_scores,
        ['https://example.test/source']::VARCHAR[] AS source_urls,
        []::VARCHAR[] AS detail_urls,
        [struct_pack(
          variant_id := 'default',
          variant_key := 'default',
          variant_label := 'Default',
          variant_display_name := 'GPT 5',
          raw_model_ids := ['openai/gpt-5']::VARCHAR[],
          family_id := 'openai/gpt-5',
          family_name := 'GPT 5',
          version_date := NULL::VARCHAR,
          version_qualifier := NULL::VARCHAR,
          total_evaluations := 1,
          last_updated := TIMESTAMP '2026-05-03 00:00:00',
          tags_covered := ['applied_reasoning']::VARCHAR[]
        )] AS variants,
        ['openai/gpt-5']::VARCHAR[] AS raw_model_ids
    `,
    path.join(snapshotDir, "models_view.parquet")
  )

  await copyParquet(
    connection,
    `
      SELECT
        TIMESTAMP '2026-05-03 00:00:00' AS snapshot_id,
        'mmlu' AS evaluation_id,
        'mmlu' AS benchmark_id,
        'accuracy' AS primary_metric_id,
        'MMLU' AS evaluation_name,
        'MMLU' AS canonical_display_name,
        'mmlu' AS composite_benchmark_key,
        'MMLU' AS composite_benchmark_name,
        'mmlu' AS composite_slug,
        'MMLU' AS composite_display_name,
        'mmlu' AS family_id,
        'MMLU' AS family_display_name,
        false AS is_slice,
        NULL AS parent_benchmark_id,
        '["applied_reasoning"]' AS derived_tags,
        struct_pack(
          evaluation_description := 'Accuracy on MMLU',
          lower_is_better := false,
          score_type := 'continuous',
          min_score := 0.0,
          max_score := 1.0,
          unit := 'proportion'
        ) AS metric_config,
        1::BIGINT AS models_count,
        ['OpenAI']::VARCHAR[] AS evaluator_names,
        ['OpenAI']::VARCHAR[] AS verified_evaluator_names,
        ['documentation']::VARCHAR[] AS source_types,
        'OpenAI' AS latest_source_name,
        0.0 AS third_party_ratio,
        0::INTEGER AS missing_generation_config_count,
        struct_pack(name := 'GPT 5', score := 0.8) AS best_model,
        struct_pack(name := 'GPT 5', score := 0.8) AS worst_model,
        0.8 AS avg_score,
        0.8 AS avg_score_norm,
        0.8 AS top_score,
        false AS has_card,
        NULL AS benchmark_card,
        false AS is_aggregated,
        [] AS aggregate_sources,
        false AS is_summary_score,
        []::VARCHAR[] AS constituent_evaluation_ids,
        struct_pack(domains := ['knowledge']::VARCHAR[], languages := ['en']::VARCHAR[], tasks := ['qa']::VARCHAR[]) AS tags,
        struct_pack(
          dataset_name := 'MMLU',
          source_type := 'documentation',
          hf_repo := NULL::VARCHAR,
          hf_split := NULL::VARCHAR,
          samples_number := 10,
          url := ['https://example.test/mmlu']::VARCHAR[],
          dataset_url := 'https://example.test/mmlu',
          dataset_version := 'v1'
        ) AS source_data,
        struct_pack(results_total := 1, has_reproducibility_gap_count := 0, populated_ratio_avg := 1.0) AS reproducibility_summary,
        struct_pack(
          total_results := 1,
          total_groups := 1,
          multi_source_groups := 0,
          first_party_only_groups := 1,
          source_type_distribution := struct_pack(first_party := 1, third_party := 0, collaborative := 0, unspecified := 0)
        ) AS provenance_summary,
        struct_pack(
          total_groups := 1,
          groups_with_variant_check := 0,
          groups_with_cross_party_check := 0,
          variant_divergent_count := 0,
          cross_party_divergent_count := 0
        ) AS comparability_summary,
        struct_pack(available := false, url_count := 0::BIGINT, sample_urls := []::VARCHAR[], models_with_loaded_instances := 0) AS instance_data,
        1::INTEGER AS metrics_count,
        ['Accuracy']::VARCHAR[] AS metric_names,
        [struct_pack(
          column_key := 'root:accuracy',
          metric_summary_id := 'mmlu%3Aaccuracy',
          metric_id := 'accuracy',
          metric_name := 'accuracy',
          display_name := 'Accuracy',
          canonical_display_name := 'Accuracy',
          lower_is_better := false,
          unit := 'proportion',
          scope := 'root',
          subtask_key := NULL::VARCHAR,
          subtask_name := NULL::VARCHAR
        )] AS leaderboard_metrics,
        [] AS leaderboard_rows,
        [struct_pack(
          metric_summary_id := 'mmlu%3Aaccuracy',
          metric_name := 'accuracy',
          display_name := 'Accuracy',
          canonical_display_name := 'Accuracy',
          metric_key := 'accuracy',
          lower_is_better := false,
          models_count := 1,
          top_score := 0.8,
          unit := 'proportion'
        )] AS root_metrics,
        [] AS subtasks,
        0::INTEGER AS subtasks_count
    `,
    path.join(snapshotDir, "evals_view.parquet")
  )

  await copyParquet(
    connection,
    `
      SELECT
        TIMESTAMP '2026-05-03 00:00:00' AS snapshot_id,
        'mmlu' AS evaluation_id,
        'mmlu%3Aaccuracy' AS metric_summary_id,
        'mmlu' AS benchmark_id,
        'accuracy' AS metric_id,
        'openai/gpt-5' AS model_key,
        'openai/gpt-5' AS model_id,
        'openai%2Fgpt-5' AS model_route_id,
        struct_pack(
          name := 'GPT 5',
          id := 'openai/gpt-5',
          developer := 'OpenAI',
          inference_platform := 'platform',
          inference_engine := 'engine',
          model_version := NULL::VARCHAR,
          architecture := 'transformer',
          parameter_count := '100B',
          release_date := '2026-01-01',
          model_url := 'https://example.test/model',
          modalities := struct_pack(input := ['text']::VARCHAR[], output := ['text']::VARCHAR[])
        ) AS model_info,
        'Accuracy' AS metric_display_name,
        'proportion' AS metric_unit,
        false AS lower_is_better,
        '["applied_reasoning"]' AS derived_tags,
        0.8 AS score,
        struct_pack(
          score := 0.8,
          standard_error := 0.01,
          sample_size := 10,
          confidence_interval := struct_pack(lower := 0.7, upper := 0.9, confidence_level := 0.95)
        ) AS score_details,
        1::INTEGER AS fact_row_count,
        1::INTEGER AS position,
        1::INTEGER AS total,
        1.0 AS percentile,
        TIMESTAMP '2026-05-03 00:00:00' AS evaluation_timestamp,
        struct_pack(
          temperature := 0.2,
          top_p := 0.95,
          max_tokens := 512,
          stop_sequences := ['<END>']::VARCHAR[]
        ) AS generation_config,
        struct_pack(
          source_name := 'OpenAI report',
          source_type := 'documentation',
          source_organization_name := 'OpenAI',
          source_organization_url := 'https://example.test',
          evaluator_relationship := 'first_party',
          source_url := 'https://example.test/report',
          publication_date := DATE '2026-05-03'
        ) AS source_metadata,
        struct_pack(
          dataset_name := 'MMLU',
          source_type := 'documentation',
          hf_repo := NULL::VARCHAR,
          hf_split := NULL::VARCHAR,
          samples_number := 10,
          url := ['https://example.test/mmlu']::VARCHAR[],
          dataset_url := 'https://example.test/mmlu',
          dataset_version := 'v1'
        ) AS source_data,
        'https://example.test/record.json' AS source_record_url,
        'https://example.test/eee-record.json' AS eee_record_url,
        struct_pack(name := 'openai-evals', version := '1.0', fork := NULL::VARCHAR) AS eval_library,
        ['first_party']::VARCHAR[] AS evaluator_relationships,
        true AS has_first_party,
        false AS has_third_party,
        'self' AS coverage_cell,
        ['OpenAI']::VARCHAR[] AS reporting_orgs,
        map(['OpenAI'], [0.8]) AS scores_by_organization,
        false AS is_summary_score,
        NULL::VARCHAR AS summary_score_for,
        [] AS aggregate_components,
        false AS has_reproducibility_gap,
        1.0 AS completeness_score,
        false AS is_multi_source,
        true AS first_party_only,
        false AS has_variant_divergence,
        false AS has_cross_party_divergence,
        NULL AS evalcards_annotations,
        NULL::VARCHAR AS instance_file_path,
        NULL::VARCHAR AS instance_file_format,
        0::INTEGER AS instance_rows,
        true AS is_verified_evaluator
    `,
    path.join(snapshotDir, "eval_results_view.parquet")
  )

  await writeFile(
    path.join(snapshotDir, "manifest.json"),
    JSON.stringify({
      generated_at: "2026-05-03T00:00:00Z",
      config_version: 2,
      skipped_configs: [],
      model_count: 1,
      eval_count: 1,
      metric_eval_count: 1,
      source_config_count: 1,
      skipped_config_count: 0,
      summary_artifacts: {
        corpus_aggregates: "headline.json",
        eval_hierarchy: "hierarchy.json",
      },
    })
  )

  const reproducibilityBlock = {
    total_triples: 1,
    triples_with_reproducibility_gap: 0,
    reproducibility_gap_rate: 0,
    agentic_triples: 0,
    per_field_missingness: {
      temperature: {
        missing_count: 0,
        missing_rate: 0,
        denominator: "all_triples",
        denominator_count: 1,
      },
    },
  }
  const completenessBlock = {
    total_triples: 1,
    completeness_avg: 0.75,
    completeness_min: 0.75,
    completeness_max: 0.75,
  }
  const provenanceBlock = {
    total_triples: 1,
    multi_source_triples: 0,
    first_party_only_triples: 1,
    source_type_distribution: {
      first_party: 1,
      third_party: 0,
      collaborative: 0,
      unspecified: 0,
    },
  }
  const comparabilityBlock = {
    total_triples: 1,
    variant_divergent_count: 0,
    cross_party_divergent_count: 0,
    groups_with_variant_check: 1,
    groups_with_cross_party_check: 0,
  }
  await writeFile(
    path.join(snapshotDir, "headline.json"),
    JSON.stringify({
      generated_at: "2026-05-03T00:00:00Z",
      signal_version: "1.0",
      stratification_dimensions: ["category"],
      reproducibility: {
        overall: reproducibilityBlock,
        by_category: { Reasoning: reproducibilityBlock },
      },
      completeness: {
        overall: completenessBlock,
        by_category: { Reasoning: completenessBlock },
      },
      provenance: {
        overall: provenanceBlock,
        by_category: { Reasoning: provenanceBlock },
      },
      comparability: {
        overall: comparabilityBlock,
        by_category: { Reasoning: comparabilityBlock },
      },
      developers: [
        {
          developer: "OpenAI",
          route_id: "OpenAI",
          model_count: 1,
          benchmark_count: 1,
          evaluation_count: 1,
          popular_evals: [{ benchmark: "MMLU", model_count: 1 }],
        },
      ],
    })
  )

  await writeFile(
    path.join(snapshotDir, "hierarchy.json"),
    JSON.stringify({
      stats: {
        family_count: 1,
        composite_count: 0,
        standalone_benchmark_count: 1,
        single_benchmark_count: 1,
        slice_count: 0,
        metric_count: 1,
        metric_rows_scanned: 1,
      },
      families: [],
    })
  )
}

describe("Stage J view-layer backend", () => {
  it("reads a pinned snapshot through the v2 accessors", async () => {
    const snapshotDir = await mkdtemp(path.join(os.tmpdir(), "eval-card-stage-j-"))
    const previousBackend = process.env.DATA_BACKEND
    const previousSnapshotUrl = process.env.SNAPSHOT_URL

    try {
      await writeSyntheticStageJSnapshot(snapshotDir)
      process.env.DATA_BACKEND = "v2"
      process.env.SNAPSHOT_URL = `file://${snapshotDir}`

      const dataBackend = await import("../lib/data-backend")
      const hfData = await import("../lib/hf-data")

      const [models, evalListData, modelSummary, evalSummary, developers, developerSummary, manifest, hierarchy, aggregates] =
        await Promise.all([
          dataBackend.getModelCardsLite(),
          dataBackend.getEvalListLiteData(),
          dataBackend.getModelSummaryById("openai%2Fgpt-5"),
          dataBackend.getEvalSummaryById("mmlu"),
          dataBackend.getDeveloperList(),
          dataBackend.getDeveloperSummaryById("OpenAI"),
          dataBackend.getBackendManifestData(),
          dataBackend.getEvalHierarchyData(),
          hfData.fetchCorpusAggregates(),
        ])

      expect(models[0]).toMatchObject({
        route_id: "openai%2Fgpt-5",
        model_name: "GPT 5",
        evaluations_count: 1,
      })
      expect(evalListData).toMatchObject({
        totalModels: 1,
        evals: [{ evaluation_id: "mmlu", evaluation_name: "MMLU", models_count: 1 }],
      })
      expect(modelSummary?.evaluations_by_tag.applied_reasoning).toHaveLength(1)
      expect(modelSummary?.evaluations_by_tag.applied_reasoning[0]?.generation_config).toMatchObject({
        temperature: 0.2,
        top_p: 0.95,
        max_tokens: 512,
        stop_sequences: ["<END>"],
      })
      expect(evalSummary?.model_results[0]).toMatchObject({
        model_route_id: "openai%2Fgpt-5",
        score: 0.8,
        result: { metric_summary_id: "mmlu%3Aaccuracy", is_verified_evaluator: true },
      })
      expect(evalSummary?.model_results[0]?.result.generation_config).toMatchObject({
        temperature: 0.2,
        top_p: 0.95,
        max_tokens: 512,
        stop_sequences: ["<END>"],
      })
      expect(developers[0]).toMatchObject({ developer: "OpenAI", route_id: "OpenAI" })
      expect(developerSummary?.models).toHaveLength(1)
      expect(manifest.model_count).toBe(1)
      expect(hierarchy.stats?.metric_rows_scanned).toBe(1)
      expect(aggregates?.completeness.overall).toMatchObject({
        total_triples: 1,
        completeness_avg: 0.75,
      })
      expect(aggregates?.provenance.overall).toMatchObject({
        total_triples: 1,
        first_party_only_triples: 1,
      })
      expect(aggregates?.comparability.overall).toMatchObject({
        groups_with_variant_check: 1,
        variant_divergent_count: 0,
      })
      expect(aggregates?.comparability.by_category.Reasoning).toBeDefined()
    } finally {
      if (previousBackend == null) {
        delete process.env.DATA_BACKEND
      } else {
        process.env.DATA_BACKEND = previousBackend
      }
      if (previousSnapshotUrl == null) {
        delete process.env.SNAPSHOT_URL
      } else {
        process.env.SNAPSHOT_URL = previousSnapshotUrl
      }
      await rm(snapshotDir, { recursive: true, force: true })
    }
  })
})
