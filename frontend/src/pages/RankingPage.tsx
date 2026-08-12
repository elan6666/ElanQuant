import { useState } from 'react'
import { Badge } from '../components/Badge'
import { EmptyState } from '../components/EmptyState'
import { formatNumber, formatPercent, shortHash } from '../format'
import type { ResearchRun, StockScore } from '../types'

export function RankingPage({ run }: { run: ResearchRun | null }) {
  const [selected, setSelected] = useState<string | null>(null)

  if (!run || run.scores.length === 0) {
    return (
      <>
        <RankingHeading run={run} />
        <EmptyState title="没有可展示的股票排名" description="只有数据完整性、PIT准入和模型推理全部通过后，后端才会发布排名。旧结果不会冒充今天的结果。" />
      </>
    )
  }

  const selectedStock = run.scores.find((score) => score.symbol === selected) ?? run.scores[0]!
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

      <section className="ranking-layout">
        <div className="ranking-table-wrap">
          <table className="ranking-table">
            <thead>
              <tr><th>排名</th><th>股票</th><th>10日预期</th><th>综合分</th><th>覆盖率</th><th>资格</th></tr>
            </thead>
            <tbody>
              {run.scores.map((stock) => (
                <tr
                  className={selectedStock.symbol === stock.symbol ? 'is-selected' : ''}
                  key={stock.symbol}
                  onClick={() => setSelected(stock.symbol)}
                >
                  <td><b>{String(stock.rank).padStart(2, '0')}</b></td>
                  <td><strong>{stock.name}</strong><small>{stock.symbol}</small></td>
                  <td className={stock.forecast_return >= 0 ? 'positive' : 'negative'}>{formatPercent(stock.forecast_return)}</td>
                  <td>{formatNumber(stock.score, 4)}</td>
                  <td>{formatPercent(stock.coverage, 1)}</td>
                  <td>{stock.eligible ? <Badge tone="success">可纳入</Badge> : <Badge tone="warning">已过滤</Badge>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <StockDetail stock={selectedStock} run={run} />
      </section>
    </>
  )
}

function RankingHeading({ run }: { run: ResearchRun | null }) {
  return (
    <header className="page-heading page-heading--split">
      <div><span className="eyebrow">04 / Ranking</span><h1>股票排名与预测路径</h1><p>主分数来自反归一化后的10日平均预测收盘价收益；排名不是买入承诺。</p></div>
      <div className="identity-card"><span>As-of</span><strong>{run?.as_of || '—'}</strong><small>Data {shortHash(run?.data_hash)}</small></div>
    </header>
  )
}

function StockDetail({ stock, run }: { stock: StockScore; run: ResearchRun }) {
  const values = stock.forecast.flatMap((point) => [point.p10, point.p90])
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  return (
    <aside className="stock-detail">
      <div className="stock-detail__head"><div><span className="eyebrow">#{stock.rank} / {stock.symbol}</span><h2>{stock.name}</h2></div><strong className={stock.forecast_return >= 0 ? 'positive' : 'negative'}>{formatPercent(stock.forecast_return)}</strong></div>
      <p>{stock.explanation}</p>
      <div className="model-compare">
        {Object.entries(stock.model_scores).map(([model, score]) => <div key={model}><span>{model}</span><b>{formatNumber(score, 4)}</b></div>)}
      </div>
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
      ) : <p className="muted">未发布逐日预测路径。</p>}
      <footer><code>RUN {run.id}</code><code>MODEL {shortHash(run.model_hash)}</code></footer>
    </aside>
  )
}
