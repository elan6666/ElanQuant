import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiContractError, createApiClient } from './api'
import {
  finalTestHistoricalBacktest,
  finalTestHistoricalTop3Backtest,
  historicalBacktest,
  historicalTop3Backtest,
} from './test/fixtures'

const response = (payload: unknown, status = 200): Response =>
  ({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? 'Not Found' : 'OK',
    json: async () => payload,
  }) as Response

const stubHistoricalCatalog = (backtests: unknown[]) => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/system/status')) {
        return response({
          service_state: 'ready',
          server_time: '2026-08-13T20:00:00+08:00',
          latest_closed_session: null,
          data_as_of: null,
          inference_as_of: null,
          active_job_id: null,
          primary_model: null,
          warnings: [],
        })
      }
      if (path.endsWith('/jobs')) return response({ jobs: [] })
      if (path.includes('/runs?')) return response({ runs: [] })
      if (path.endsWith('/research/experiments')) return response({ experiments: [] })
      if (path.endsWith('/research/backtests')) return response({ available: true, backtests })
      if (path.includes('/research/backtests/') && path.includes('/series?signal=mean')) {
        return response({ signal: 'mean', points: [] })
      }
      return response({}, 404)
    }),
  )
}

describe('API runtime contract', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('rejects missing core fields instead of fabricating a production success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/system/status')) {
          return response({ inference_as_of: null, active_job_id: null })
        }
        if (path.endsWith('/jobs')) return response({ items: [] })
        if (path.includes('/runs?')) return response({ runs: [] })
        if (path.endsWith('/research/experiments')) return response({ experiments: [] })
        return response({}, 404)
      }),
    )

    await expect(createApiClient().getSnapshot()).rejects.toBeInstanceOf(ApiContractError)
  })

  it('decodes backend DATA_INCOMPLETE jobs into the validation stage', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/system/status')) {
          return response({
            service_state: 'degraded',
            server_time: '2026-08-13T02:00:00+08:00',
            latest_closed_session: '2026-08-12',
            data_as_of: null,
            inference_as_of: null,
            active_job_id: null,
            warnings: ['data incomplete'],
          })
        }
        if (path.endsWith('/jobs')) {
          return response({
            items: [
              {
                id: 'job-1',
                status: 'DATA_INCOMPLETE',
                stage: 'DATA_INCOMPLETE',
                created_at: '2026-08-13T02:00:00+08:00',
                requested_session: '2026-08-12',
                error_code: 'DATA_INCOMPLETE',
              },
            ],
          })
        }
        if (path.includes('/runs?')) return response({ runs: [] })
        if (path.endsWith('/research/experiments')) return response({ experiments: [] })
        return response({}, 404)
      }),
    )

    const snapshot = await createApiClient().getSnapshot()
    expect(snapshot.jobs[0]).toMatchObject({
      state: 'data_incomplete',
      stage: 'validating_data',
      error_code: 'DATA_INCOMPLETE',
    })
  })

  it('decodes the live evidence-chain envelopes without adapter drift', async () => {
    const evaluation = {
      rank_ic: 0.01,
      pearson_ic: 0.02,
      top10_mean_return: 0.03,
      rows: 18_000,
      cross_sections: 60,
      anchor_set_sha256: 'a'.repeat(64),
    }
    const experiment = {
      id: 'small-zero-shot',
      model_size: 'small',
      track: 'zero_shot',
      state: 'passed',
      rank_ic: 0.01,
      pearson_ic: 0.02,
      top10_mean_return: 0.03,
      model_hash: 'b'.repeat(64),
      receipt: 'c'.repeat(64),
      note: 'baseline',
      evaluations: { validation_2025: evaluation },
    }
    const run = {
      id: 'run-1',
      as_of: '2026-08-12',
      status: 'success',
      created_at: '2026-08-12T16:30:00+08:00',
      model_id: 'small-strict-pit',
      protocol: 'STRICT_PIT_SMALL',
      model_versions: ['small-strict-pit@123456789abc'],
      scoreable: false,
      viewed_test: true,
      provenance: {
        data_hash: 'd'.repeat(64),
        model_hash: 'e'.repeat(64),
        tokenizer_hash: 'f'.repeat(64),
        config_hash: '1'.repeat(64),
        code_hash: '2'.repeat(64),
      },
      warnings: [],
      paper_publication: { state: 'FROZEN', source_run_id: 'run-1' },
      data_health: {
        status: 'PASS',
        resolved_session: '2026-08-12',
        eligible_symbols: 300,
        membership_count: 300,
        excluded_counts: {},
      },
      experiment_matrix: [experiment],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/system/status')) {
          return response({
            service_state: 'ready', server_time: '2026-08-12T16:30:00+08:00',
            latest_closed_session: '2026-08-12', data_as_of: '2026-08-12',
            inference_as_of: '2026-08-12', active_job_id: null,
            primary_model: 'small-strict-pit', execution_profile: 'remote-linux-nvidia', warnings: [],
          })
        }
        if (path.endsWith('/jobs')) return response({ jobs: [] })
        if (path.endsWith('/runs/latest')) return response(run)
        if (path.includes('/runs?limit=')) {
          return response({ runs: [{ id: 'run-1', as_of_session: '2026-08-12', created_at: run.created_at, protocol: run.protocol, paper_publication_state: 'FROZEN', paper_publication_run_id: 'run-1' }] })
        }
        if (path.endsWith('/research/experiments')) return response({ experiments: [experiment] })
        if (path.endsWith('/paper/account')) {
          return response({ as_of: '2026-08-12', initial_cash: 100_000, cash: 100_000, market_value: 0, equity: 100_000, valuation_policy: 'REAL_CLOSE_OR_BOOK_COST', positions: [], gaps: [] })
        }
        if (path.endsWith('/runs/run-1/scores')) {
          return response({ scores: [{ rank: 1, code: '000001.SZ', name: '平安银行', score: 0.04, forecast_return: 0.04, reference_price: 10, coverage: 1, input_completeness: 1, eligible: true, model_spread: 0.01, previous_rank: null, rank_delta: null, selected_top3: true, paper_decision: 'ORDER_FROZEN', paper_reason: 'frozen', model_scores: { 'small-strict-pit': 0.04 }, forecast: [] }] })
        }
        if (path.endsWith('/runs/run-1/diff')) return response({ run_id: 'run-1', against_run_id: null, comparable: false })
        if (path.endsWith('/paper/orders')) return response({ orders: [] })
        if (path.endsWith('/paper/nav')) return response({ nav: [{ session: '2026-08-12', nav: 1, benchmark_nav: null }] })
        if (path.endsWith('/paper/summary')) {
          return response({ sample_sessions: 1, evidence_state: 'insufficient_evidence', order_counts: { pending: 0, filled: 0, rejected: 0 }, decision_counts: {}, total_fees: 0, gross_turnover: 0, max_drawdown: null, latest_publication: { run_id: 'run-1', signal_session: '2026-08-12', state: 'FROZEN', source_run_id: 'run-1' }, latest_decisions: [], warnings: [] })
        }
        return response({}, 404)
      }),
    )

    const snapshot = await createApiClient().getSnapshot()
    expect(snapshot.latest_run?.scores[0]).toMatchObject({
      symbol: '000001.SZ', reference_price: 10, selected_top3: true, paper_decision: 'ORDER_FROZEN',
    })
    expect(snapshot.system).toMatchObject({
      active_execution_profile: 'remote-linux-nvidia',
      default_execution_location: 'remote',
      execution_profiles: {
        local: { available: false, profile_id: null },
        remote: { available: true, profile_id: 'remote-linux-nvidia' },
      },
    })
    expect(snapshot.research_catalog[0]?.evaluations.validation_2025?.rows).toBe(18_000)
    expect(snapshot.research_catalog_available).toBe(true)
    expect(snapshot.paper_summary?.latest_publication?.source_run_id).toBe('run-1')
  })

  it('submits an additive execution profile and verifies the returned identity', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void input
      void init
      return response({
        created: true,
        job: { id: 'job-local', execution_profile: 'local-apple-silicon' },
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const receipt = await createApiClient().submitUpdateInfer('local-apple-silicon')

    expect(receipt).toEqual({
      job_id: 'job-local',
      coalesced: false,
      execution_profile: 'local-apple-silicon',
    })
    expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
      force: false,
      execution_profile: 'local-apple-silicon',
    })
  })

  it('keeps the control plane usable when the optional research catalog is unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/system/status')) {
          return response({
            service_state: 'ready', server_time: '2026-08-12T16:30:00+08:00',
            latest_closed_session: null, data_as_of: null, inference_as_of: null,
            active_job_id: null, primary_model: null, warnings: [],
          })
        }
        if (path.endsWith('/jobs')) return response({ jobs: [] })
        if (path.includes('/runs?')) return response({ runs: [] })
        if (path.endsWith('/research/experiments')) {
          return response({ detail: 'Research catalog failed its receipt gate' }, 503)
        }
        return response({}, 404)
      }),
    )

    const snapshot = await createApiClient().getSnapshot()
    expect(snapshot.research_catalog).toEqual([])
    expect(snapshot.research_catalog_available).toBe(false)
    expect(snapshot.system.service_state).toBe('ready')
  })

  it('decodes the sealed official-demo backtest as a separate read-only track', async () => {
    const legacyBacktest: Record<string, unknown> = { ...historicalBacktest }
    delete legacyBacktest.strategy_variant_id
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const path = String(input)
        if (path.endsWith('/system/status')) {
          return response({
            service_state: 'ready',
            server_time: '2026-08-13T15:00:00+08:00',
            latest_closed_session: null,
            data_as_of: null,
            inference_as_of: null,
            active_job_id: null,
            primary_model: null,
            warnings: [],
          })
        }
        if (path.endsWith('/jobs')) return response({ jobs: [] })
        if (path.includes('/runs?')) return response({ runs: [] })
        if (path.endsWith('/research/experiments')) return response({ experiments: [] })
        if (path.endsWith('/research/backtests')) {
          return response({ available: true, backtests: [legacyBacktest] })
        }
        if (path.includes('/research/backtests/') && path.includes('/series?signal=mean')) {
          return response({
            signal: 'mean',
            points: [
              {
                session: '2025-01-02',
                strategy: 0.01,
                benchmark: 0.005,
                excess: 0.005,
                strategy_nav: 1.01,
                benchmark_nav: 1.005,
              },
            ],
          })
        }
        return response({}, 404)
      }),
    )

    const snapshot = await createApiClient().getSnapshot()
    expect(snapshot.historical_backtest_available).toBe(true)
    expect(snapshot.historical_backtests[0]?.strategy).toMatchObject({ topk: 50, n_drop: 5, hold_thresh: 5 })
    expect(snapshot.historical_backtest_series[historicalBacktest.id]?.[0]?.strategy).toBe(0.01)
    expect(snapshot.paper).toBeNull()
  })

  it('accepts only the complete frozen split-by-strategy matrix for the new contract', async () => {
    const matrix = [
      historicalBacktest,
      historicalTop3Backtest,
      finalTestHistoricalBacktest,
      finalTestHistoricalTop3Backtest,
    ]
    stubHistoricalCatalog(matrix)

    const snapshot = await createApiClient().getSnapshot()
    expect(snapshot.historical_backtests).toHaveLength(4)
    expect(
      snapshot.historical_backtests.map(
        (entry) => `${entry.evaluation_split}:${entry.strategy_variant_id}`,
      ),
    ).toEqual([
      'validation_2025:official_top50',
      'validation_2025:historical_top3',
      'test_viewed_2026:official_top50',
      'test_viewed_2026:historical_top3',
    ])
  })

  it('accepts the exact six-model by split by strategy matrix', async () => {
    const models = [
      'small-zero-shot',
      'small-official-ft',
      'small-strict-pit',
      'base-zero-shot',
      'base-official-ft',
      'base-strict-pit',
    ] as const
    const splitPairs = [
      [historicalBacktest, historicalTop3Backtest],
      [finalTestHistoricalBacktest, finalTestHistoricalTop3Backtest],
    ] as const
    const matrix = models.flatMap((model) =>
      splitPairs.flatMap(([top50, top3]) => {
        const top50Id = `historical-${model}-${top50.evaluation_split}-official_top50-v1`
        return [
          {
            ...top50,
            id: top50Id,
            track_kind: 'HISTORICAL_MODEL_MATRIX',
            model_cell_id: model,
            comparison_group_id: 'six-model-top50-top3-v1',
            result_role:
              top50.evaluation_split === 'test_viewed_2026'
                ? 'POST_HOC_OPENED_MODEL_STRATEGY_DIAGNOSTIC'
                : 'POST_HOC_MODEL_STRATEGY_COMPARISON',
            selection_eligible: false,
            used_for_selection: false,
          },
          {
            ...top3,
            id: `historical-${model}-${top3.evaluation_split}-historical_top3-v1`,
            track_kind: 'HISTORICAL_MODEL_MATRIX',
            model_cell_id: model,
            comparison_group_id: 'six-model-top50-top3-v1',
            source_backtest_id: top50Id,
            result_role:
              top3.evaluation_split === 'test_viewed_2026'
                ? 'POST_HOC_OPENED_MODEL_STRATEGY_DIAGNOSTIC'
                : 'POST_HOC_MODEL_STRATEGY_COMPARISON',
          },
        ]
      }),
    )
    stubHistoricalCatalog(matrix)

    const snapshot = await createApiClient().getSnapshot()
    expect(snapshot.historical_backtests).toHaveLength(24)
    expect(new Set(snapshot.historical_backtests.map((entry) => entry.model_cell_id)).size).toBe(6)
  })

  it('accepts the exact official-v3 four-model by two-strategy rolling matrix', async () => {
    const models = [
      'small-zero-shot',
      'small-official-ft',
      'base-zero-shot',
      'base-official-ft',
    ] as const
    const matrix = models.flatMap((model) => {
      const top50Id = `official-v3-${model}-official_top50`
      return [
        {
          ...finalTestHistoricalBacktest,
          id: top50Id,
          track_kind: 'OFFICIAL_SPLIT_V3_MODEL_MATRIX',
          model_cell_id: model,
          evaluation_split: 'test_viewed_official_v3',
          comparison_group_id: 'official-split-v3-top50-top3-v1',
          result_role: 'OPENED_ROLLING_TEST_MODEL_STRATEGY_DIAGNOSTIC',
          selection_eligible: false,
          used_for_selection: false,
          source_backtest_id: null,
        },
        {
          ...finalTestHistoricalTop3Backtest,
          id: `official-v3-${model}-historical_top3`,
          track_kind: 'OFFICIAL_SPLIT_V3_MODEL_MATRIX',
          model_cell_id: model,
          evaluation_split: 'test_viewed_official_v3',
          comparison_group_id: 'official-split-v3-top50-top3-v1',
          result_role: 'OPENED_ROLLING_TEST_MODEL_STRATEGY_DIAGNOSTIC',
          selection_eligible: false,
          used_for_selection: false,
          source_backtest_id: top50Id,
        },
      ]
    })
    stubHistoricalCatalog(matrix)

    const snapshot = await createApiClient().getSnapshot()
    expect(snapshot.historical_backtests).toHaveLength(8)
    expect(new Set(snapshot.historical_backtests.map((entry) => entry.model_cell_id))).toEqual(
      new Set(models),
    )
    expect(new Set(snapshot.historical_backtests.map((entry) => entry.evaluation_split))).toEqual(
      new Set(['test_viewed_official_v3']),
    )
  })

  it('rejects a partial new matrix instead of rendering a misleading comparison', async () => {
    stubHistoricalCatalog([
      historicalBacktest,
      historicalTop3Backtest,
      finalTestHistoricalBacktest,
    ])

    await expect(createApiClient().getSnapshot()).rejects.toThrow(ApiContractError)
  })

  it('decodes a sealed holdings session with exact position fields', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      expect(String(input)).toContain(
        '/api/v1/research/backtests/historical-top3-opened-2026-v1/holdings?session=2026-07-29',
      )
      return response({
        backtest_id: 'historical-top3-opened-2026-v1',
        available: true,
        signal: 'mean',
        empty: false,
        sessions: ['2026-07-28', '2026-07-29'],
        default_session: '2026-07-29',
        selected_session: '2026-07-29',
        source: { artifact_sha256: 'a'.repeat(64), receipt_sha256: 'b'.repeat(64), backtest_receipt_sha256: 'c'.repeat(64) },
        holdings: [
          { instrument: 'SH600000', amount: 1_000, weight: 0.4, value: 12_500 },
          { instrument: 'SZ000001', amount: 800, weight: 0.6, value: 18_750 },
        ],
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const holdings = await createApiClient().getHistoricalHoldings(
      'historical-top3-opened-2026-v1',
      '2026-07-29',
    )
    expect(holdings?.holdings).toHaveLength(2)
    expect(holdings?.holdings[0]).toMatchObject({ instrument: 'SH600000', value: 12_500 })
  })

  it('rejects holdings whose empty marker disagrees with the sealed rows', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => response({
        backtest_id: 'historical-top3-opened-2026-v1',
        available: true,
        signal: 'mean',
        empty: true,
        sessions: ['2026-07-29'],
        default_session: '2026-07-29',
        selected_session: '2026-07-29',
        source: { artifact_sha256: 'a'.repeat(64), receipt_sha256: 'b'.repeat(64), backtest_receipt_sha256: 'c'.repeat(64) },
        holdings: [{ instrument: 'SH600000', amount: 1_000, weight: 1, value: 12_500 }],
      })),
    )

    await expect(
      createApiClient().getHistoricalHoldings(
        'historical-top3-opened-2026-v1',
        '2026-07-29',
      ),
    ).rejects.toThrow(ApiContractError)
  })
})
