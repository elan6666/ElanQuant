import { useEffect, useId, useRef, useState } from 'react'

import { Badge } from '../components/Badge'
import { EmptyState } from '../components/EmptyState'
import { MetricHelp } from '../components/MetricHelp'
import { formatMoney, formatPercent, shortHash } from '../format'
import type {
  HistoricalBacktest,
  HistoricalBacktestPoint,
  HistoricalHoldingsSnapshot,
  HistoricalModelCell,
  HistoricalStrategyVariant,
  OfficialDemoSignal,
} from '../types'

const signals: { id: OfficialDemoSignal; label: string; detail: string }[] = [
  { id: 'mean', label: '未来均值', detail: '预先指定的主信号' },
  { id: 'last', label: '第10日', detail: '辅助描述，不参与选优' },
  { id: 'max', label: '未来最大', detail: '辅助描述，不参与选优' },
  { id: 'min', label: '未来最小', detail: '辅助描述，不参与选优' },
]

const modelCells: { id: HistoricalModelCell; label: string; detail: string }[] = [
  { id: 'small-zero-shot', label: 'Small · Zero-shot', detail: '官方预训练权重' },
  { id: 'small-official-ft', label: 'Small · Official FT', detail: '作者风格微调' },
  { id: 'base-zero-shot', label: 'Base · Zero-shot', detail: '官方预训练权重' },
  { id: 'base-official-ft', label: 'Base · Official FT', detail: '作者风格微调' },
]
const publicModelIds = new Set<HistoricalModelCell>(modelCells.map((model) => model.id))

const deviationTranslations: Record<string, string> = {
  "Uses the admitted extended validation_2025 split, not the author's fixed dates.":
    '使用准入后的扩展版 2025 验证集，而不是作者 Demo 的固定时间窗。',
  'Uses the admitted opened test_viewed_2026 split for a frozen post-selection evaluation.':
    '使用未参与训练或 checkpoint 选择的 2026 测试集；结果已开封，只能评估冻结版本。',
  'Candidate eligibility uses only T-known membership/data with a complete prior 90-global-session context; forecast timestamps use the next ten global exchange sessions without reading future symbol rows.':
    '候选资格只使用 T 日已知成分与数据，要求过去 90 个全市场交易日完整；未来时间戳固定为下一个 10 个全市场交易日，不读取未来个股行。',
  "Uses dynamic PIT CSI300 membership and provider data, not the author's Qlib bundle.":
    '使用动态 PIT 沪深300与本项目准入数据，而不是作者的 Qlib 数据包。',
  'Uses true provider amount instead of OHLC-average times volume.':
    '成交额使用供应商真值，而不是 OHLC 均价乘成交量的近似值。',
  'Pins pyqlib 0.9.7 because the Kronos repository does not pin a Qlib version.':
    '作者仓库没有固定 Qlib 版本；本项目为审计与复算固定为 pyqlib 0.9.7。',
  'Adds seed 100 and machine-readable receipts for reproducibility.':
    '新增 seed=100 与机器可读回执，保证同一证据可以复算。',
  'Provider factor=1 leaves corporate-action handling as a disclosed limitation.':
    '供应商复权因子固定为 1；公司行动处理仍是已披露的数据限制。',
  'Corrected signal candidates do not depend on future symbol membership or future symbol-row availability.':
    '已修正信号候选集，不再依赖未来成分资格或未来个股行是否存在。',
}

function translateDeviation(deviation: string) {
  return deviationTranslations[deviation] ?? deviation
}

export function HistoricalBacktestPage({
  backtests,
  available,
  seriesById,
  onLoadHoldings,
}: {
  backtests: HistoricalBacktest[]
  available: boolean
  seriesById: Record<string, HistoricalBacktestPoint[]>
  onLoadHoldings: (
    backtestId: string,
    session?: string,
    signal?: AbortSignal,
  ) => Promise<HistoricalHoldingsSnapshot | null>
}) {
  const [selectedSplit, setSelectedSplit] = useState<
    'validation_2025' | 'test_viewed_2026'
  >('test_viewed_2026')
  const [selectedStrategy, setSelectedStrategy] = useState<HistoricalStrategyVariant>(
    'official_top50',
  )
  const [selectedModel, setSelectedModel] = useState<HistoricalModelCell>('small-official-ft')
  const publicBacktests = backtests.filter((entry) => publicModelIds.has(entry.model_cell_id))
  const activeModel = publicBacktests.some((entry) => entry.model_cell_id === selectedModel)
    ? selectedModel
    : (publicBacktests[0]?.model_cell_id ?? 'small-official-ft')
  const modelBacktests = publicBacktests.filter((entry) => entry.model_cell_id === activeModel)
  const activeSplit = modelBacktests.some((entry) => entry.evaluation_split === selectedSplit)
    ? selectedSplit
    : 'validation_2025'
  const splitBacktests = modelBacktests.filter((entry) => entry.evaluation_split === activeSplit)
  const backtest =
    splitBacktests.find((entry) => entry.strategy_variant_id === selectedStrategy) ??
    splitBacktests.find((entry) => entry.strategy_variant_id === 'official_top50') ??
    null
  const officialBacktest = splitBacktests.find(
    (entry) => entry.strategy_variant_id === 'official_top50',
  )
  const top3Backtest = splitBacktests.find(
    (entry) => entry.strategy_variant_id === 'historical_top3',
  )
  const officialSeries = officialBacktest ? (seriesById[officialBacktest.id] ?? []) : []
  const top3Series = top3Backtest ? (seriesById[top3Backtest.id] ?? []) : []
  return (
    <>
      <header className="page-heading page-heading--split backtest-heading">
        <div>
          <span className="eyebrow">04 / Official-demo method</span>
          <h1>历史组合 <span className="title-phrase">对照回测</span></h1>
          <p>四个公开模型版本分别使用自己的预测信号，交叉查看两个评估期与 Top50 / Top3 组合。结果只作研究比较，不自动选模或改动在线账户。</p>
        </div>
        <div className="identity-card identity-card--backtest">
          <span>轨道身份</span>
          <strong>4 MODELS × 2 SPLITS × 2 PORTFOLIOS</strong>
          <small>历史 Qlib 模拟 · 只读回执 · 不生成在线订单</small>
        </div>
      </header>

      <section className="track-separation" aria-label="双轨隔离说明">
        <div><span>在线产品</span><strong>在线 Top3 模拟账户</strong><small>手动按钮 · T日冻结 · T+1执行/拒绝</small></div>
        <b aria-hidden="true">≠</b>
        <div><span>历史研究</span><strong>Qlib Top3 组合变体</strong><small>开封后探索性敏感性分析 · Top3 / Drop1 / Hold5</small></div>
        <p>历史 Top3 不等同在线 Top3，不共享订单、持仓、净值或执行逻辑；本页数字只来自只读封存回执。</p>
      </section>

      {!available || !backtest ? (
        <EmptyState
          title="官方对齐回测正在服务器生成"
          description="Top3 仍可正常使用。只有标准化信号、Qlib回测和哈希回执全部通过后，本页才会展示结果。"
        />
      ) : (
        <>
          <section className="historical-model-picker" aria-labelledby="historical-model-heading">
            <div className="section-heading">
              <div><span className="eyebrow">Model matrix</span><h2 id="historical-model-heading">选择模型版本</h2></div>
              <small>每格均使用自身 checkpoint 生成的标准化空间信号</small>
            </div>
            <div className="historical-model-cards" role="group" aria-label="历史回测模型版本">
              {modelCells.map((model) => {
                const present = publicBacktests.some((entry) => entry.model_cell_id === model.id)
                const item = publicBacktests.find(
                  (entry) =>
                    entry.model_cell_id === model.id &&
                    entry.evaluation_split === activeSplit &&
                    entry.strategy_variant_id === selectedStrategy,
                )
                return (
                  <button
                    type="button"
                    className={activeModel === model.id ? 'historical-model-card is-active' : 'historical-model-card'}
                    aria-pressed={activeModel === model.id}
                    disabled={!present}
                    key={model.id}
                    onClick={() => setSelectedModel(model.id)}
                  >
                    <strong>{model.label}</strong>
                    <small>{model.detail}</small>
                    <b>{item ? `${formatPercent(item.metrics.mean.total_return_with_cost)} 含费累计` : '未发布'}</b>
                  </button>
                )
              })}
            </div>
            <p className="historical-strategy-disclosure">Small / Base 与两种公开对照轨互相独立；页面不会把某一格的信号或收益复制给其他模型。</p>
          </section>
          <div className="backtest-split-tabs" role="group" aria-label="历史回测评估分区">
            {([
              ['test_viewed_2026', '2026 已开封样本外诊断（已修正）'],
              ['validation_2025', '2025 训练验证 / checkpoint 选择'],
            ] as const).map(([split, label]) => {
              const present = modelBacktests.some((entry) => entry.evaluation_split === split)
              return (
                <button
                  type="button"
                  aria-pressed={backtest.evaluation_split === split}
                  disabled={!present}
                  key={split}
                  onClick={() => setSelectedSplit(split)}
                >
                  {label}
                </button>
              )
            })}
          </div>
          <section className="historical-strategy-picker" aria-labelledby="historical-strategy-heading">
            <div className="section-heading">
              <div><span className="eyebrow">Portfolio sensitivity</span><h2 id="historical-strategy-heading">查看组合明细</h2></div>
              <small>默认展示官方对齐 Top50</small>
            </div>
            <div className="historical-strategy-cards" role="group" aria-label="历史组合明细">
              {([
                ['official_top50', '官方对齐 Top50', 'Top50 / Drop5 / Hold5', '封存方法基线'],
                ['historical_top3', '历史 Qlib Top3', 'Top3 / Drop1 / Hold5', '开封后探索性敏感性分析'],
              ] as const).map(([variant, label, params, note]) => {
                const item = splitBacktests.find((entry) => entry.strategy_variant_id === variant)
                const active = backtest.strategy_variant_id === variant
                return (
                  <button
                    type="button"
                    className={active ? 'historical-strategy-card is-active' : 'historical-strategy-card'}
                    aria-pressed={active}
                    disabled={!item}
                    key={variant}
                    onClick={() => setSelectedStrategy(variant)}
                  >
                    <span>{variant === 'official_top50' ? '官方方法' : '组合变体'}</span>
                    <strong>{label}</strong>
                    <small>{params}</small>
                    <em>{note}</em>
                    {item ? <b>{formatPercent(item.metrics.mean.total_return_with_cost)} 累计收益</b> : <b>未发布</b>}
                  </button>
                )
              })}
            </div>
            <p className="historical-strategy-disclosure">历史 Top3 不用于选模，不用于改动已冻结参数，也不等同在线 Top3 模拟账户。</p>
          </section>
          <BacktestEvidence
            key={backtest.id}
            backtest={backtest}
            officialSeries={officialSeries}
            top3Series={top3Series}
            onLoadHoldings={onLoadHoldings}
          />
        </>
      )}
    </>
  )
}

function BacktestEvidence({
  backtest,
  officialSeries,
  top3Series,
  onLoadHoldings,
}: {
  backtest: HistoricalBacktest
  officialSeries: HistoricalBacktestPoint[]
  top3Series: HistoricalBacktestPoint[]
  onLoadHoldings: (
    backtestId: string,
    session?: string,
    signal?: AbortSignal,
  ) => Promise<HistoricalHoldingsSnapshot | null>
}) {
  const primary = backtest.metrics.mean
  const finalTest = backtest.evaluation_split === 'test_viewed_2026'
  const historicalTop3 = backtest.strategy_variant_id === 'historical_top3'
  const selectedSeries = historicalTop3 ? top3Series : officialSeries
  const positionCounts = selectedSeries
    .map((point) => point.position_count)
    .filter((value): value is number => value !== null && value !== undefined)
    .sort((left, right) => left - right)
  const positionCountMidpoint = Math.floor(positionCounts.length / 2)
  const positionCountMedian = positionCounts.length % 2
    ? positionCounts[positionCountMidpoint]
    : ((positionCounts[positionCountMidpoint - 1] ?? 0) + (positionCounts[positionCountMidpoint] ?? 0)) / 2
  const positionCountSummary = positionCounts.length
    ? `${positionCounts[0]} – ${positionCounts.at(-1)} 只，中位数 ${positionCountMedian}`
    : '会因可交易性与涨跌停偏离 3 只；逐日数值尚未公开'
  return (
    <>
      <div className="official-boundary-banner">
        <Badge tone="success">
          {historicalTop3
            ? 'POST-HOC / NON-SELECTION'
            : finalTest
              ? 'CORRECTED / OOS 2026 / OPENED'
              : 'TRAINING VALIDATION / 2025'}
        </Badge>
        <strong>
          {historicalTop3
            ? finalTest
              ? '2026 窗口已开封；这是组合层的事后诊断，不用于选模'
              : '2025 已在查看后构建；这是事后敏感性分析，不用于选模'
            : finalTest
              ? '已修正未来成分/缺行条件；窗口已开封，只作样本外诊断，不是新的盲测'
              : '这一段参与 validation loss 和 best checkpoint 选择，不是最终测试'}
        </strong>
        <span>标准化分数不是预测收益率；历史 Qlib Top3 不等同在线 Top3 账户。</span>
      </div>

      <section className="metric-grid backtest-metrics">
        <div className={`metric ${primary.total_return_with_cost >= 0 ? 'metric--positive' : 'metric--negative'}`}><span>策略累计收益（含费）</span><strong>{formatPercent(primary.total_return_with_cost)}</strong><small>官方算术累计曲线口径</small></div>
        <div className="metric"><span>沪深300同期</span><strong>{formatPercent(primary.benchmark_return)}</strong><small>SH000300</small></div>
        <div className={`metric ${primary.excess_return_with_cost >= 0 ? 'metric--positive' : 'metric--negative'}`}><span>含费超额</span><strong>{formatPercent(primary.excess_return_with_cost)}</strong><small>策略 − 基准 − 成本</small></div>
        <div className="metric metric--negative"><span>最大回撤</span><strong>{formatPercent(primary.max_drawdown_with_cost)}</strong><small>mean 主信号</small></div>
      </section>

      <MetricHelp
        items={[
          { term: '累计收益', description: '评估期内每日策略收益的算术累加；不是模拟账户净值。' },
          { term: '沪深300同期', description: '与策略相同评估区间内，沪深300每日收益的算术累加。' },
          { term: '含费超额', description: '策略累计收益减去基准累计收益，并计入交易成本。' },
          { term: '最大回撤', description: '累计收益曲线从历史峰值到之后最低点的最大跌幅。' },
          { term: '信息比率', description: '含费超额收益相对其波动的比率，用于比较风险调整后的表现。' },
          { term: '日均换手', description: '每日成交金额相对组合资产的平均比例。' },
        ]}
      />

      <section className="content-section backtest-chart-section">
        <div className="section-heading">
          <div><span className="eyebrow">Primary signal / mean</span><h2>{finalTest ? '2026 已开封样本外诊断曲线' : '2025 训练验证曲线'}</h2></div>
          <span className="count-label">{selectedSeries.length} SESSIONS</span>
        </div>
        <BacktestChart officialPoints={officialSeries} top3Points={top3Series} />
        <div className="chart-legend" aria-label="曲线图例">
          <span className="chart-legend__official">官方对齐 Top50（实线）</span>
          {top3Series.length > 1 ? <span className="chart-legend__top3">历史 Qlib Top3（长虚线）</span> : null}
          <span className="chart-legend__benchmark">沪深300（短虚线）</span>
          <small>与官方 qlib_test.py 一致：这里是每日收益算术累加，不把它称为账户NAV。</small>
        </div>
      </section>

      <HistoricalHoldingsViewer backtest={backtest} onLoad={onLoadHoldings} />

      <section className="official-signal-grid" aria-label="四个官方信号">
        {signals.map((signal) => {
          const metric = backtest.metrics[signal.id]
          return (
            <article className={signal.id === 'mean' ? 'official-signal-card is-primary' : 'official-signal-card'} key={signal.id}>
              <div><span>{signal.id.toUpperCase()}</span>{signal.id === 'mean' ? <Badge tone="success">固定主信号</Badge> : null}</div>
              <h2>{signal.label}</h2>
              <p>{signal.detail}</p>
              <dl><div><dt>累计收益</dt><dd>{formatPercent(metric.total_return_with_cost)}</dd></div><div><dt>含费超额</dt><dd>{formatPercent(metric.excess_return_with_cost)}</dd></div><div><dt>信息比率</dt><dd>{metric.information_ratio_with_cost.toFixed(3)}</dd></div><div><dt>最大回撤</dt><dd>{formatPercent(metric.max_drawdown_with_cost)}</dd></div></dl>
            </article>
          )
        })}
      </section>

      <section className="two-column backtest-evidence-grid">
        <div className="content-section">
          <div className="section-heading"><div><span className="eyebrow">Resolved strategy</span><h2>{historicalTop3 ? '历史 Top3 组合参数' : '官方 Demo 执行参数'}</h2></div></div>
          <div className="evidence-list">
            <div><span>持仓 / 每次剔除</span><strong>{backtest.strategy.topk} / {backtest.strategy.n_drop}</strong></div>
            <div><span>最少持有</span><strong>{backtest.strategy.hold_thresh} 个交易日</strong></div>
            <div><span>执行价 / 延迟</span><strong>次日开盘 / 是</strong></div>
            <div><span>假设资金</span><strong>{formatMoney(backtest.execution.account)}</strong></div>
            <div><span>买入 / 卖出成本</span><strong>{formatPercent(backtest.execution.open_cost)} / {formatPercent(backtest.execution.close_cost)}</strong></div>
            <div><span>涨跌停阈值</span><strong>{formatPercent(backtest.execution.limit_threshold)}</strong></div>
            <div><span>日均换手</span><strong>{primary.turnover_mean === null ? '—' : formatPercent(primary.turnover_mean)}</strong></div>
            {historicalTop3 ? <div><span>实际持仓数</span><strong>{positionCountSummary}</strong></div> : null}
            {historicalTop3 ? <div><span>逐日可观察性</span><strong>{backtest.observability?.turnover_exposed && backtest.observability.position_count_exposed ? '换手与持仓数已暴露' : '只展示摘要，局限已披露'}</strong></div> : null}
          </div>
        </div>
        <div className="content-section">
          <div className="section-heading"><div><span className="eyebrow">Evidence identity</span><h2>数据与回执</h2></div></div>
          <div className="evidence-list">
            <div><span>模型格</span><strong>{backtest.model_cell_id}</strong></div>
            <div><span>组合身份</span><strong>{historicalTop3 ? '历史 Qlib Top3' : '官方对齐 Top50'}</strong></div>
            <div><span>执行域</span><strong>历史 Qlib 模拟</strong></div>
            <div><span>Qlib</span><strong>{backtest.qlib.version}</strong></div>
            <div><span>实际区间</span><strong>{backtest.support.actual_start ?? '—'} → {backtest.support.actual_end ?? '—'}</strong></div>
            <div><span>交易日 / 信号行</span><strong>{backtest.support.sessions} / {backtest.support.signal_rows.toLocaleString()}</strong></div>
            <div><span>Backtest receipt</span><code>{shortHash(backtest.receipt_sha256)}</code></div>
            <div><span>Signal receipt</span><code>{shortHash(backtest.signal_receipt_sha256)}</code></div>
            {backtest.analysis_lock_sha256 ? <div><span>Analysis lock</span><code>{shortHash(backtest.analysis_lock_sha256)}</code></div> : null}
            <div><span>Backtest code</span><code>{shortHash(backtest.backtest_code_sha256)}</code></div>
          </div>
        </div>
      </section>

      <section className="method-note method-note--dark backtest-deviations">
        <div className="method-note__index">DEVIATIONS</div>
        <div><h2>对齐的是方法，不伪装成逐字数据复现</h2><ul>{backtest.deviations.map((deviation) => <li key={deviation}>{translateDeviation(deviation)}</li>)}</ul></div>
      </section>
    </>
  )
}

function HistoricalHoldingsViewer({
  backtest,
  onLoad,
}: {
  backtest: HistoricalBacktest
  onLoad: (
    backtestId: string,
    session?: string,
    signal?: AbortSignal,
  ) => Promise<HistoricalHoldingsSnapshot | null>
}) {
  const [snapshot, setSnapshot] = useState<HistoricalHoldingsSnapshot | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'unavailable' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setState('loading')
    void onLoad(backtest.id, undefined, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        if (result === null) {
          setSnapshot(null)
          setState('unavailable')
          return
        }
        setSnapshot(result)
        setState('ready')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setMessage(error instanceof Error ? error.message : '未知错误')
        setState('error')
      })
    return () => {
      controller.abort()
      if (controllerRef.current === controller) controllerRef.current = null
    }
  }, [backtest.id, onLoad])

  const selectSession = (session?: string) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    setState('loading')
    void onLoad(backtest.id, session, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        if (result === null) {
          setSnapshot(null)
          setState('unavailable')
          return
        }
        setSnapshot(result)
        setState('ready')
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setMessage(error instanceof Error ? error.message : '未知错误')
        setState('error')
      })
  }

  return (
    <section className="content-section historical-holdings" aria-labelledby="historical-holdings-heading">
      <div className="section-heading historical-holdings__heading">
        <div><span className="eyebrow">Sealed positions</span><h2 id="historical-holdings-heading">评估期实际持仓</h2></div>
        {snapshot ? (
          <label>
            <span>交易日</span>
            <div className="holdings-session-control">
              <button
                type="button"
                aria-label="上一交易日"
                disabled={state === 'loading' || snapshot.sessions.indexOf(snapshot.selected_session) <= 0}
                onClick={() => selectSession(snapshot.sessions[snapshot.sessions.indexOf(snapshot.selected_session) - 1])}
              >←</button>
              <select
                aria-label="持仓交易日"
                value={snapshot.selected_session}
                disabled={state === 'loading'}
                onChange={(event) => selectSession(event.target.value)}
              >
                {snapshot.sessions.map((session) => <option key={session} value={session}>{session}</option>)}
              </select>
              <button
                type="button"
                aria-label="下一交易日"
                disabled={state === 'loading' || snapshot.sessions.indexOf(snapshot.selected_session) >= snapshot.sessions.length - 1}
                onClick={() => selectSession(snapshot.sessions[snapshot.sessions.indexOf(snapshot.selected_session) + 1])}
              >→</button>
            </div>
          </label>
        ) : null}
      </div>

      {state === 'loading' ? <div className="holdings-state" role="status">正在校验该交易日的封存持仓…</div> : null}
      {state === 'unavailable' ? (
        <EmptyState
          title="该回测没有封存持仓工件"
          description="旧版 Top50 只发布了指标与曲线；页面不会推测或伪造历史持仓。"
        />
      ) : null}
      {state === 'error' ? <div className="holdings-state holdings-state--error" role="alert"><strong>持仓证据读取失败</strong><span>{message}</span><button type="button" onClick={() => selectSession(snapshot?.selected_session)}>重试持仓读取</button></div> : null}
      {state === 'ready' && snapshot ? (
        <>
          <div className="holdings-summary" aria-live="polite">
            <div><span>实际持仓</span><strong>{snapshot.holdings.length} 只</strong></div>
            <div><span>策略目标</span><strong>{backtest.strategy.topk} 只</strong></div>
            <p>{snapshot.holdings.length === backtest.strategy.topk ? '实际持仓数与策略目标一致。' : '实际持仓数与目标不同；可交易性、涨跌停与最少持有约束都可能造成偏离。'}</p>
          </div>
          <MetricHelp
            title="持仓数字怎么算"
            items={[
              { term: '数量', description: '该交易日封存的模拟持股数量。' },
              { term: '权重', description: '单只股票市值 ÷ 当日组合总市值。' },
              { term: '市值', description: '封存持股数量乘以回测采用的当日估值价格。' },
            ]}
          />
          {snapshot.holdings.length ? (
            <div className="holdings-table-wrap">
              <table className="holdings-table">
                <caption className="sr-only">{snapshot.selected_session} 封存历史持仓</caption>
                <thead><tr><th scope="col">股票代码</th><th scope="col">数量</th><th scope="col">权重</th><th scope="col">市值</th></tr></thead>
                <tbody>
                  {snapshot.holdings.map((holding) => {
                    return (
                      <tr key={holding.instrument}>
                        <th scope="row"><code>{holding.instrument}</code></th>
                        <td>{holding.amount.toLocaleString()}</td>
                        <td>{formatPercent(holding.weight)}</td>
                        <td>{formatMoney(holding.value)}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : <div className="holdings-state">该交易日的封存持仓为空。</div>}
          <div className="holdings-receipt"><span>Artifact <code>{shortHash(snapshot.source.artifact_sha256)}</code></span><span>Holdings receipt <code>{shortHash(snapshot.source.receipt_sha256)}</code></span><span>Backtest receipt <code>{shortHash(snapshot.source.backtest_receipt_sha256)}</code></span></div>
        </>
      ) : null}
    </section>
  )
}

function BacktestChart({
  officialPoints,
  top3Points,
}: {
  officialPoints: HistoricalBacktestPoint[]
  top3Points: HistoricalBacktestPoint[]
}) {
  const chartId = useId().replace(/:/g, '')
  const points = officialPoints.length >= 2 ? officialPoints : top3Points
  if (points.length < 2) return <EmptyState title="历史曲线尚未发布" description="回测摘要存在，但逐日曲线还没有通过哈希校验。" />
  const values = [
    ...officialPoints.flatMap((point) => [point.strategy, point.benchmark]),
    ...top3Points.map((point) => point.strategy),
  ]
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const polyline = (series: HistoricalBacktestPoint[], key: 'strategy' | 'benchmark') => series.map((point, index) => {
    const x = 2 + (index / (series.length - 1)) * 96
    const y = 94 - ((point[key] - min) / range) * 86
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
  const benchmarkPoints = officialPoints.length >= 2 ? officialPoints : top3Points
  const hasTop3 = top3Points.length >= 2
  return (
    <div className="backtest-chart">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-labelledby={`${chartId}-title ${chartId}-description`}>
        <title id={`${chartId}-title`}>{hasTop3 ? '官方对齐Top50、历史Qlib Top3与沪深300算术累计收益曲线' : '官方对齐Top50与沪深300算术累计收益曲线'}</title>
        <desc id={`${chartId}-description`}>{hasTop3 ? '展示封存区间内官方对齐Top50实线、历史Qlib Top3长虚线和沪深300短虚线的每日收益算术累加。' : '旧版回执只展示官方对齐Top50实线和沪深300短虚线的每日收益算术累加。'}</desc>
        <line x1="0" x2="100" y1={94 - ((0 - min) / range) * 86} y2={94 - ((0 - min) / range) * 86} className="backtest-chart__zero" />
        {officialPoints.length >= 2 ? <polyline points={polyline(officialPoints, 'strategy')} className="backtest-chart__official" vectorEffect="non-scaling-stroke" /> : null}
        {hasTop3 ? <polyline points={polyline(top3Points, 'strategy')} className="backtest-chart__top3" vectorEffect="non-scaling-stroke" /> : null}
        <polyline points={polyline(benchmarkPoints, 'benchmark')} className="backtest-chart__benchmark" vectorEffect="non-scaling-stroke" />
      </svg>
      <div><span>{points[0]?.session}</span><strong>{hasTop3 ? '三线对照' : '两线对照'}</strong><span>{points.at(-1)?.session}</span></div>
    </div>
  )
}
