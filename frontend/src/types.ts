export type ServiceState = 'ready' | 'degraded' | 'offline'
export type JobState =
  | 'queued'
  | 'running'
  | 'data_incomplete'
  | 'failed'
  | 'interrupted'
  | 'succeeded'

export type JobStage =
  | 'queued'
  | 'resolving_session'
  | 'updating_data'
  | 'validating_data'
  | 'infer_small'
  | 'scoring'
  | 'paper_ledger'
  | 'completed'

export interface SystemStatus {
  service_state: ServiceState
  server_time: string | null
  latest_closed_session: string | null
  data_as_of: string | null
  inference_as_of: string | null
  active_job_id: string | null
  primary_model: string | null
  warnings: string[]
}

export interface JobEvent {
  id: string
  stage: JobStage
  state: JobState
  message: string
  created_at: string
}

export interface Job {
  id: string
  kind: 'update_infer'
  state: JobState
  stage: JobStage
  requested_at: string
  started_at: string | null
  finished_at: string | null
  as_of: string | null
  progress: number
  message: string | null
  error_code: string | null
  retry_of: string | null
  coalesced: boolean
  events: JobEvent[]
}

export type ExperimentTrack = 'zero_shot' | 'official_style' | 'strict_pit'
export type ExperimentState = 'pending' | 'running' | 'passed' | 'failed' | 'blocked'

export interface ExperimentCell {
  id: string
  model_size: 'small'
  track: ExperimentTrack
  state: ExperimentState
  rank_ic: number | null
  pearson_ic: number | null
  top10_mean_return: number | null
  model_hash: string | null
  receipt: string | null
  note: string | null
}

export interface ForecastPoint {
  session: string
  p10: number
  mean: number
  p90: number
}

export interface StockScore {
  rank: number
  symbol: string
  name: string
  score: number
  forecast_return: number
  coverage: number | null
  eligible: boolean
  explanation: string
  model_scores: Record<string, number>
  forecast: ForecastPoint[]
}

export interface ResearchRun {
  id: string
  as_of: string
  status: 'success' | 'stale'
  created_at: string
  model_id: string
  protocol: string
  model_versions: string[]
  scoreable: boolean
  viewed_test: boolean
  data_hash: string
  model_hash: string
  tokenizer_hash: string
  config_hash: string
  code_hash: string
  warnings: string[]
  experiment_matrix: ExperimentCell[]
  scores: StockScore[]
}

export interface PaperPosition {
  symbol: string
  name: string
  quantity: number
  available_quantity: number | null
  average_cost: number | null
  last_price: number | null
  valuation_source: 'latest_close' | 'average_cost_fallback' | null
  market_value: number | null
  unrealized_pnl: number | null
  held_sessions: number | null
}

export interface PaperOrder {
  id: string
  signal_session: string
  execution_session: string | null
  symbol: string
  name: string
  side: 'buy' | 'sell'
  quantity: number
  status: 'intent' | 'filled' | 'rejected'
  price: number | null
  fees: number | null
  reason: string | null
}

export interface NavPoint {
  session: string
  nav: number
  benchmark_nav: number | null
}

export interface PaperAccount {
  as_of: string | null
  initial_cash: number
  cash: number
  market_value: number
  total_equity: number
  total_return: number | null
  valuation_policy: string | null
  positions: PaperPosition[]
  orders: PaperOrder[]
  nav: NavPoint[]
  gaps: string[]
}

export interface DashboardSnapshot {
  system: SystemStatus
  jobs: Job[]
  latest_run: ResearchRun | null
  paper: PaperAccount | null
}

export interface SubmitJobReceipt {
  job_id: string
  coalesced: boolean
}

export interface ApiClient {
  getSnapshot(signal?: AbortSignal): Promise<DashboardSnapshot>
  submitUpdateInfer(signal?: AbortSignal): Promise<SubmitJobReceipt>
  retryJob(id: string, signal?: AbortSignal): Promise<SubmitJobReceipt>
}
