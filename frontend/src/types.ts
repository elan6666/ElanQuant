export type ServiceState = 'ready' | 'degraded' | 'offline'
export type ExecutionLocation = 'local' | 'remote'
export type ExecutionProfile =
  | 'local-apple-silicon'
  | 'remote-linux-nvidia'
  | 'legacy-yilangliu'

export interface ExecutionProfileAvailability {
  available: boolean
  profile_id: ExecutionProfile | null
  reason: string | null
}
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
  | 'infer_base'
  | 'scoring'
  | 'paper_ledger'
  | 'research_only'
  | 'completed'

export interface SystemStatus {
  service_state: ServiceState
  server_time: string | null
  latest_closed_session: string | null
  data_as_of: string | null
  inference_as_of: string | null
  active_job_id: string | null
  primary_model: string | null
  active_execution_profile: ExecutionProfile
  default_execution_location: ExecutionLocation
  execution_profiles: Record<ExecutionLocation, ExecutionProfileAvailability>
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
  execution_profile: ExecutionProfile
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
  evaluations: Partial<
    Record<'validation_2025' | 'test_viewed_2026' | 'test_viewed_official_v3', EvaluationSplit>
  >
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
  reference_price: number | null
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

export type OfficialDemoSignal = 'mean' | 'last' | 'max' | 'min'
export type HistoricalEvaluationSplit =
  | 'validation_2025'
  | 'test_viewed_2026'
  | 'test_viewed_official_v3'
export type HistoricalStrategyVariant = 'official_top50' | 'historical_top3'
export type HistoricalModelCell =
  | 'small-zero-shot'
  | 'small-official-ft'
  | 'small-strict-pit'
  | 'base-zero-shot'
  | 'base-official-ft'
  | 'base-strict-pit'

export interface OfficialDemoMetrics {
  total_return_with_cost: number
  benchmark_return: number
  excess_return_without_cost: number
  excess_return_with_cost: number
  annualized_return_with_cost: number
  annualized_excess_return_with_cost: number
  information_ratio_with_cost: number
  max_drawdown_with_cost: number
  total_cost: number
  turnover_mean: number | null
}

export interface HistoricalBacktest {
  id: string
  state: 'passed'
  track_kind:
    | 'OFFICIAL_DEMO_METHOD_EXTENDED_PIT'
    | 'HISTORICAL_MODEL_MATRIX'
    | 'OFFICIAL_SPLIT_V3_MODEL_MATRIX'
  model_cell_id: HistoricalModelCell
  generated_at: string
  evaluation_split: HistoricalEvaluationSplit
  strategy_variant_id: HistoricalStrategyVariant
  strategy_role: 'OFFICIAL_METHOD_BASELINE' | 'PORTFOLIO_SENSITIVITY_VARIANT'
  comparison_group_id: string
  execution_domain: 'HISTORICAL_QLIB_SIMULATION'
  online_paper_equivalent: false
  promotion_eligible: boolean
  source_backtest_id: string | null
  observability: {
    turnover_exposed: boolean
    position_count_exposed: boolean
  } | null
  result_role:
    | 'TRAINING_VALIDATION_CHECKPOINT_SELECTION'
    | 'CORRECTED_OPENED_OOS_DIAGNOSTIC'
    | 'POST_HOC_HISTORICAL_SENSITIVITY'
    | 'POST_HOC_OPENED_STRATEGY_DIAGNOSTIC'
    | 'POST_HOC_MODEL_STRATEGY_COMPARISON'
    | 'POST_HOC_OPENED_MODEL_STRATEGY_DIAGNOSTIC'
    | 'OPENED_ROLLING_TEST_MODEL_STRATEGY_DIAGNOSTIC'
  selection_eligible: boolean
  used_for_selection: boolean
  test_data_access: 'NOT_APPLICABLE' | 'VIEWED'
  primary_signal: 'mean'
  receipt_sha256: string
  signal_receipt_sha256: string
  provider_receipt_sha256: string
  backtest_code_sha256: string
  analysis_lock_sha256: string | null
  strategy: {
    topk: 50 | 3
    n_drop: 5 | 1
    hold_thresh: 5
    method_sell: 'bottom'
    method_buy: 'top'
    only_tradable: false
    forbid_all_trade_at_limit: true
  }
  execution: {
    account: number
    benchmark: 'SH000300'
    delay_execution: true
    deal_price: 'open'
    open_cost: number
    close_cost: number
    min_cost: number
    limit_threshold: number
  }
  support: {
    sessions: number
    signal_rows: number
    signal_cross_sections: number | null
    actual_start: string | null
    actual_end: string | null
    candidate_min: number | null
    candidate_median: number | null
    candidate_max: number | null
  }
  metrics: Record<OfficialDemoSignal, OfficialDemoMetrics>
  qlib: { version: string; metadata_sha256: string; record_sha256: string; source_tree_sha256: string }
  curve_semantics: { official: string; derived: string }
  deviations: string[]
}

export interface HistoricalBacktestPoint {
  session: string
  strategy: number
  benchmark: number
  excess: number
  strategy_nav: number
  benchmark_nav: number
  turnover?: number | null
  position_count?: number | null
}

export interface HistoricalHolding {
  instrument: string
  weight: number
  amount: number
  value: number
}

export interface HistoricalHoldingsSnapshot {
  backtest_id: string
  available: true
  signal: 'mean'
  empty: boolean
  sessions: string[]
  default_session: string
  selected_session: string
  source: {
    artifact_sha256: string
    receipt_sha256: string
    backtest_receipt_sha256: string
  }
  holdings: HistoricalHolding[]
}

/** A single, execution-aligned comparison is intentionally separate from the
 * Kronos-only historical catalogue.  Raw model outputs are not comparable;
 * only the protocol and strategy metrics below share a denominator. */
export interface CrossModelComparison {
  available: boolean
  id: string | null
  protocol: {
    id: string
    label: string
    universe: string
    frequency: string
    signal_start: string
    signal_end: string
    execution_start: string
    execution_end: string
    anchor_set_sha256: string
    label_definition: string
    viewed: boolean
  } | null
  models: CrossModelComparisonModel[]
}

export interface CrossModelComparisonMetrics {
  rank_ic?: number | null
  pearson_ic?: number | null
  icir?: number | null
  mae?: number | null
  rmse?: number | null
  coverage?: number | null
  total_return_with_cost?: number | null
  benchmark_return?: number | null
  excess_return_with_cost?: number | null
  information_ratio_with_cost?: number | null
  max_drawdown_with_cost?: number | null
  turnover_mean?: number | null
}

export interface CrossModelHolding {
  instrument: string
  weight: number
  amount?: number | null
  value?: number | null
}

export interface CrossModelStrategy {
  id: string
  label: string
  topk: 1 | 3 | 50
  metrics: CrossModelComparisonMetrics
  series: HistoricalBacktestPoint[]
  holdings: { session: string; items: CrossModelHolding[]; receipt_sha256?: string | null } | null
}

export interface CrossModelComparisonModel {
  id: string
  family: 'itransformer_b2' | 'kronos_base'
  label: string
  input: { description: string; lookback_sessions: number; features: string[] }
  checkpoint_sha256: string
  common_metrics: CrossModelComparisonMetrics
  native_metrics?: Record<string, number | string | null>
  strategies: CrossModelStrategy[]
}

export interface DashboardSnapshot {
  system: SystemStatus
  jobs: Job[]
  latest_run: ResearchRun | null
  research_catalog: ExperimentCell[]
  research_catalog_available: boolean
  historical_backtests: HistoricalBacktest[]
  historical_backtest_available: boolean
  historical_backtest_series: Record<string, HistoricalBacktestPoint[]>
  cross_model_comparison?: CrossModelComparison
  runs: RunSummary[]
  run_diff: RunDiff | null
  paper: PaperAccount | null
  paper_summary: PaperSummary | null
}

export interface SubmitJobReceipt {
  job_id: string
  coalesced: boolean
  execution_profile: ExecutionProfile
}

export interface ApiClient {
  getSnapshot(signal?: AbortSignal): Promise<DashboardSnapshot>
  getHistoricalHoldings(
    backtestId: string,
    session?: string,
    signal?: AbortSignal,
  ): Promise<HistoricalHoldingsSnapshot | null>
  submitUpdateInfer(profile: ExecutionProfile, signal?: AbortSignal): Promise<SubmitJobReceipt>
  retryJob(id: string, signal?: AbortSignal): Promise<SubmitJobReceipt>
}
