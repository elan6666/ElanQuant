import type {
  ApiClient,
  DashboardSnapshot,
  ExperimentCell,
  ForecastPoint,
  Job,
  JobEvent,
  NavPoint,
  PaperAccount,
  PaperOrder,
  PaperPosition,
  ResearchRun,
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

const parseSystem = (value: unknown): SystemStatus => {
  const item = object(value, 'system')
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
  'scoring',
  'paper_ledger',
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
    coalesced: optionalBoolean(item.coalesced, false, `${path}.coalesced`),
    events: optionalArray(item.events, `${path}.events`).map((event, index) =>
      parseEvent(event, `${path}.events[${index}]`),
    ),
  }
}

const parseExperiment = (value: unknown, path: string): ExperimentCell => {
  const item = object(value, path)
  return {
    id: string(item.id, `${path}.id`),
    model_size: enumValue(item.model_size, ['small'], `${path}.model_size`),
    track: enumValue(item.track, ['zero_shot', 'official_style', 'strict_pit'], `${path}.track`),
    state: enumValue(item.state, ['pending', 'running', 'passed', 'failed', 'blocked'], `${path}.state`),
    rank_ic: nullableNumber(item.rank_ic, `${path}.rank_ic`),
    pearson_ic: nullableNumber(item.pearson_ic, `${path}.pearson_ic`),
    top10_mean_return: nullableNumber(item.top10_mean_return, `${path}.top10_mean_return`),
    model_hash: nullableString(item.model_hash, `${path}.model_hash`),
    receipt: nullableString(item.receipt, `${path}.receipt`),
    note: nullableString(item.note, `${path}.note`),
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
    coverage: optionalNumber(item.coverage, `${path}.coverage`),
    eligible: boolean(item.eligible, `${path}.eligible`),
    explanation: optionalString(item.explanation, `${path}.explanation`) ?? '',
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
    warnings: optionalStrings(item.warnings, 'latest_run.warnings'),
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

const parseReceipt = (value: unknown): SubmitJobReceipt => {
  const item = object(value, 'receipt')
  const nestedJob = item.job === undefined ? null : object(item.job, 'receipt.job')
  return {
    job_id: string(item.job_id ?? item.id ?? nestedJob?.id, 'receipt.id'),
    coalesced:
      item.created === undefined
        ? optionalBoolean(item.coalesced, false, 'receipt.coalesced')
        : !boolean(item.created, 'receipt.created'),
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
    const [systemRaw, jobsRaw, runRaw, paperRaw] = await Promise.all([
      requestJson('/api/v1/system/status', { signal }),
      requestJson('/api/v1/jobs', { signal }),
      optionalJson('/api/v1/runs/latest', signal),
      optionalJson('/api/v1/paper/account', signal),
    ])
    const jobItems = collection(jobsRaw, ['items', 'jobs'], 'jobs_response')
    const parsedRun = runRaw === null ? null : parseRun(runRaw)
    const [scoresRaw, ordersRaw, navRaw] = await Promise.all([
      parsedRun === null
        ? Promise.resolve(null)
        : optionalJson(`/api/v1/runs/${encodeURIComponent(parsedRun.id)}/scores`, signal),
      paperRaw === null ? Promise.resolve(null) : optionalJson('/api/v1/paper/orders', signal),
      paperRaw === null ? Promise.resolve(null) : optionalJson('/api/v1/paper/nav', signal),
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
      paper: paperRaw === null ? null : parsePaper(paperRaw, orders, nav),
    } satisfies DashboardSnapshot
  },

  async submitUpdateInfer(signal) {
    return parseReceipt(
      await requestJson('/api/v1/jobs/update-infer', {
        method: 'POST',
        signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force: false }),
      }),
    )
  },

  async retryJob(id, signal) {
    return parseReceipt(
      await requestJson(`/api/v1/jobs/${encodeURIComponent(id)}/retry`, {
        method: 'POST',
        signal,
      }),
    )
  },
})
