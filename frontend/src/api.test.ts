import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiContractError, createApiClient } from './api'

const response = (payload: unknown, status = 200): Response =>
  ({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? 'Not Found' : 'OK',
    json: async () => payload,
  }) as Response

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
            primary_model: 'small-strict-pit', warnings: [],
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
          return response({ scores: [{ rank: 1, code: '000001.SZ', name: '平安银行', score: 0.04, forecast_return: 0.04, coverage: 1, input_completeness: 1, eligible: true, model_spread: 0.01, previous_rank: null, rank_delta: null, selected_top3: true, paper_decision: 'ORDER_FROZEN', paper_reason: 'frozen', model_scores: { 'small-strict-pit': 0.04 }, forecast: [] }] })
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
      symbol: '000001.SZ', selected_top3: true, paper_decision: 'ORDER_FROZEN',
    })
    expect(snapshot.research_catalog[0]?.evaluations.validation_2025?.rows).toBe(18_000)
    expect(snapshot.research_catalog_available).toBe(true)
    expect(snapshot.paper_summary?.latest_publication?.source_run_id).toBe('run-1')
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
})
