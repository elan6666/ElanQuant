import type {
  ApiClient,
  CrossModelComparison,
  DashboardSnapshot,
  DataHealth,
  EvaluationSplit,
  ExecutionProfile,
  ExperimentCell,
  ForecastPoint,
  HistoricalBacktest,
  HistoricalBacktestPoint,
  HistoricalHoldingsSnapshot,
  Job,
  JobEvent,
  NavPoint,
  OfficialDemoMetrics,
  PaperAccount,
  PaperDecision,
  PaperOrder,
  PaperPosition,
  PaperSummary,
  RankChange,
  ResearchRun,
  RunDiff,
  RunSummary,
  StockScore,
  SubmitJobReceipt,
  SystemStatus,
} from './types'

export class ApiContractError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiContractError'
  }
}

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiRequestError'
  }
}

const object = (value: unknown, path: string): Record<string, unknown> => {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new ApiContractError(`${path} 应为对象`)
  }
  return value as Record<string, unknown>
}

const array = (value: unknown, path: string): unknown[] => {
  if (!Array.isArray(value)) throw new ApiContractError(`${path} 应为数组`)
  return value
}

const string = (value: unknown, path: string): string => {
  if (typeof value !== 'string') throw new ApiContractError(`${path} 应为字符串`)
  return value
}

const nullableString = (value: unknown, path: string): string | null =>
  value === null ? null : string(value, path)

const optionalString = (value: unknown, path: string): string | null =>
  value === undefined || value === null ? null : string(value, path)

const number = (value: unknown, path: string): number => {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new ApiContractError(`${path} 应为有限数字`)
  }
  return value
}

const nullableNumber = (value: unknown, path: string): number | null =>
  value === null ? null : number(value, path)

const optionalNumber = (value: unknown, path: string): number | null =>
  value === undefined || value === null ? null : number(value, path)

const boolean = (value: unknown, path: string): boolean => {
  if (typeof value !== 'boolean') throw new ApiContractError(`${path} 应为布尔值`)
  return value
}

const optionalBoolean = (value: unknown, fallback: boolean, path: string): boolean =>
  value === undefined || value === null ? fallback : boolean(value, path)

const enumValue = <T extends string>(value: unknown, allowed: readonly T[], path: string): T => {
  if (typeof value !== 'string' || !allowed.includes(value as T)) {
    throw new ApiContractError(`${path} 的值不受支持`)
  }
  return value as T
}

const strings = (value: unknown, path: string): string[] =>
  array(value, path).map((item, index) => string(item, `${path}[${index}]`))

const optionalStrings = (value: unknown, path: string): string[] =>
  value === undefined || value === null ? [] : strings(value, path)

const optionalArray = (value: unknown, path: string): unknown[] =>
  value === undefined || value === null ? [] : array(value, path)

const executionProfileIds = [
  'local-apple-silicon',
  'remote-linux-nvidia',
  'legacy-yilangliu',
] as const

const parseExecutionProfile = (value: unknown, path: string): ExecutionProfile =>
  enumValue(value, executionProfileIds, path)

const parseSystem = (value: unknown): SystemStatus => {
  const item = object(value, 'system')
  const activeProfile =
    item.execution_profile === undefined || item.execution_profile === null
      ? 'legacy-yilangliu'
      : parseExecutionProfile(item.execution_profile, 'system.execution_profile')
  const activeLocation = activeProfile === 'local-apple-silicon' ? 'local' : 'remote'
  return {
    service_state:
      item.service_state === undefined
        ? 'ready'
        : enumValue(item.service_state, ['ready', 'degraded', 'offline'], 'system.service_state'),
    server_time: optionalString(item.server_time, 'system.server_time'),
    latest_closed_session: optionalString(item.latest_closed_session, 'system.latest_closed_session'),
    data_as_of: nullableString(item.data_as_of, 'system.data_as_of'),
    inference_as_of: nullableString(item.inference_as_of, 'system.inference_as_of'),
    active_job_id: nullableString(item.active_job_id, 'system.active_job_id'),
    primary_model: optionalString(item.primary_model, 'system.primary_model'),
    active_execution_profile: activeProfile,
    default_execution_location: activeLocation,
    execution_profiles: {
      local: {
        available: activeLocation === 'local',
        profile_id: activeLocation === 'local' ? activeProfile : null,
        reason: activeLocation === 'local' ? null : '请从本机 profile 启动 ElanQuant',
      },
      remote: {
        available: activeLocation === 'remote',
        profile_id: activeLocation === 'remote' ? activeProfile : null,
        reason: activeLocation === 'remote' ? null : '请从远程 profile 启动 ElanQuant',
      },
    },
    warnings: optionalStrings(item.warnings, 'system.warnings'),
  }
}

const jobStates = ['queued', 'running', 'data_incomplete', 'failed', 'interrupted', 'succeeded'] as const
const jobStages = [
  'queued',
  'resolving_session',
  'updating_data',
  'validating_data',
  'infer_small',
  'infer_base',
  'scoring',
  'paper_ledger',
  'research_only',
  'completed',
] as const

const normalizeJobState = (value: unknown, path: string): Job['state'] => {
  const raw = string(value, path).toLowerCase()
  if (raw === 'success' || raw === 'completed') return 'succeeded'
  return enumValue(raw, jobStates, path)
}

const normalizeStage = (value: unknown, path: string): Job['stage'] => {
  const raw = string(value, path).toLowerCase()
  if (raw === 'success' || raw === 'succeeded') return 'completed'
  if (raw === 'failed' || raw === 'interrupted' || raw === 'data_incomplete') {
    return 'validating_data'
  }
  return enumValue(raw, jobStages, path)
}

const parseEvent = (value: unknown, path: string): JobEvent => {
  const item = object(value, path)
  return {
    id: string(item.id, `${path}.id`),
    stage: normalizeStage(item.stage, `${path}.stage`),
    state: normalizeJobState(item.state ?? item.status, `${path}.status`),
    message: string(item.message, `${path}.message`),
    created_at: string(item.created_at, `${path}.created_at`),
  }
}

const parseJob = (value: unknown, path: string): Job => {
  const item = object(value, path)
  const state = normalizeJobState(item.status ?? item.state, `${path}.status`)
  const stage = normalizeStage(item.stage, `${path}.stage`)
  const stageIndex = jobStages.indexOf(stage)
  const error = typeof item.error === 'string' ? item.error : null
  return {
    id: string(item.id, `${path}.id`),
    kind: item.kind === undefined ? 'update_infer' : enumValue(item.kind, ['update_infer'], `${path}.kind`),
    execution_profile:
      item.execution_profile === undefined || item.execution_profile === null
        ? 'legacy-yilangliu'
        : parseExecutionProfile(item.execution_profile, `${path}.execution_profile`),
    state,
    stage,
    requested_at: string(item.created_at ?? item.requested_at, `${path}.created_at`),
    started_at: optionalString(item.started_at, `${path}.started_at`),
    finished_at: optionalString(item.finished_at, `${path}.finished_at`),
    as_of: optionalString(
      item.as_of ?? item.resolved_session ?? item.requested_session,
      `${path}.as_of`,
    ),
    progress:
      optionalNumber(item.progress, `${path}.progress`) ??
      (state === 'succeeded' ? 1 : Math.max(0, stageIndex / (jobStages.length - 1))),
    message: optionalString(item.message, `${path}.message`) ?? error,
    error_code: optionalString(item.error_code, `${path}.error_code`),
    retry_of: optionalString(item.retry_of ?? item.parent_job_id, `${path}.retry_of`),
    run_id: optionalString(item.run_id, `${path}.run_id`),
    coalesced: optionalBoolean(item.coalesced, false, `${path}.coalesced`),
    events: optionalArray(item.events, `${path}.events`).map((event, index) =>
      parseEvent(event, `${path}.events[${index}]`),
    ),
  }
}

const parseExperiment = (value: unknown, path: string): ExperimentCell => {
  const item = object(value, path)
  const evaluationsRaw =
    item.evaluations === undefined || item.evaluations === null
      ? {}
      : object(item.evaluations, `${path}.evaluations`)
  const parseEvaluation = (value: unknown, evaluationPath: string): EvaluationSplit => {
    const evaluation = object(value, evaluationPath)
    return {
      rank_ic: number(evaluation.rank_ic, `${evaluationPath}.rank_ic`),
      pearson_ic: number(evaluation.pearson_ic, `${evaluationPath}.pearson_ic`),
      top10_mean_return: number(
        evaluation.top10_mean_return,
        `${evaluationPath}.top10_mean_return`,
      ),
      rows: number(evaluation.rows, `${evaluationPath}.rows`),
      cross_sections: number(evaluation.cross_sections, `${evaluationPath}.cross_sections`),
      anchor_set_sha256: string(
        evaluation.anchor_set_sha256,
        `${evaluationPath}.anchor_set_sha256`,
      ),
    }
  }
  return {
    id: string(item.id, `${path}.id`),
    model_size: enumValue(item.model_size, ['small', 'base'], `${path}.model_size`),
    track: enumValue(item.track, ['zero_shot', 'official_style', 'strict_pit'], `${path}.track`),
    state: enumValue(item.state, ['pending', 'running', 'passed', 'failed', 'blocked'], `${path}.state`),
    rank_ic: nullableNumber(item.rank_ic, `${path}.rank_ic`),
    pearson_ic: nullableNumber(item.pearson_ic, `${path}.pearson_ic`),
    top10_mean_return: nullableNumber(item.top10_mean_return, `${path}.top10_mean_return`),
    model_hash: nullableString(item.model_hash, `${path}.model_hash`),
    receipt: nullableString(item.receipt, `${path}.receipt`),
    note: nullableString(item.note, `${path}.note`),
    evaluations: Object.fromEntries(
      Object.entries(evaluationsRaw).map(([split, evaluation]) => [
        enumValue(
          split,
          ['validation_2025', 'test_viewed_2026', 'test_viewed_official_v3'],
          `${path}.evaluations.split`,
        ),
        parseEvaluation(evaluation, `${path}.evaluations.${split}`),
      ]),
    ),
  }
}

const parseDataHealth = (value: unknown, path: string): DataHealth => {
  const item = object(value, path)
  const excludedRaw =
    item.excluded_counts === undefined || item.excluded_counts === null
      ? {}
      : object(item.excluded_counts, `${path}.excluded_counts`)
  return {
    status: optionalString(item.status, `${path}.status`),
    resolved_session: optionalString(item.resolved_session, `${path}.resolved_session`),
    generated_at_utc: optionalString(item.generated_at_utc, `${path}.generated_at_utc`),
    generated_after_market_finalization:
      item.generated_after_market_finalization === undefined ||
      item.generated_after_market_finalization === null
        ? null
        : boolean(
            item.generated_after_market_finalization,
            `${path}.generated_after_market_finalization`,
          ),
    daily_finalization_cutoff: optionalString(
      item.daily_finalization_cutoff,
      `${path}.daily_finalization_cutoff`,
    ),
    membership_count: optionalNumber(item.membership_count, `${path}.membership_count`),
    eligible_symbols: optionalNumber(item.eligible_symbols, `${path}.eligible_symbols`),
    excluded_counts: Object.fromEntries(
      Object.entries(excludedRaw).map(([reason, count]) => [
        reason,
        number(count, `${path}.excluded_counts.${reason}`),
      ]),
    ),
    membership_snapshot: optionalString(item.membership_snapshot, `${path}.membership_snapshot`),
    membership_available_session: optionalString(
      item.membership_available_session,
      `${path}.membership_available_session`,
    ),
    membership_availability_policy: optionalString(
      item.membership_availability_policy,
      `${path}.membership_availability_policy`,
    ),
    membership_revision_limitation: optionalString(
      item.membership_revision_limitation,
      `${path}.membership_revision_limitation`,
    ),
    transport_caveat: optionalString(item.transport_caveat, `${path}.transport_caveat`),
    snapshot_logic_sha256: optionalString(
      item.snapshot_logic_sha256,
      `${path}.snapshot_logic_sha256`,
    ),
  }
}

const parseForecast = (value: unknown, path: string): ForecastPoint => {
  const item = object(value, path)
  return {
    session: string(item.session, `${path}.session`),
    p10: number(item.p10, `${path}.p10`),
    mean: number(item.mean, `${path}.mean`),
    p90: number(item.p90, `${path}.p90`),
  }
}

const parseScore = (value: unknown, path: string): StockScore => {
  const item = object(value, path)
  const modelScores = item.model_scores === undefined ? {} : object(item.model_scores, `${path}.model_scores`)
  const symbol = string(item.code ?? item.symbol, `${path}.code`)
  return {
    rank: number(item.rank, `${path}.rank`),
    symbol,
    name: optionalString(item.name, `${path}.name`) ?? symbol,
    score: number(item.score, `${path}.score`),
    forecast_return: number(item.forecast_return, `${path}.forecast_return`),
    reference_price: optionalNumber(item.reference_price, `${path}.reference_price`),
    coverage: optionalNumber(item.coverage, `${path}.coverage`),
    input_completeness: optionalNumber(
      item.input_completeness ?? item.coverage,
      `${path}.input_completeness`,
    ),
    eligible: boolean(item.eligible, `${path}.eligible`),
    explanation: optionalString(item.explanation, `${path}.explanation`) ?? '',
    model_spread: optionalNumber(item.model_spread, `${path}.model_spread`),
    previous_rank: optionalNumber(item.previous_rank, `${path}.previous_rank`),
    rank_delta: optionalNumber(item.rank_delta, `${path}.rank_delta`),
    selected_top3: optionalBoolean(item.selected_top3, false, `${path}.selected_top3`),
    paper_decision: optionalString(item.paper_decision, `${path}.paper_decision`),
    paper_reason: optionalString(item.paper_reason, `${path}.paper_reason`),
    model_scores: Object.fromEntries(
      Object.entries(modelScores).map(([key, score]) => [key, number(score, `${path}.model_scores.${key}`)]),
    ),
    forecast: optionalArray(item.forecast, `${path}.forecast`).map((point, index) =>
      parseForecast(point, `${path}.forecast[${index}]`),
    ),
  }
}

const parseModelVersions = (value: unknown, path: string): string[] => {
  if (Array.isArray(value)) {
    return value.map((entry, index) => {
      if (typeof entry === 'string') return entry
      const item = object(entry, `${path}[${index}]`)
      return string(item.id ?? item.name ?? item.model_id, `${path}[${index}].id`)
    })
  }
  const item = object(value, path)
  return Object.entries(item).map(([key, version]) =>
    typeof version === 'string' ? `${key}@${version}` : key,
  )
}

const normalizedRunStatus = (value: unknown, path: string): ResearchRun['status'] => {
  const status = string(value, path).toLowerCase()
  if (status === 'success' || status === 'succeeded' || status === 'completed') return 'success'
  if (status === 'stale') return 'stale'
  throw new ApiContractError(`${path} 的值不受支持`)
}

const parseRun = (value: unknown, scores: StockScore[] = []): ResearchRun => {
  const item = object(value, 'latest_run')
  const provenance = object(item.provenance, 'latest_run.provenance')
  const modelVersions = parseModelVersions(item.model_versions, 'latest_run.model_versions')
  const publication =
    item.paper_publication === undefined || item.paper_publication === null
      ? {}
      : object(item.paper_publication, 'latest_run.paper_publication')
  return {
    id: string(item.id, 'latest_run.id'),
    as_of: string(item.as_of, 'latest_run.as_of'),
    status: normalizedRunStatus(item.status, 'latest_run.status'),
    created_at: optionalString(item.created_at, 'latest_run.created_at') ?? string(item.as_of, 'latest_run.as_of'),
    model_id: optionalString(item.model_id, 'latest_run.model_id') ?? modelVersions.join(' + '),
    protocol: string(item.protocol, 'latest_run.protocol'),
    model_versions: modelVersions,
    scoreable: optionalBoolean(item.scoreable, false, 'latest_run.scoreable'),
    viewed_test: optionalBoolean(item.viewed_test, false, 'latest_run.viewed_test'),
    data_hash: optionalString(provenance.data_hash, 'latest_run.provenance.data_hash') ?? '',
    model_hash: optionalString(provenance.model_hash, 'latest_run.provenance.model_hash') ?? '',
    tokenizer_hash: optionalString(provenance.tokenizer_hash, 'latest_run.provenance.tokenizer_hash') ?? '',
    config_hash: optionalString(provenance.config_hash, 'latest_run.provenance.config_hash') ?? '',
    code_hash: optionalString(provenance.code_hash, 'latest_run.provenance.code_hash') ?? '',
    evaluation_hash:
      optionalString(provenance.evaluation_hash, 'latest_run.provenance.evaluation_hash') ?? '',
    warnings: optionalStrings(item.warnings, 'latest_run.warnings'),
    paper_publication: {
      state: optionalString(publication.state, 'latest_run.paper_publication.state'),
      source_run_id: optionalString(
        publication.source_run_id,
        'latest_run.paper_publication.source_run_id',
      ),
    },
    data_health:
      item.data_health === undefined || item.data_health === null
        ? null
        : parseDataHealth(item.data_health, 'latest_run.data_health'),
    experiment_matrix: optionalArray(item.experiment_matrix, 'latest_run.experiment_matrix').map((cell, index) =>
      parseExperiment(cell, `latest_run.experiment_matrix[${index}]`),
    ),
    scores,
  }
}

const parsePosition = (value: unknown, path: string): PaperPosition => {
  const item = object(value, path)
  const symbol = string(item.code ?? item.symbol, `${path}.code`)
  return {
    symbol,
    name: optionalString(item.name, `${path}.name`) ?? symbol,
    quantity: number(item.quantity, `${path}.quantity`),
    available_quantity: optionalNumber(item.available_quantity, `${path}.available_quantity`),
    average_cost: optionalNumber(item.average_cost, `${path}.average_cost`),
    last_price: optionalNumber(item.last_price, `${path}.last_price`),
    valuation_source:
      item.valuation_source === undefined || item.valuation_source === null
        ? null
        : item.valuation_source === 'LATEST_STRICT_SCORE_CLOSE' ||
            item.valuation_source === 'MARKET_CLOSE'
          ? 'latest_close'
          : item.valuation_source === 'AVERAGE_COST_FALLBACK'
            ? 'average_cost_fallback'
            : (() => { throw new ApiContractError(`${path}.valuation_source 的值不受支持`) })(),
    market_value: optionalNumber(item.market_value, `${path}.market_value`),
    unrealized_pnl: optionalNumber(item.unrealized_pnl, `${path}.unrealized_pnl`),
    held_sessions: optionalNumber(item.held_sessions, `${path}.held_sessions`),
  }
}

const parseOrder = (value: unknown, path: string): PaperOrder => {
  const item = object(value, path)
  const symbol = string(item.code ?? item.symbol, `${path}.code`)
  return {
    id: string(item.id, `${path}.id`),
    run_id: optionalString(item.run_id, `${path}.run_id`),
    signal_session: string(item.signal_date ?? item.signal_session, `${path}.signal_date`),
    execution_session: optionalString(item.execution_date ?? item.execution_session, `${path}.execution_date`),
    symbol,
    name: optionalString(item.name, `${path}.name`) ?? symbol,
    side: enumValue(string(item.side, `${path}.side`).toLowerCase(), ['buy', 'sell'], `${path}.side`),
    quantity: number(item.quantity, `${path}.quantity`),
    status: enumValue(string(item.status, `${path}.status`).toLowerCase(), ['intent', 'filled', 'rejected'], `${path}.status`),
    price: optionalNumber(item.price, `${path}.price`),
    fees: optionalNumber(item.fees, `${path}.fees`),
    reason: optionalString(item.rejection_reason ?? item.reason, `${path}.rejection_reason`),
  }
}

const parseNav = (value: unknown, path: string): NavPoint => {
  const item = object(value, path)
  return {
    session: string(item.session, `${path}.session`),
    nav: number(item.nav, `${path}.nav`),
    benchmark_nav: nullableNumber(item.benchmark_nav, `${path}.benchmark_nav`),
  }
}

const parsePaper = (value: unknown, orders: PaperOrder[] = [], nav: NavPoint[] = []): PaperAccount => {
  const item = object(value, 'paper')
  const equity = number(item.equity ?? item.total_equity, 'paper.equity')
  const cash = number(item.cash, 'paper.cash')
  const initialCash = optionalNumber(item.initial_cash, 'paper.initial_cash')
  return {
    as_of: nullableString(item.as_of, 'paper.as_of'),
    initial_cash: initialCash ?? 100_000,
    cash,
    market_value: optionalNumber(item.market_value, 'paper.market_value') ?? equity - cash,
    total_equity: equity,
    total_return:
      optionalNumber(item.total_return, 'paper.total_return') ??
      (initialCash === null ? null : equity / initialCash - 1),
    valuation_policy: optionalString(item.valuation_policy, 'paper.valuation_policy'),
    positions: array(item.positions, 'paper.positions').map((position, index) =>
      parsePosition(position, `paper.positions[${index}]`),
    ),
    orders,
    nav,
    gaps: optionalStrings(item.gaps, 'paper.gaps'),
  }
}

const parseRunSummary = (value: unknown, path: string): RunSummary => {
  const item = object(value, path)
  return {
    id: string(item.id, `${path}.id`),
    as_of: string(item.as_of_session ?? item.as_of, `${path}.as_of_session`),
    created_at: string(item.created_at, `${path}.created_at`),
    protocol: string(item.protocol, `${path}.protocol`),
    paper_publication_state: optionalString(
      item.paper_publication_state,
      `${path}.paper_publication_state`,
    ),
    paper_publication_run_id: optionalString(
      item.paper_publication_run_id,
      `${path}.paper_publication_run_id`,
    ),
  }
}

const parseRunDiff = (value: unknown): RunDiff => {
  const item = object(value, 'run_diff')
  const comparable = boolean(item.comparable, 'run_diff.comparable')
  const changesRaw =
    item.identity_changes === undefined || item.identity_changes === null
      ? {}
      : object(item.identity_changes, 'run_diff.identity_changes')
  return {
    run_id: string(item.run_id, 'run_diff.run_id'),
    against_run_id: optionalString(item.against_run_id, 'run_diff.against_run_id'),
    comparable,
    reason: optionalString(item.reason, 'run_diff.reason'),
    same_session:
      item.same_session === undefined || item.same_session === null
        ? null
        : boolean(item.same_session, 'run_diff.same_session'),
    identity_changes: Object.fromEntries(
      Object.entries(changesRaw).map(([key, changed]) => [
        key,
        boolean(changed, `run_diff.identity_changes.${key}`),
      ]),
    ),
    top3_overlap: optionalNumber(item.top3_overlap, 'run_diff.top3_overlap'),
    top10_overlap: optionalNumber(item.top10_overlap, 'run_diff.top10_overlap'),
    top3_added: optionalStrings(item.top3_added, 'run_diff.top3_added'),
    top3_dropped: optionalStrings(item.top3_dropped, 'run_diff.top3_dropped'),
    largest_rank_changes: optionalArray(
      item.largest_rank_changes,
      'run_diff.largest_rank_changes',
    ).map((change, index): RankChange => {
      const raw = object(change, `run_diff.largest_rank_changes[${index}]`)
      return {
        code: string(raw.code, `run_diff.largest_rank_changes[${index}].code`),
        from_rank: number(raw.from_rank, `run_diff.largest_rank_changes[${index}].from_rank`),
        to_rank: number(raw.to_rank, `run_diff.largest_rank_changes[${index}].to_rank`),
        delta: number(raw.delta, `run_diff.largest_rank_changes[${index}].delta`),
      }
    }),
  }
}

const parseDecision = (value: unknown, path: string): PaperDecision => {
  const item = object(value, path)
  return {
    run_id: string(item.run_id, `${path}.run_id`),
    symbol: string(item.code ?? item.symbol, `${path}.code`),
    name: string(item.name, `${path}.name`),
    rank: number(item.rank, `${path}.rank`),
    decision: string(item.decision, `${path}.decision`),
    reason: string(item.reason, `${path}.reason`),
    quantity: number(item.quantity, `${path}.quantity`),
    sizing_price: number(item.sizing_price, `${path}.sizing_price`),
  }
}

const parsePaperSummary = (value: unknown): PaperSummary => {
  const item = object(value, 'paper_summary')
  const counts = object(item.order_counts, 'paper_summary.order_counts')
  const decisionCounts = object(item.decision_counts, 'paper_summary.decision_counts')
  const publication =
    item.latest_publication === undefined || item.latest_publication === null
      ? null
      : object(item.latest_publication, 'paper_summary.latest_publication')
  return {
    sample_sessions: number(item.sample_sessions, 'paper_summary.sample_sessions'),
    evidence_state: enumValue(
      item.evidence_state,
      ['available', 'insufficient_evidence'],
      'paper_summary.evidence_state',
    ),
    order_counts: {
      pending: number(counts.pending, 'paper_summary.order_counts.pending'),
      filled: number(counts.filled, 'paper_summary.order_counts.filled'),
      rejected: number(counts.rejected, 'paper_summary.order_counts.rejected'),
    },
    decision_counts: Object.fromEntries(
      Object.entries(decisionCounts).map(([decision, count]) => [
        decision,
        number(count, `paper_summary.decision_counts.${decision}`),
      ]),
    ),
    total_fees: number(item.total_fees, 'paper_summary.total_fees'),
    gross_turnover: optionalNumber(item.gross_turnover, 'paper_summary.gross_turnover'),
    max_drawdown: optionalNumber(item.max_drawdown, 'paper_summary.max_drawdown'),
    latest_publication:
      publication === null
        ? null
        : {
            run_id: string(publication.run_id, 'paper_summary.latest_publication.run_id'),
            signal_session: string(
              publication.signal_session,
              'paper_summary.latest_publication.signal_session',
            ),
            state: optionalString(publication.state, 'paper_summary.latest_publication.state'),
            source_run_id: optionalString(
              publication.source_run_id,
              'paper_summary.latest_publication.source_run_id',
            ),
          },
    latest_decisions: optionalArray(
      item.latest_decisions,
      'paper_summary.latest_decisions',
    ).map((decision, index) => parseDecision(decision, `paper_summary.latest_decisions[${index}]`)),
    warnings: optionalStrings(item.warnings, 'paper_summary.warnings'),
  }
}

const parseOfficialMetrics = (value: unknown, path: string): OfficialDemoMetrics => {
  const item = object(value, path)
  return {
    total_return_with_cost: number(item.total_return_with_cost, `${path}.total_return_with_cost`),
    benchmark_return: number(item.benchmark_return, `${path}.benchmark_return`),
    excess_return_without_cost: number(
      item.excess_return_without_cost,
      `${path}.excess_return_without_cost`,
    ),
    excess_return_with_cost: number(
      item.excess_return_with_cost,
      `${path}.excess_return_with_cost`,
    ),
    annualized_return_with_cost: number(
      item.annualized_return_with_cost,
      `${path}.annualized_return_with_cost`,
    ),
    annualized_excess_return_with_cost: number(
      item.annualized_excess_return_with_cost,
      `${path}.annualized_excess_return_with_cost`,
    ),
    information_ratio_with_cost: number(
      item.information_ratio_with_cost,
      `${path}.information_ratio_with_cost`,
    ),
    max_drawdown_with_cost: number(
      item.max_drawdown_with_cost,
      `${path}.max_drawdown_with_cost`,
    ),
    total_cost: number(item.total_cost, `${path}.total_cost`),
    turnover_mean: optionalNumber(item.turnover_mean, `${path}.turnover_mean`),
  }
}

const parseHistoricalBacktest = (value: unknown, path: string): HistoricalBacktest => {
  const item = object(value, path)
  const strategy = object(item.strategy, `${path}.strategy`)
  const execution = object(item.execution, `${path}.execution`)
  const support = object(item.support, `${path}.support`)
  const metrics = object(item.metrics, `${path}.metrics`)
  const qlib = object(item.qlib, `${path}.qlib`)
  const semantics = object(item.curve_semantics, `${path}.curve_semantics`)
  const observability =
    item.observability === undefined || item.observability === null
      ? null
      : object(item.observability, `${path}.observability`)
  const requireLiteral = <T extends string | number | boolean>(
    value: unknown,
    expected: T,
    literalPath: string,
  ): T => {
    if (value !== expected) throw new ApiContractError(`${literalPath} 不符合封存契约`)
    return expected
  }
  const requireNull = (value: unknown, literalPath: string): null => {
    if (value !== null) throw new ApiContractError(`${literalPath} 不符合封存契约`)
    return null
  }
  const evaluationSplit = string(item.evaluation_split, `${path}.evaluation_split`)
  if (
    evaluationSplit !== 'validation_2025' &&
    evaluationSplit !== 'test_viewed_2026' &&
    evaluationSplit !== 'test_viewed_official_v3'
  ) {
    throw new ApiContractError(`${path}.evaluation_split 不符合封存契约`)
  }
  const finalTest = evaluationSplit !== 'validation_2025'
  const legacy = item.strategy_variant_id === undefined
  const strategyVariant = legacy
    ? 'official_top50'
    : enumValue(
        item.strategy_variant_id,
        ['official_top50', 'historical_top3'],
        `${path}.strategy_variant_id`,
      )
  const historicalTop3 = strategyVariant === 'historical_top3'
  const trackKind = enumValue(
    item.track_kind,
    [
      'OFFICIAL_DEMO_METHOD_EXTENDED_PIT',
      'HISTORICAL_MODEL_MATRIX',
      'OFFICIAL_SPLIT_V3_MODEL_MATRIX',
    ],
    `${path}.track_kind`,
  )
  const matrix = trackKind !== 'OFFICIAL_DEMO_METHOD_EXTENDED_PIT'
  const officialV3 = trackKind === 'OFFICIAL_SPLIT_V3_MODEL_MATRIX'
  const expectedRole = officialV3
    ? 'OPENED_ROLLING_TEST_MODEL_STRATEGY_DIAGNOSTIC'
    : matrix
    ? finalTest
      ? 'POST_HOC_OPENED_MODEL_STRATEGY_DIAGNOSTIC'
      : 'POST_HOC_MODEL_STRATEGY_COMPARISON'
    : historicalTop3
      ? finalTest
        ? 'POST_HOC_OPENED_STRATEGY_DIAGNOSTIC'
        : 'POST_HOC_HISTORICAL_SENSITIVITY'
      : finalTest
        ? 'CORRECTED_OPENED_OOS_DIAGNOSTIC'
        : 'TRAINING_VALIDATION_CHECKPOINT_SELECTION'
  const expectedAccess = finalTest ? 'VIEWED' : 'NOT_APPLICABLE'
  const expectedSelection = matrix ? false : !historicalTop3 && !finalTest
  const strategyRole = legacy
    ? 'OFFICIAL_METHOD_BASELINE'
    : requireLiteral(
        item.strategy_role,
        historicalTop3 ? 'PORTFOLIO_SENSITIVITY_VARIANT' : 'OFFICIAL_METHOD_BASELINE',
        `${path}.strategy_role`,
      )
  return {
    id: string(item.id, `${path}.id`),
    state: requireLiteral(item.state, 'passed', `${path}.state`),
    track_kind: trackKind,
    model_cell_id: enumValue(
      item.model_cell_id,
      [
        'small-zero-shot',
        'small-official-ft',
        'small-strict-pit',
        'base-zero-shot',
        'base-official-ft',
        'base-strict-pit',
      ],
      `${path}.model_cell_id`,
    ),
    generated_at: string(item.generated_at, `${path}.generated_at`),
    evaluation_split: evaluationSplit,
    strategy_variant_id: strategyVariant,
    strategy_role: strategyRole,
    comparison_group_id: legacy
      ? `legacy:${evaluationSplit}`
      : string(item.comparison_group_id, `${path}.comparison_group_id`),
    execution_domain: legacy
      ? 'HISTORICAL_QLIB_SIMULATION'
      : requireLiteral(
          item.execution_domain,
          'HISTORICAL_QLIB_SIMULATION',
          `${path}.execution_domain`,
        ),
    online_paper_equivalent: legacy
      ? false
      : requireLiteral(item.online_paper_equivalent, false, `${path}.online_paper_equivalent`),
    promotion_eligible: legacy
      ? false
      : requireLiteral(item.promotion_eligible, false, `${path}.promotion_eligible`),
    source_backtest_id: legacy
      ? null
      : historicalTop3
        ? string(item.source_backtest_id, `${path}.source_backtest_id`)
        : requireNull(item.source_backtest_id, `${path}.source_backtest_id`),
    observability:
      observability === null
        ? null
        : {
            turnover_exposed: boolean(
              observability.turnover_exposed,
              `${path}.observability.turnover_exposed`,
            ),
            position_count_exposed: boolean(
              observability.position_count_exposed,
              `${path}.observability.position_count_exposed`,
            ),
          },
    result_role: requireLiteral(item.result_role, expectedRole, `${path}.result_role`),
    selection_eligible: requireLiteral(
      item.selection_eligible,
      expectedSelection,
      `${path}.selection_eligible`,
    ),
    used_for_selection: requireLiteral(
      item.used_for_selection,
      expectedSelection,
      `${path}.used_for_selection`,
    ),
    test_data_access: requireLiteral(
      item.test_data_access,
      expectedAccess,
      `${path}.test_data_access`,
    ),
    primary_signal: requireLiteral(item.primary_signal, 'mean', `${path}.primary_signal`),
    receipt_sha256: string(item.receipt_sha256, `${path}.receipt_sha256`),
    signal_receipt_sha256: string(item.signal_receipt_sha256, `${path}.signal_receipt_sha256`),
    provider_receipt_sha256: string(
      item.provider_receipt_sha256,
      `${path}.provider_receipt_sha256`,
    ),
    backtest_code_sha256: string(item.backtest_code_sha256, `${path}.backtest_code_sha256`),
    analysis_lock_sha256: optionalString(
      item.analysis_lock_sha256,
      `${path}.analysis_lock_sha256`,
    ),
    strategy: {
      topk: requireLiteral(strategy.topk, historicalTop3 ? 3 : 50, `${path}.strategy.topk`),
      n_drop: requireLiteral(strategy.n_drop, historicalTop3 ? 1 : 5, `${path}.strategy.n_drop`),
      hold_thresh: requireLiteral(strategy.hold_thresh, 5, `${path}.strategy.hold_thresh`),
      method_sell: requireLiteral(strategy.method_sell, 'bottom', `${path}.strategy.method_sell`),
      method_buy: requireLiteral(strategy.method_buy, 'top', `${path}.strategy.method_buy`),
      only_tradable: requireLiteral(strategy.only_tradable, false, `${path}.strategy.only_tradable`),
      forbid_all_trade_at_limit: requireLiteral(
        strategy.forbid_all_trade_at_limit,
        true,
        `${path}.strategy.forbid_all_trade_at_limit`,
      ),
    },
    execution: {
      account: number(execution.account, `${path}.execution.account`),
      benchmark: requireLiteral(execution.benchmark, 'SH000300', `${path}.execution.benchmark`),
      delay_execution: requireLiteral(
        execution.delay_execution,
        true,
        `${path}.execution.delay_execution`,
      ),
      deal_price: requireLiteral(execution.deal_price, 'open', `${path}.execution.deal_price`),
      open_cost: number(execution.open_cost, `${path}.execution.open_cost`),
      close_cost: number(execution.close_cost, `${path}.execution.close_cost`),
      min_cost: number(execution.min_cost, `${path}.execution.min_cost`),
      limit_threshold: number(execution.limit_threshold, `${path}.execution.limit_threshold`),
    },
    support: {
      sessions: number(support.sessions, `${path}.support.sessions`),
      signal_rows: number(support.signal_rows, `${path}.support.signal_rows`),
      signal_cross_sections: optionalNumber(
        support.signal_cross_sections,
        `${path}.support.signal_cross_sections`,
      ),
      actual_start: optionalString(support.actual_start, `${path}.support.actual_start`),
      actual_end: optionalString(support.actual_end, `${path}.support.actual_end`),
      candidate_min: optionalNumber(support.candidate_min, `${path}.support.candidate_min`),
      candidate_median: optionalNumber(
        support.candidate_median,
        `${path}.support.candidate_median`,
      ),
      candidate_max: optionalNumber(support.candidate_max, `${path}.support.candidate_max`),
    },
    metrics: {
      mean: parseOfficialMetrics(metrics.mean, `${path}.metrics.mean`),
      last: parseOfficialMetrics(metrics.last, `${path}.metrics.last`),
      max: parseOfficialMetrics(metrics.max, `${path}.metrics.max`),
      min: parseOfficialMetrics(metrics.min, `${path}.metrics.min`),
    },
    qlib: {
      version: string(qlib.version, `${path}.qlib.version`),
      metadata_sha256: string(qlib.metadata_sha256, `${path}.qlib.metadata_sha256`),
      record_sha256: string(qlib.record_sha256, `${path}.qlib.record_sha256`),
      source_tree_sha256: string(qlib.source_tree_sha256, `${path}.qlib.source_tree_sha256`),
    },
    curve_semantics: {
      official: string(semantics.official, `${path}.curve_semantics.official`),
      derived: string(semantics.derived, `${path}.curve_semantics.derived`),
    },
    deviations: strings(item.deviations, `${path}.deviations`),
  }
}

const parseHistoricalBacktestEnvelope = (
  value: unknown,
): { available: boolean; backtests: HistoricalBacktest[] } => {
  const item = object(value, 'historical_backtests')
  const available = boolean(item.available, 'historical_backtests.available')
  const entries = array(item.backtests, 'historical_backtests.backtests')
  if (!available && entries.length === 0) return { available: false, backtests: [] }
  const legacy = entries.every((entry, index) =>
    object(entry, `historical_backtests.backtests[${index}]`).strategy_variant_id === undefined,
  )
  const matrix = entries.length === 24
  const officialV3 = entries.length === 8
  if (
    !available ||
    (legacy ? ![1, 2].includes(entries.length) : ![4, 8, 24].includes(entries.length))
  ) {
    throw new ApiContractError('historical_backtests 可用状态与封存条目不一致')
  }
  const backtests = entries.map((entry, index) =>
    parseHistoricalBacktest(entry, `historical_backtests.backtests[${index}]`),
  )
  const pairs = backtests.map(
    (entry) => `${entry.model_cell_id}:${entry.evaluation_split}:${entry.strategy_variant_id}`,
  )
  if (new Set(pairs).size !== backtests.length) {
    throw new ApiContractError('historical_backtests 分区与组合变体重复')
  }
  if (!legacy) {
    const models = matrix
      ? [
          'small-zero-shot',
          'small-official-ft',
          'small-strict-pit',
          'base-zero-shot',
          'base-official-ft',
          'base-strict-pit',
        ]
      : officialV3
        ? ['small-zero-shot', 'small-official-ft', 'base-zero-shot', 'base-official-ft']
        : ['small-official-ft']
    const splits = officialV3
      ? ['test_viewed_official_v3']
      : ['validation_2025', 'test_viewed_2026']
    const expectedPairs = new Set(
      models.flatMap((model) =>
        splits.flatMap((split) =>
          ['official_top50', 'historical_top3'].map(
            (variant) => `${model}:${split}:${variant}`,
          ),
        ),
      ),
    )
    if (pairs.some((pair) => !expectedPairs.has(pair))) {
      throw new ApiContractError('historical_backtests 不是完整的 2×2 封存矩阵')
    }
    const comparisonGroup = matrix
      ? 'six-model-top50-top3-v1'
      : officialV3
        ? 'official-split-v3-top50-top3-v1'
        : 'top50-vs-top3-v1'
    if (backtests.some((entry) => entry.comparison_group_id !== comparisonGroup)) {
      throw new ApiContractError('historical_backtests comparison_group_id 不符合封存契约')
    }
    for (const top3 of backtests.filter(
      (entry) => entry.strategy_variant_id === 'historical_top3',
    )) {
      const source = backtests.find(
        (entry) =>
          entry.evaluation_split === top3.evaluation_split &&
          entry.model_cell_id === top3.model_cell_id &&
          entry.strategy_variant_id === 'official_top50',
      )
      if (top3.source_backtest_id !== source?.id) {
        throw new ApiContractError('historical_backtests Top3 源回测身份不匹配')
      }
    }
  }
  return {
    available: true,
    backtests,
  }
}

const parseHistoricalSeries = (value: unknown): HistoricalBacktestPoint[] => {
  const item = object(value, 'historical_series')
  if (item.signal !== 'mean') throw new ApiContractError('历史曲线必须固定使用 mean 主信号')
  return array(item.points, 'historical_series.points').map((point, index) => {
    const row = object(point, `historical_series.points[${index}]`)
    return {
      session: string(row.session, `historical_series.points[${index}].session`),
      strategy: number(row.strategy, `historical_series.points[${index}].strategy`),
      benchmark: number(row.benchmark, `historical_series.points[${index}].benchmark`),
      excess: number(row.excess, `historical_series.points[${index}].excess`),
      strategy_nav: number(row.strategy_nav, `historical_series.points[${index}].strategy_nav`),
      benchmark_nav: number(row.benchmark_nav, `historical_series.points[${index}].benchmark_nav`),
      turnover: optionalNumber(row.turnover, `historical_series.points[${index}].turnover`),
      position_count: optionalNumber(
        row.position_count,
        `historical_series.points[${index}].position_count`,
      ),
    }
  })
}

const parseCrossModelComparison = (value: unknown): CrossModelComparison => {
  const item = object(value, 'cross_model_comparison')
  const available = boolean(item.available, 'cross_model_comparison.available')
  if (!available) return { available: false, id: null, protocol: null, models: [] }
  const protocol = object(item.protocol, 'cross_model_comparison.protocol')
  const models = array(item.models, 'cross_model_comparison.models').map((rawModel, index) => {
    const modelPath = `cross_model_comparison.models[${index}]`
    const model = object(rawModel, modelPath)
    const input = object(model.input, `${modelPath}.input`)
    const common = object(model.common_metrics, `${modelPath}.common_metrics`)
    const metric = (raw: Record<string, unknown>, key: string) => optionalNumber(raw[key], `${modelPath}.${key}`)
    return {
      id: string(model.id, `${modelPath}.id`),
      family: enumValue(model.family, ['itransformer_b2', 'kronos_base'], `${modelPath}.family`),
      label: string(model.label, `${modelPath}.label`),
      input: {
        description: string(input.description, `${modelPath}.input.description`),
        lookback_sessions: number(input.lookback_sessions, `${modelPath}.input.lookback_sessions`),
        features: strings(input.features, `${modelPath}.input.features`),
      },
      checkpoint_sha256: string(model.checkpoint_sha256, `${modelPath}.checkpoint_sha256`),
      common_metrics: {
        rank_ic: metric(common, 'rank_ic'), pearson_ic: metric(common, 'pearson_ic'), icir: metric(common, 'icir'),
        mae: metric(common, 'mae'), rmse: metric(common, 'rmse'), coverage: metric(common, 'coverage'),
      },
      native_metrics: model.native_metrics === undefined || model.native_metrics === null ? undefined : Object.fromEntries(Object.entries(object(model.native_metrics, `${modelPath}.native_metrics`)).map(([key, candidate]) => [key, candidate === null || typeof candidate === 'string' ? candidate : number(candidate, `${modelPath}.native_metrics.${key}`)])),
      strategies: array(model.strategies, `${modelPath}.strategies`).map((rawStrategy, strategyIndex) => {
        const path = `${modelPath}.strategies[${strategyIndex}]`
        const strategy = object(rawStrategy, path)
        const metrics = object(strategy.metrics, `${path}.metrics`)
        const holdingsRaw = strategy.holdings === undefined || strategy.holdings === null ? null : object(strategy.holdings, `${path}.holdings`)
        return {
          id: string(strategy.id, `${path}.id`), label: string(strategy.label, `${path}.label`),
          topk: (() => {
            const candidate = number(strategy.topk, `${path}.topk`)
            if (candidate !== 1 && candidate !== 3 && candidate !== 50) {
              throw new ApiContractError(`${path}.topk 的值不受支持`)
            }
            return candidate as 1 | 3 | 50
          })(),
          metrics: {
            total_return_with_cost: optionalNumber(metrics.total_return_with_cost, `${path}.metrics.total_return_with_cost`),
            benchmark_return: optionalNumber(metrics.benchmark_return, `${path}.metrics.benchmark_return`),
            excess_return_with_cost: optionalNumber(metrics.excess_return_with_cost, `${path}.metrics.excess_return_with_cost`),
            information_ratio_with_cost: optionalNumber(metrics.information_ratio_with_cost, `${path}.metrics.information_ratio_with_cost`),
            max_drawdown_with_cost: optionalNumber(metrics.max_drawdown_with_cost, `${path}.metrics.max_drawdown_with_cost`),
            turnover_mean: optionalNumber(metrics.turnover_mean, `${path}.metrics.turnover_mean`),
          },
          series: array(strategy.series, `${path}.series`).map((rawPoint, pointIndex) => {
            const point = object(rawPoint, `${path}.series[${pointIndex}]`)
            return { session: string(point.session, `${path}.series[${pointIndex}].session`), strategy: number(point.strategy, `${path}.series[${pointIndex}].strategy`), benchmark: number(point.benchmark, `${path}.series[${pointIndex}].benchmark`), excess: optionalNumber(point.excess, `${path}.series[${pointIndex}].excess`) ?? 0, strategy_nav: optionalNumber(point.strategy_nav, `${path}.series[${pointIndex}].strategy_nav`) ?? 1, benchmark_nav: optionalNumber(point.benchmark_nav, `${path}.series[${pointIndex}].benchmark_nav`) ?? 1 }
          }),
          holdings: holdingsRaw === null ? null : {
            session: string(holdingsRaw.session, `${path}.holdings.session`),
            receipt_sha256: optionalString(holdingsRaw.receipt_sha256, `${path}.holdings.receipt_sha256`),
            items: array(holdingsRaw.items, `${path}.holdings.items`).map((rawHolding, holdingIndex) => { const holding = object(rawHolding, `${path}.holdings.items[${holdingIndex}]`); return { instrument: string(holding.instrument, `${path}.holdings.items[${holdingIndex}].instrument`), weight: number(holding.weight, `${path}.holdings.items[${holdingIndex}].weight`), amount: optionalNumber(holding.amount, `${path}.holdings.items[${holdingIndex}].amount`), value: optionalNumber(holding.value, `${path}.holdings.items[${holdingIndex}].value`) } }),
          },
        }
      }),
    }
  })
  return {
    available: true, id: optionalString(item.id, 'cross_model_comparison.id'),
    protocol: { id: string(protocol.id, 'cross_model_comparison.protocol.id'), label: string(protocol.label, 'cross_model_comparison.protocol.label'), universe: string(protocol.universe, 'cross_model_comparison.protocol.universe'), frequency: string(protocol.frequency, 'cross_model_comparison.protocol.frequency'), signal_start: string(protocol.signal_start, 'cross_model_comparison.protocol.signal_start'), signal_end: string(protocol.signal_end, 'cross_model_comparison.protocol.signal_end'), execution_start: string(protocol.execution_start, 'cross_model_comparison.protocol.execution_start'), execution_end: string(protocol.execution_end, 'cross_model_comparison.protocol.execution_end'), anchor_set_sha256: string(protocol.anchor_set_sha256, 'cross_model_comparison.protocol.anchor_set_sha256'), label_definition: string(protocol.label_definition, 'cross_model_comparison.protocol.label_definition'), viewed: boolean(protocol.viewed, 'cross_model_comparison.protocol.viewed') },
    models,
  }
}

const parseHistoricalHoldings = (value: unknown): HistoricalHoldingsSnapshot => {
  const item = object(value, 'historical_holdings')
  const source = object(item.source, 'historical_holdings.source')
  const holdings = array(item.holdings, 'historical_holdings.holdings').map(
    (holding, index) => {
      const row = object(holding, `historical_holdings.holdings[${index}]`)
      return {
        instrument: string(
          row.instrument,
          `historical_holdings.holdings[${index}].instrument`,
        ),
        weight: number(row.weight, `historical_holdings.holdings[${index}].weight`),
        amount: number(row.amount, `historical_holdings.holdings[${index}].amount`),
        value: number(row.value, `historical_holdings.holdings[${index}].value`),
      }
    },
  )
  const sessions = strings(item.sessions, 'historical_holdings.sessions')
  const defaultSession = string(
    item.default_session,
    'historical_holdings.default_session',
  )
  const selectedSession = string(
    item.selected_session,
    'historical_holdings.selected_session',
  )
  if (
    sessions.length === 0 ||
    new Set(sessions).size !== sessions.length ||
    [...sessions].sort().some((session, index) => session !== sessions[index]) ||
    !sessions.includes(defaultSession) ||
    !sessions.includes(selectedSession) ||
    new Set(holdings.map((holding) => holding.instrument)).size !== holdings.length ||
    holdings.some(
      (holding) =>
        holding.instrument.length === 0 ||
        holding.amount < 0 ||
        holding.weight < 0 ||
        holding.weight > 1 ||
        holding.value < 0,
    ) ||
    item.signal !== 'mean' ||
    typeof item.empty !== 'boolean' ||
    item.empty !== (holdings.length === 0)
  ) {
    throw new ApiContractError('historical_holdings 日期或持仓身份不符合封存契约')
  }
  return {
    backtest_id: string(item.backtest_id, 'historical_holdings.backtest_id'),
    available: requireLiteralBoolean(
      item.available,
      true,
      'historical_holdings.available',
    ),
    signal: 'mean',
    empty: item.empty,
    sessions,
    default_session: defaultSession,
    selected_session: selectedSession,
    source: {
      artifact_sha256: string(
        source.artifact_sha256,
        'historical_holdings.source.artifact_sha256',
      ),
      receipt_sha256: string(
        source.receipt_sha256,
        'historical_holdings.source.receipt_sha256',
      ),
      backtest_receipt_sha256: string(
        source.backtest_receipt_sha256,
        'historical_holdings.source.backtest_receipt_sha256',
      ),
    },
    holdings,
  }
}

const requireLiteralBoolean = <T extends boolean>(
  value: unknown,
  expected: T,
  path: string,
): T => {
  if (value !== expected) throw new ApiContractError(`${path} 不符合封存契约`)
  return expected
}

const parseReceipt = (value: unknown, requestedProfile: ExecutionProfile): SubmitJobReceipt => {
  const item = object(value, 'receipt')
  const nestedJob = item.job === undefined ? null : object(item.job, 'receipt.job')
  return {
    job_id: string(item.job_id ?? item.id ?? nestedJob?.id, 'receipt.id'),
    coalesced:
      item.created === undefined
        ? optionalBoolean(item.coalesced, false, 'receipt.coalesced')
        : !boolean(item.created, 'receipt.created'),
    execution_profile:
      item.execution_profile === undefined && nestedJob?.execution_profile === undefined
        ? requestedProfile
        : parseExecutionProfile(
            item.execution_profile ?? nestedJob?.execution_profile,
            'receipt.execution_profile',
          ),
  }
}

const requestJson = async (path: string, init: RequestInit = {}): Promise<unknown> => {
  const response = await fetch(path, {
    ...init,
    headers: { Accept: 'application/json', ...init.headers },
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const payload = object(await response.json(), 'error')
      if (typeof payload.detail === 'string') detail = payload.detail
    } catch {
      // Keep the HTTP status text when an error body is not JSON.
    }
    throw new ApiRequestError(detail || `HTTP ${response.status}`, response.status)
  }
  return response.json()
}

const optionalJson = async (path: string, signal?: AbortSignal): Promise<unknown | null> => {
  try {
    return await requestJson(path, { signal })
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) return null
    throw error
  }
}

const optionalServiceJson = async (
  path: string,
  signal?: AbortSignal,
): Promise<unknown | null> => {
  try {
    return await requestJson(path, { signal })
  } catch (error) {
    if (error instanceof ApiRequestError && (error.status === 404 || error.status === 503)) {
      return null
    }
    throw error
  }
}

const collection = (value: unknown, keys: string[], path: string): unknown[] => {
  if (Array.isArray(value)) return value
  const envelope = object(value, path)
  for (const key of keys) {
    if (Array.isArray(envelope[key])) return envelope[key] as unknown[]
  }
  throw new ApiContractError(`${path} 缺少数组字段 ${keys.join(' / ')}`)
}

export const createApiClient = (): ApiClient => ({
  async getSnapshot(signal) {
    const [systemRaw, jobsRaw, runRaw, runsRaw, researchRaw, backtestsRaw, comparisonRaw, paperRaw] = await Promise.all([
      requestJson('/api/v1/system/status', { signal }),
      requestJson('/api/v1/jobs', { signal }),
      optionalJson('/api/v1/runs/latest', signal),
      requestJson('/api/v1/runs?limit=10', { signal }),
      optionalServiceJson('/api/v1/research/experiments', signal),
      optionalServiceJson('/api/v1/research/backtests', signal),
      optionalServiceJson('/api/v1/research/comparisons', signal),
      optionalJson('/api/v1/paper/account', signal),
    ])
    const jobItems = collection(jobsRaw, ['items', 'jobs'], 'jobs_response')
    const runItems = collection(runsRaw, ['items', 'runs'], 'runs_response')
    const runs = runItems.map((run, index) => parseRunSummary(run, `runs[${index}]`))
    const researchItems =
      researchRaw === null
        ? []
        : collection(researchRaw, ['items', 'experiments'], 'research_response')
    const researchCatalog = researchItems.map((experiment, index) =>
      parseExperiment(experiment, `research[${index}]`),
    )
    const parsedRun = runRaw === null ? null : parseRun(runRaw)
    const historical =
      backtestsRaw === null
        ? { available: false, backtests: [] }
        : parseHistoricalBacktestEnvelope(backtestsRaw)
    const historicalSeriesPromise = Promise.all(
      historical.backtests.map(async (backtest) => {
        const raw = await optionalServiceJson(
          `/api/v1/research/backtests/${encodeURIComponent(backtest.id)}/series?signal=mean`,
          signal,
        )
        return [backtest.id, raw === null ? [] : parseHistoricalSeries(raw)] as const
      }),
    )
    const [scoresRaw, diffRaw, ordersRaw, navRaw, paperSummaryRaw, historicalSeriesRaw] = await Promise.all([
      parsedRun === null
        ? Promise.resolve(null)
        : optionalJson(`/api/v1/runs/${encodeURIComponent(parsedRun.id)}/scores`, signal),
      parsedRun === null
        ? Promise.resolve(null)
        : optionalJson(`/api/v1/runs/${encodeURIComponent(parsedRun.id)}/diff`, signal),
      paperRaw === null ? Promise.resolve(null) : optionalJson('/api/v1/paper/orders', signal),
      paperRaw === null ? Promise.resolve(null) : optionalJson('/api/v1/paper/nav', signal),
      paperRaw === null ? Promise.resolve(null) : optionalJson('/api/v1/paper/summary', signal),
      historicalSeriesPromise,
    ])

    const embeddedRun = runRaw === null ? null : object(runRaw, 'latest_run')
    const scoreItems =
      scoresRaw !== null
        ? collection(scoresRaw, ['items', 'scores'], 'scores_response')
        : embeddedRun?.scores === undefined
          ? []
          : array(embeddedRun.scores, 'latest_run.scores')
    const scores = scoreItems.map((score, index) => parseScore(score, `scores[${index}]`))
    const orderItems = ordersRaw === null ? [] : collection(ordersRaw, ['items', 'orders'], 'orders_response')
    const orders = orderItems.map((order, index) => parseOrder(order, `orders[${index}]`))
    const navItems = navRaw === null ? [] : collection(navRaw, ['items', 'nav'], 'nav_response')
    const nav = navItems.map((point, index) => parseNav(point, `nav[${index}]`))

    return {
      system: parseSystem(systemRaw),
      jobs: jobItems.map((job, index) => parseJob(job, `jobs[${index}]`)),
      latest_run: runRaw === null ? null : parseRun(runRaw, scores),
      research_catalog: researchCatalog,
      research_catalog_available: researchRaw !== null,
      historical_backtests: historical.backtests,
      historical_backtest_available: historical.available,
      historical_backtest_series: Object.fromEntries(historicalSeriesRaw),
      cross_model_comparison:
        comparisonRaw === null ? { available: false, id: null, protocol: null, models: [] } : parseCrossModelComparison(comparisonRaw),
      runs,
      run_diff: diffRaw === null ? null : parseRunDiff(diffRaw),
      paper: paperRaw === null ? null : parsePaper(paperRaw, orders, nav),
      paper_summary: paperSummaryRaw === null ? null : parsePaperSummary(paperSummaryRaw),
    } satisfies DashboardSnapshot
  },

  async getHistoricalHoldings(backtestId, session, signal) {
    const raw = await optionalJson(
      `/api/v1/research/backtests/${encodeURIComponent(backtestId)}/holdings${session ? `?session=${encodeURIComponent(session)}` : ''}`,
      signal,
    )
    if (raw === null) return null
    const parsed = parseHistoricalHoldings(raw)
    if (parsed.backtest_id !== backtestId || (session && parsed.selected_session !== session)) {
      throw new ApiContractError('historical_holdings 回执身份与请求不一致')
    }
    return parsed
  },

  async submitUpdateInfer(profile, signal) {
    return parseReceipt(
      await requestJson('/api/v1/jobs/update-infer', {
        method: 'POST',
        signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: false, execution_profile: profile }),
      }),
      profile,
    )
  },

  async retryJob(id, signal) {
    const raw = await requestJson(`/api/v1/jobs/${encodeURIComponent(id)}/retry`, {
      method: 'POST',
      signal,
    })
    const item = object(raw, 'receipt')
    const nestedJob = item.job === undefined ? null : object(item.job, 'receipt.job')
    const profile =
      item.execution_profile === undefined && nestedJob?.execution_profile === undefined
        ? 'legacy-yilangliu'
        : parseExecutionProfile(
            item.execution_profile ?? nestedJob?.execution_profile,
            'receipt.execution_profile',
          )
    return parseReceipt(raw, profile)
  },
})
