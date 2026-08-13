import { useState } from 'react'

import { Badge } from '../components/Badge'
import { EmptyState } from '../components/EmptyState'
import { formatMoney, formatPercent, shortHash } from '../format'
import type {
  HistoricalBacktest,
  HistoricalBacktestPoint,
  OfficialDemoSignal,
} from '../types'

const signals: { id: OfficialDemoSignal; label: string; detail: string }[] = [
  { id: 'mean', label: '未来均值', detail: '预先指定的主信号' },
  { id: 'last', label: '第10日', detail: '辅助描述，不参与选优' },
  { id: 'max', label: '未来最大', detail: '辅助描述，不参与选优' },
  { id: 'min', label: '未来最小', detail: '辅助描述，不参与选优' },
]

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
}: {
  backtests: HistoricalBacktest[]
  available: boolean
  seriesById: Record<string, HistoricalBacktestPoint[]>
}) {
  const [selectedSplit, setSelectedSplit] = useState<
    'validation_2025' | 'test_viewed_2026'
  >('test_viewed_2026')
  const backtest =
    backtests.find((entry) => entry.evaluation_split === selectedSplit) ??
    backtests.find((entry) => entry.evaluation_split === 'validation_2025') ??
    null
  const series = backtest === null ? [] : (seriesById[backtest.id] ?? [])
  return (
    <>
      <header className="page-heading page-heading--split backtest-heading">
        <div>
          <span className="eyebrow">04 / Official-demo method</span>
          <h1>官方对齐版 <span className="title-phrase">历史回测</span></h1>
          <p>新增一条独立研究版本：标准化空间信号、Top‑50、Drop‑5、最少持有5日。原来的 Top3 在线排名与模拟账户完整保留。</p>
        </div>
        <div className="identity-card identity-card--backtest">
          <span>轨道身份</span>
          <strong>TOP50 / DROP5 / HOLD5</strong>
          <small>历史研究 · 1亿元假设账户 · 不生成在线订单</small>
        </div>
      </header>

      <section className="track-separation" aria-label="双轨隔离说明">
        <div><span>保留</span><strong>Top3 在线模拟</strong><small>手动按钮 · T日冻结 · T+1执行/拒绝</small></div>
        <b aria-hidden="true">＋</b>
        <div><span>新增</span><strong>官方 Demo 对齐版</strong><small>连续历史回测 · Top50 / Drop5 / Hold5</small></div>
        <p>两条轨道不共享订单、持仓、净值或策略名称；本页所有数字都来自只读封存回执。</p>
      </section>

      <section className="strategy-compare" aria-label="Top3与官方对齐版对比">
        <div className="strategy-compare__head"><span>项目</span><strong>保留的 Top3</strong><strong>新增官方对齐版</strong></div>
        {[
          ['行情 / 预测长度', '日频 / 10日', '日频 / 10日'],
          ['运行方式', '收盘后手动按钮', '封存分区连续回测'],
          ['预测采样', '10条', '5条（官方）'],
          ['股票信号', '反归一化百分比收益', '标准化空间差值'],
          ['股票池', '动态PIT沪深300', '动态PIT沪深300（数据偏差已披露）'],
          ['主策略', 'Top3进入 / 退出', 'Top50 / Drop5'],
          ['最少持有', '暂不承诺', '5个交易日'],
          ['执行语义', 'T冻结、T+1执行/拒绝、不递补', 'Qlib延迟至次日开盘'],
          ['拒单处理', '明确禁止同次递补', '由固定Qlib策略与交易所模型处理'],
        ].map(([label, top3, official]) => (
          <div key={label}><span>{label}</span><b>{top3}</b><b>{official}</b></div>
        ))}
      </section>

      {!available || !backtest ? (
        <EmptyState
          title="官方对齐回测正在服务器生成"
          description="Top3 仍可正常使用。只有标准化信号、Qlib回测和哈希回执全部通过后，本页才会展示结果。"
        />
      ) : (
        <>
          <div className="backtest-split-tabs" role="group" aria-label="历史回测评估分区">
            {([
              ['test_viewed_2026', '2026 已开封样本外诊断（已修正）'],
              ['validation_2025', '2025 训练验证 / checkpoint 选择'],
            ] as const).map(([split, label]) => {
              const present = backtests.some((entry) => entry.evaluation_split === split)
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
          <BacktestEvidence backtest={backtest} series={series} />
        </>
      )}
    </>
  )
}

function BacktestEvidence({
  backtest,
  series,
}: {
  backtest: HistoricalBacktest
  series: HistoricalBacktestPoint[]
}) {
  const primary = backtest.metrics.mean
  const finalTest = backtest.evaluation_split === 'test_viewed_2026'
  return (
    <>
      <div className="official-boundary-banner">
        <Badge tone="success">
          {finalTest ? 'CORRECTED / OOS 2026 / OPENED' : 'TRAINING VALIDATION / 2025'}
        </Badge>
        <strong>
          {finalTest
            ? '已修正未来成分/缺行条件；窗口已开封，只作样本外诊断，不是新的盲测'
            : '这一段参与 validation loss 和 best checkpoint 选择，不是最终测试'}
        </strong>
        <span>标准化分数不是预测收益率；本回测也不是在线账户。</span>
      </div>

      <section className="metric-grid backtest-metrics">
        <div className={`metric ${primary.total_return_with_cost >= 0 ? 'metric--positive' : 'metric--negative'}`}><span>策略累计收益（含费）</span><strong>{formatPercent(primary.total_return_with_cost)}</strong><small>官方算术累计曲线口径</small></div>
        <div className="metric"><span>沪深300同期</span><strong>{formatPercent(primary.benchmark_return)}</strong><small>SH000300</small></div>
        <div className={`metric ${primary.excess_return_with_cost >= 0 ? 'metric--positive' : 'metric--negative'}`}><span>含费超额</span><strong>{formatPercent(primary.excess_return_with_cost)}</strong><small>策略 − 基准 − 成本</small></div>
        <div className="metric metric--negative"><span>最大回撤</span><strong>{formatPercent(primary.max_drawdown_with_cost)}</strong><small>mean 主信号</small></div>
      </section>

      <section className="content-section backtest-chart-section">
        <div className="section-heading">
          <div><span className="eyebrow">Primary signal / mean</span><h2>{finalTest ? '2026 已开封样本外诊断曲线' : '2025 训练验证曲线'}</h2></div>
          <span className="count-label">{series.length} SESSIONS</span>
        </div>
        <BacktestChart points={series} />
        <div className="chart-legend"><span className="chart-legend__strategy">Top50策略（含费）</span><span className="chart-legend__benchmark">沪深300</span><small>与官方 qlib_test.py 一致：这里是每日收益算术累加，不把它称为账户NAV。</small></div>
      </section>

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
          <div className="section-heading"><div><span className="eyebrow">Resolved strategy</span><h2>官方 Demo 执行参数</h2></div></div>
          <div className="evidence-list">
            <div><span>持仓 / 每次剔除</span><strong>{backtest.strategy.topk} / {backtest.strategy.n_drop}</strong></div>
            <div><span>最少持有</span><strong>{backtest.strategy.hold_thresh} 个交易日</strong></div>
            <div><span>执行价 / 延迟</span><strong>次日开盘 / 是</strong></div>
            <div><span>假设资金</span><strong>{formatMoney(backtest.execution.account)}</strong></div>
            <div><span>买入 / 卖出成本</span><strong>{formatPercent(backtest.execution.open_cost)} / {formatPercent(backtest.execution.close_cost)}</strong></div>
            <div><span>涨跌停阈值</span><strong>{formatPercent(backtest.execution.limit_threshold)}</strong></div>
          </div>
        </div>
        <div className="content-section">
          <div className="section-heading"><div><span className="eyebrow">Evidence identity</span><h2>数据与回执</h2></div></div>
          <div className="evidence-list">
            <div><span>模型格</span><strong>{backtest.model_cell_id}</strong></div>
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

function BacktestChart({ points }: { points: HistoricalBacktestPoint[] }) {
  if (points.length < 2) return <EmptyState title="历史曲线尚未发布" description="回测摘要存在，但逐日曲线还没有通过哈希校验。" />
  const values = points.flatMap((point) => [point.strategy, point.benchmark])
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const polyline = (key: 'strategy' | 'benchmark') => points.map((point, index) => {
    const x = 2 + (index / (points.length - 1)) * 96
    const y = 94 - ((point[key] - min) / range) * 86
    return `${x.toFixed(2)},${y.toFixed(2)}`
  }).join(' ')
  return (
    <div className="backtest-chart">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-labelledby="backtest-chart-title backtest-chart-description">
        <title id="backtest-chart-title">Top50策略与沪深300算术累计收益曲线</title>
        <desc id="backtest-chart-description">展示封存区间内的含费Top50策略和沪深300每日收益算术累加。</desc>
        <line x1="0" x2="100" y1={94 - ((0 - min) / range) * 86} y2={94 - ((0 - min) / range) * 86} className="backtest-chart__zero" />
        <polyline points={polyline('strategy')} className="backtest-chart__strategy" vectorEffect="non-scaling-stroke" />
        <polyline points={polyline('benchmark')} className="backtest-chart__benchmark" vectorEffect="non-scaling-stroke" />
      </svg>
      <div><span>{points[0]?.session}</span><strong>{formatPercent(points.at(-1)?.strategy)}</strong><span>{points.at(-1)?.session}</span></div>
    </div>
  )
}
