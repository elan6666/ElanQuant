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
  run_id: string | null
  coalesced: boolean
  events: JobEvent[]
}

export type ExperimentTrack = 'zero_shot' | 'official_style' | 'strict_pit'
export type ExperimentState = 'pending' | 'running' | 'passed' | 'failed' | 'blocked'

export interface ExperimentCell {
  id: string
  model_size: 'small' | 'base'
  track: ExperimentTrack
  state: ExperimentState
  rank_ic: number | null
  pearson_ic: number | null
  top10_mean_return: number | null
  model_hash: string | null
  receipt: string | null
  note: string | null
  evaluations: Partial<Record<'validation_2025' | 'test_viewed_2026', EvaluationSplit>>
}

export interface EvaluationSplit {
  rank_ic: number
  pearson_ic: number
  top10_mean_return: number
  rows: number
  cross_sections: number
  anchor_set_sha256: string
}

export interface DataHealth {
  status: string | null
  resolved_session: string | null
  generated_at_utc: string | null
  generated_after_market_finalization: boolean | null
  daily_finalization_cutoff: string | null
  membership_count: number | null
  eligible_symbols: number | null
  excluded_counts: Record<string, number>
  membership_snapshot: string | null
  membership_available_session: string | null
  membership_availability_policy: string | null
  membership_revision_limitation: string | null
  transport_caveat: string | null
  snapshot_logic_sha256: string | null
}

export interface PaperPublication {
  state: string | null
  source_run_id: string | null
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
  input_completeness: number | null
  eligible: boolean
  explanation: string
  model_spread: number | null
  previous_rank: number | null
  rank_delta: number | null
  selected_top3: boolean
  paper_decision: string | null
  paper_reason: string | null
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
  evaluation_hash: string
  warnings: string[]
  paper_publication: PaperPublication
  data_health: DataHealth | null
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
  run_id: string | null
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

export interface RunSummary {
  id: string
  as_of: string
  created_at: string
  protocol: string
  paper_publication_state: string | null
  paper_publication_run_id: string | null
}

export interface RankChange {
  code: string
  from_rank: number
  to_rank: number
  delta: number
}

export interface RunDiff {
  run_id: string
  against_run_id: string | null
  comparable: boolean
  reason: string | null
  same_session: boolean | null
  identity_changes: Record<string, boolean>
  top3_overlap: number | null
  top10_overlap: number | null
  top3_added: string[]
  top3_dropped: string[]
  largest_rank_changes: RankChange[]
}

export interface PaperDecision {
  run_id: string
  symbol: string
  name: string
  rank: number
  decision: string
  reason: string
  quantity: number
  sizing_price: number
}

export interface PaperSummary {
  sample_sessions: number
  evidence_state: 'available' | 'insufficient_evidence'
  order_counts: { pending: number; filled: number; rejected: number }
  decision_counts: Record<string, number>
  total_fees: number
  gross_turnover: number | null
  max_drawdown: number | null
  latest_publication: (PaperPublication & { run_id: string; signal_session: string }) | null
  latest_decisions: PaperDecision[]
  warnings: string[]
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
  research_catalog: ExperimentCell[]
  research_catalog_available: boolean
  runs: RunSummary[]
  run_diff: RunDiff | null
  paper: PaperAccount | null
  paper_summary: PaperSummary | null
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
