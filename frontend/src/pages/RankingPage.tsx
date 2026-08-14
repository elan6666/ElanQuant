import { useMemo, useState } from 'react'
import { Badge } from '../components/Badge'
import { EmptyState } from '../components/EmptyState'
import { MetricHelp } from '../components/MetricHelp'
import { formatNumber, formatPercent, formatPrice, paperDecisionLabel, paperDecisionReason, shortHash } from '../format'
import type { ResearchRun, StockScore } from '../types'

const emptyScores: StockScore[] = []

export function RankingPage({ run }: { run: ResearchRun | null }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [limit, setLimit] = useState<10 | 50 | 300>(50)
  const scores = run?.scores ?? emptyScores
  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return scores
      .filter(
        (score) =>
          !normalized ||
          score.symbol.toLowerCase().includes(normalized) ||
          score.name.toLowerCase().includes(normalized),
      )
      .slice(0, limit)
  }, [limit, query, scores])

  if (!run || scores.length === 0) {
    return (
      <>
        <RankingHeading run={run} />
        <EmptyState title="没有可展示的股票排名" description="只有数据完整性、PIT准入和模型推理全部通过后，后端才会发布排名。旧结果不会冒充今天的结果。" />
      </>
    )
  }

  const selectedStock = visible.find((score) => score.symbol === selected) ?? visible[0]
  const stale = run.status === 'stale'

  return (
    <>
      <RankingHeading run={run} />
      {stale ? (
        <div className="stale-banner"><Badge tone="stale">历史结果</Badge><span>该结果仍可复核，但不能标记为当前交易日推荐。</span></div>
      ) : null}
      {!run.scoreable ? (
        <div className="online-banner"><strong>在线预测</strong><span>未来10日尚未结束，因此本次预测不能进入IC、RankIC或收益评估。</span></div>
      ) : null}

      <section className="ranking-tools" aria-label="排名筛选">
        <label><span>查找股票</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="代码或名称" /></label>
        <div><span>展示范围</span>{([10, 50, 300] as const).map((value) => <button className={limit === value ? 'filter-button is-active' : 'filter-button'} type="button" key={value} onClick={() => setLimit(value)}>TOP {value === 300 ? 'ALL' : value}</button>)}</div>
        <small>{visible.length} / {run.scores.length} 只</small>
      </section>

      <MetricHelp
        title="这些数字怎么读"
        items={[
          { term: '10日预测涨跌', description: '未来10个预测收盘价的平均值 ÷ 当前收盘价 − 1；不是已实现收益，也不是上涨概率。' },
          { term: '输入数据完整度', description: '本次后端准入要求中，已经满足的输入项所占比例；100% 表示要求齐全。' },
          { term: '模型评分差距', description: '参与本次排名的模型评分最高值减最低值；越小表示评分更接近，不是概率或置信区间。' },
        ]}
      />

      {selectedStock ? <section className="ranking-layout">
        <div className="ranking-table-wrap">
          <table className="ranking-table">
            <thead>
              <tr><th>排名</th><th>股票</th><th>10日预测涨跌</th><th>上次排名</th><th>输入数据完整度</th><th>资格</th></tr>
            </thead>
            <tbody>
              {visible.map((stock) => (
                <tr
                  className={selectedStock.symbol === stock.symbol ? 'is-selected' : ''}
                  key={stock.symbol}
                  onClick={() => setSelected(stock.symbol)}
                >
                  <td><b>{String(stock.rank).padStart(2, '0')}</b></td>
                  <td><button
                    aria-label={`查看 ${stock.name} ${stock.symbol} 的证据详情`}
                    aria-pressed={selectedStock.symbol === stock.symbol}
                    className="ranking-stock-button"
                    onClick={(event) => {
                      event.stopPropagation()
                      setSelected(stock.symbol)
                    }}
                    type="button"
                  ><strong>{stock.name}</strong><small>{stock.symbol}</small></button></td>
                  <td className={stock.forecast_return >= 0 ? 'positive' : 'negative'}>{formatPercent(stock.forecast_return)}</td>
                  <td>{stock.previous_rank === null ? '首次' : `#${stock.previous_rank} ${stock.rank_delta === null ? '' : stock.rank_delta > 0 ? `↑${stock.rank_delta}` : stock.rank_delta < 0 ? `↓${Math.abs(stock.rank_delta)}` : '—'}`}</td>
                  <td>{formatPercent(stock.input_completeness, 1)}</td>
                  <td>{stock.eligible ? <Badge tone="success">可纳入</Badge> : <Badge tone="warning">已过滤</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <StockDetail stock={selectedStock} run={run} />
      </section> : <EmptyState title="没有匹配的股票" description="请更换代码或名称关键字；系统不会在空搜索时展示无关股票详情。" />}
    </>
  )
}

function RankingHeading({ run }: { run: ResearchRun | null }) {
  return (
    <header className="page-heading page-heading--split">
      <div><span className="eyebrow">05 / Ranking</span><h1>股票排名与证据解释</h1><p>主分数来自反归一化后的10日平均预测收盘价收益；排名不是买入承诺。</p></div>
      <div className="identity-card"><span>As-of</span><strong>{run?.as_of || '—'}</strong><small>Data {shortHash(run?.data_hash)}</small></div>
    </header>
  )
}

function StockDetail({ stock, run }: { stock: StockScore; run: ResearchRun }) {
  const values = stock.forecast.flatMap((point) => [point.p10, point.p90])
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const predictedAveragePrice =
    stock.reference_price === null
      ? null
      : stock.reference_price * (1 + stock.forecast_return)
  return (
    <aside className="stock-detail">
      <div className="stock-detail__head">
        <div><span className="eyebrow">#{stock.rank} / {stock.symbol}</span><h2>{stock.name}</h2></div>
        <div className="forecast-return-summary">
          <span>10日预测涨跌</span>
          <strong className={stock.forecast_return >= 0 ? 'positive' : 'negative'}>{formatPercent(stock.forecast_return)}</strong>
        </div>
      </div>
      <p className="signal-explanation">
        {formatPercent(stock.forecast_return)} 表示预测的10日平均收盘价比当前收盘价
        {stock.forecast_return >= 0 ? '高' : '低'} {formatPercent(Math.abs(stock.forecast_return))}；不是已实现收益，也不是上涨概率。
      </p>
      {stock.reference_price !== null && predictedAveragePrice !== null ? (
        <div className="forecast-denominator">
          <span>当前收盘价 <b>{formatPrice(stock.reference_price)}</b></span>
          <span>预测10日平均价约 <b>{formatPrice(predictedAveragePrice)}</b></span>
        </div>
      ) : (
        <p className="forecast-denominator">公式：未来10个预测收盘价平均值 ÷ 当前收盘价 − 1</p>
      )}
      <p>封存主模型用于本次排名；多模型评分差距只作解释，不代表置信区间。</p>
      <div className="stock-facts">
        <div><span>上次排名</span><b>{stock.previous_rank === null ? '首次出现' : `#${stock.previous_rank}`}</b></div>
        <div><span>模型评分差距</span><b>{formatNumber(stock.model_spread, 4)}</b></div>
        <div><span>Top 3资格</span><b>{stock.selected_top3 ? '已入选' : '未入选'}</b></div>
        <div><span>模拟账本决策</span><b>{paperDecisionLabel(stock.paper_decision)}</b></div>
      </div>
      {stock.paper_reason ? <p className="decision-reason">{paperDecisionReason(stock.paper_decision, stock.paper_reason)}</p> : null}
      <details className="raw-score-details">
        <summary>查看各模型原始分数</summary>
        <div className="model-compare">
          {Object.entries(stock.model_scores).map(([model, score]) => <div key={model}><span>{model}</span><b>{formatNumber(score, 4)}</b></div>)}
        </div>
      </details>
      {stock.forecast.length > 0 ? (
        <div className="forecast-chart" role="img" aria-label="未来十日预测均值与区间">
          <div className="forecast-chart__grid" />
          {stock.forecast.map((point, index) => {
            const left = stock.forecast.length === 1 ? 50 : (index / (stock.forecast.length - 1)) * 100
            const bottom = ((point.mean - min) / range) * 100
            const low = ((point.p10 - min) / range) * 100
            const high = ((point.p90 - min) / range) * 100
            return (
              <div className="forecast-point" key={point.session} style={{ left: `${left}%`, bottom: `${bottom}%` }} title={`${point.session} 均值 ${point.mean.toFixed(2)}`}>
                <span style={{ height: `${Math.max(4, high - low)}%`, bottom: `${low - bottom}%` }} />
                <i />
              </div>
            )
          })}
        </div>
      ) : <p className="muted">当前只发布封存的10日汇总信号，未发布可审计的逐日分位数路径。</p>}
      <footer><code>RUN {run.id}</code><code>MODEL {shortHash(run.model_hash)}</code></footer>
    </aside>
  )
}
