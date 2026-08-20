import { useMemo, useState } from 'react'

import { formatNumber, formatPercent, shortHash } from '../format'
import type { CrossModelComparison, CrossModelComparisonMetrics } from '../types'

const metricDefinitions: Array<[keyof CrossModelComparisonMetrics, string, string, 'percent' | 'number']> = [
  ['rank_ic', 'RankIC', '每日截面中，预测排序与随后实际收益排序的相关性；0 附近表示排序信号较弱。', 'number'],
  ['pearson_ic', 'Pearson IC', '预测分数与随后实际收益的线性相关性；与 RankIC 共同说明预测质量。', 'number'],
  ['icir', 'ICIR', 'RankIC 的均值除以其波动，数值越高表示信号更稳定。', 'number'],
  ['coverage', '覆盖率', '进入共同评估锚点的有效股票样本占比。', 'percent'],
]

const strategyDefinitions: Array<[keyof CrossModelComparisonMetrics, string, string, 'percent' | 'number']> = [
  ['total_return_with_cost', '累计收益（含费）', '按共同执行期、T+1 价格和成本计算的策略算术累计收益。', 'percent'],
  ['excess_return_with_cost', '含费超额', '策略累计收益减去同一期间的沪深300累计收益。', 'percent'],
  ['max_drawdown_with_cost', '最大回撤', '策略曲线从任一历史高点到随后低点的最大跌幅。', 'percent'],
  ['turnover_mean', '日均换手', '平均每日买卖金额占组合规模的比例，越高通常意味着成本敏感性更高。', 'percent'],
]
const noModels: CrossModelComparison['models'] = []

const value = (metric: CrossModelComparisonMetrics, key: keyof CrossModelComparisonMetrics, kind: 'percent' | 'number') =>
  kind === 'percent' ? formatPercent(metric[key] as number | null | undefined) : formatNumber(metric[key] as number | null | undefined)

function ComparisonCurve({ lines }: { lines: Array<{ label: string; points: { session: string; strategy: number; benchmark: number }[]; tone: string }> }) {
  const all = lines.flatMap((line) => line.points.flatMap((point) => [point.strategy, point.benchmark]))
  if (all.length < 2) return <p className="comparison-empty">该组合尚未发布可绘制的封存曲线。</p>
  const min = Math.min(0, ...all)
  const max = Math.max(0, ...all)
  const range = Math.max(max - min, 0.01)
  const points = (rows: { strategy: number }[]) => rows.map((point, index) => `${(index / Math.max(rows.length - 1, 1)) * 100},${94 - ((point.strategy - min) / range) * 86}`).join(' ')
  return <div className="comparison-chart"><svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="所选模型的策略累计收益曲线对比"><line className="comparison-chart__zero" x1="0" x2="100" y1={94 - ((0 - min) / range) * 86} y2={94 - ((0 - min) / range) * 86} />{lines.map((line) => <polyline key={line.label} points={points(line.points)} className={line.tone} vectorEffect="non-scaling-stroke" />)}</svg><div className="chart-legend">{lines.map((line) => <span key={line.label} className={line.tone.replace('comparison-chart__', 'comparison-legend__')}>{line.label}</span>)}<small>同一执行区间；纵轴为含费算术累计收益。</small></div></div>
}

export function CrossModelComparisonPanel({ comparison }: { comparison?: CrossModelComparison }) {
  const models = comparison?.models ?? noModels
  const [family, setFamily] = useState(models[0]?.family)
  const currentFamily = models.some((model) => model.family === family) ? family : models[0]?.family
  const selectedModel = models.find((model) => model.family === currentFamily) ?? null
  const [topk, setTopk] = useState<1 | 3 | 50>(1)
  const selectedTopk = selectedModel?.strategies.some((strategy) => strategy.topk === topk) ? topk : (selectedModel?.strategies[0]?.topk ?? 1)
  const selectedStrategy = selectedModel?.strategies.find((strategy) => strategy.topk === selectedTopk) ?? null
  const lines = useMemo(() => models.map((model, index) => {
    const strategy = model.strategies.find((candidate) => candidate.topk === selectedTopk)
    return strategy ? { label: model.label, points: strategy.series, tone: index === 0 ? 'comparison-chart__itransformer' : 'comparison-chart__kronos' } : null
  }).filter((line): line is NonNullable<typeof line> => line !== null), [models, selectedTopk])

  if (!comparison?.available || !comparison.protocol || !selectedModel || !selectedStrategy) return null
  const protocol = comparison.protocol
  return <section className="cross-model-panel" aria-labelledby="cross-model-heading">
    <header className="cross-model-panel__heading"><div><span className="eyebrow">Aligned cross-model study</span><h2 id="cross-model-heading">统一评估期模型对比</h2><p>{protocol.label} · {protocol.universe} · {protocol.frequency}</p></div><div className="cross-model-panel__dates"><span>信号期 {protocol.signal_start} → {protocol.signal_end}</span><strong>执行期 {protocol.execution_start} → {protocol.execution_end}</strong></div></header>
    <p className="comparison-protocol">所有模型使用相同的评估锚点与策略执行期。预测输入窗口可不同：这正是模型定义的一部分；原生损失不会横向比较。</p>
    <div className="comparison-pickers"><div role="group" aria-label="选择模型家族">{models.map((model) => <button type="button" key={model.id} className={currentFamily === model.family ? 'comparison-choice is-active' : 'comparison-choice'} aria-pressed={currentFamily === model.family} onClick={() => setFamily(model.family)}><strong>{model.label}</strong><small>{model.input.lookback_sessions} 个历史交易日输入</small></button>)}</div><div role="group" aria-label="选择组合规模">{([1, 3, 50] as const).map((item) => <button key={item} type="button" disabled={!models.some((model) => model.strategies.some((strategy) => strategy.topk === item))} className={selectedTopk === item ? 'comparison-topk is-active' : 'comparison-topk'} aria-pressed={selectedTopk === item} onClick={() => setTopk(item)}>Top{item}</button>)}</div></div>
    <div className="comparison-input"><span>当前模型输入</span><strong>{selectedModel.input.description}</strong><small>窗口：过去 {selectedModel.input.lookback_sessions} 个交易日；特征：{selectedModel.input.features.join('、')}</small></div>
    <div className="comparison-metric-grid">{metricDefinitions.map(([key, label, help, kind]) => <div key={key}><span>{label}</span><strong>{value(selectedModel.common_metrics, key, kind)}</strong><small>{help}</small></div>)}</div>
    <ComparisonCurve lines={lines} />
    <section className="comparison-strategy"><div><span className="eyebrow">Selected strategy</span><h3>{selectedModel.label} · {selectedStrategy.label}</h3><p>Top{selectedStrategy.topk} 按共同执行协议回测；下列数值只比较交易结果。</p></div><div className="comparison-strategy__metrics">{strategyDefinitions.map(([key, label, help, kind]) => <div key={key}><span title={help}>{label}</span><strong>{value(selectedStrategy.metrics, key, kind)}</strong><small>{help}</small></div>)}</div></section>
    <section className="comparison-holdings"><div><span className="eyebrow">Sealed holdings</span><h3>评估期末持仓</h3></div>{selectedStrategy.holdings ? <><p>{selectedStrategy.holdings.session} · {selectedStrategy.holdings.items.length} 只实际持仓（策略目标 Top{selectedStrategy.topk}）</p><div className="holdings-table-wrap"><table className="holdings-table"><thead><tr><th>股票代码</th><th>权重</th><th>数量</th><th>市值</th></tr></thead><tbody>{selectedStrategy.holdings.items.map((holding) => <tr key={holding.instrument}><th>{holding.instrument}</th><td>{formatPercent(holding.weight)}</td><td>{holding.amount?.toLocaleString('zh-CN') ?? '—'}</td><td>{holding.value === null || holding.value === undefined ? '—' : holding.value.toLocaleString('zh-CN', { style: 'currency', currency: 'CNY', maximumFractionDigits: 0 })}</td></tr>)}</tbody></table></div><small>持仓回执 {shortHash(selectedStrategy.holdings.receipt_sha256)}</small></> : <p className="comparison-empty">该策略尚未公开期末持仓回执。</p>}</section>
    <footer className="comparison-evidence">共同锚点 {shortHash(protocol.anchor_set_sha256)} · checkpoint {shortHash(selectedModel.checkpoint_sha256)} · 标签定义：{protocol.label_definition}</footer>
  </section>
}
