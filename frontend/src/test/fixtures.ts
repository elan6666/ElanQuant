import type { DashboardSnapshot, Job, PaperAccount, ResearchRun } from '../types'

export const runningJob: Job = {
  id: 'job-20260812-001',
  kind: 'update_infer',
  state: 'running',
  stage: 'infer_small',
  requested_at: '2026-08-12T15:40:00+08:00',
  started_at: '2026-08-12T15:40:01+08:00',
  finished_at: null,
  as_of: '2026-08-12',
  progress: 0.55,
  message: '正在批量运行Kronos Small。',
  error_code: null,
  retry_of: null,
  coalesced: false,
  events: [],
}

export const incompleteJob: Job = {
  ...runningJob,
  id: 'job-20260812-002',
  state: 'data_incomplete',
  stage: 'validating_data',
  progress: 0.35,
  message: '2026-08-12 的 amount 覆盖率未达到准入阈值。',
  error_code: 'AMOUNT_COVERAGE',
  finished_at: '2026-08-12T15:42:00+08:00',
}

export const successRun: ResearchRun = {
  id: 'run-20260812-001',
  as_of: '2026-08-12',
  status: 'success',
  created_at: '2026-08-12T16:05:00+08:00',
  model_id: 'small-strict-pit',
  protocol: 'strict_pit',
  model_versions: ['small-v1'],
  scoreable: false,
  viewed_test: true,
  data_hash: 'data000000000000000000000000000000000000001',
  model_hash: 'model0000000000000000000000000000000000001',
  tokenizer_hash: 'token000000000000000000000000000000000001',
  config_hash: 'config00000000000000000000000000000000001',
  code_hash: 'code000000000000000000000000000000000001',
  warnings: [],
  experiment_matrix: [],
  scores: [
    {
      rank: 1,
      symbol: '600000.SH',
      name: '浦发银行',
      score: 0.0832,
      forecast_return: 0.041,
      coverage: 1,
      eligible: true,
      explanation: 'Small严格PIT轨分数，数据覆盖完整。',
      model_scores: { small: 0.0832 },
      forecast: [
        { session: '2026-08-13', p10: 10.1, mean: 10.3, p90: 10.5 },
        { session: '2026-08-14', p10: 10.0, mean: 10.4, p90: 10.8 },
      ],
    },
  ],
}

export const paperAccount: PaperAccount = {
  as_of: '2026-08-12',
  initial_cash: 100_000,
  cash: 67_000,
  market_value: 34_000,
  total_equity: 101_000,
  total_return: 0.01,
  valuation_policy: 'REAL_CLOSE_OR_BOOK_COST',
  positions: [],
  orders: [],
  nav: [],
  gaps: [],
}

export const snapshot = (overrides: Partial<DashboardSnapshot> = {}): DashboardSnapshot => ({
  system: {
    service_state: 'ready',
    server_time: '2026-08-12T16:05:00+08:00',
    latest_closed_session: '2026-08-12',
    data_as_of: '2026-08-12',
    inference_as_of: null,
    active_job_id: null,
    primary_model: null,
    warnings: [],
  },
  jobs: [],
  latest_run: null,
  paper: null,
  ...overrides,
})
