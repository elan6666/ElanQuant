import { Badge } from '../components/Badge'
import { EmptyState } from '../components/EmptyState'
import { Metric } from '../components/Metric'
import { formatMoney, formatPercent } from '../format'
import type { PaperAccount } from '../types'

export function PaperPage({ account }: { account: PaperAccount | null }) {
  return (
    <>
      <header className="page-heading page-heading--split">
        <div><span className="eyebrow">05 / Paper ledger</span><h1>模拟账户与成交账本</h1><p>T日收盘冻结意图，T+1只负责成交或拒绝；拒单不会用新信息补买另一只股票。</p></div>
        <div className="identity-card identity-card--paper"><span>账户类型</span><strong>RMB 100K / LONG ONLY</strong><small>完全模拟 · 无券商连接</small></div>
      </header>

      {!account ? (
        <EmptyState title="模拟账户尚未初始化" description="第一次有效推理会创建账户并冻结下一交易日订单意图。没有真实行情结果时，不生成模拟成交。" />
      ) : (
        <>
          <section className="metric-grid metric-grid--paper">
            <Metric label="账户总资产" value={formatMoney(account.total_equity)} detail={`截至 ${account.as_of || '—'}`} tone={(account.total_return ?? 0) >= 0 ? 'positive' : 'negative'} />
            <Metric label="可用现金" value={formatMoney(account.cash)} detail={`${formatPercent(account.cash / account.total_equity)} 现金占比`} />
            <Metric label="持仓市值" value={formatMoney(account.market_value)} detail={`${account.positions.length} 只持仓`} />
            <Metric label="累计收益" value={formatPercent(account.total_return)} detail={`初始资金 ${formatMoney(account.initial_cash)}`} tone={(account.total_return ?? 0) >= 0 ? 'positive' : 'negative'} />
          </section>

          {account.gaps.length > 0 ? <div className="gap-notice"><strong>手动运行缺口</strong>{account.gaps.map((gap) => <span key={gap}>{gap}</span>)}</div> : null}

          <section className="two-column two-column--ledger">
            <div className="content-section">
              <div className="section-heading"><div><span className="eyebrow">Positions</span><h2>当前持仓</h2></div><span className="count-label">TOP 3</span></div>
              {account.positions.length === 0 ? <EmptyState title="当前空仓" description="系统尚未形成可执行的模拟持仓。" /> : (
                <div className="positions-list">
                  {account.positions.map((position) => (
                    <article key={position.symbol}>
                      <div><strong>{position.name}</strong><small>{position.symbol} · 平均成本 {position.average_cost === null ? '—' : formatMoney(position.average_cost)}</small></div>
                      <div><b>{position.quantity} 股</b><small>可卖 {position.available_quantity ?? '—'}</small></div>
                      <div><b>{position.market_value === null ? '—' : formatMoney(position.market_value)}</b><small className={(position.unrealized_pnl ?? 0) >= 0 ? 'positive' : 'negative'}>{position.valuation_source === 'average_cost_fallback' ? '成本价回退估值' : position.unrealized_pnl === null ? '—' : formatMoney(position.unrealized_pnl)}</small></div>
                    </article>
                  ))}
                </div>
              )}
            </div>

            <div className="content-section">
              <div className="section-heading"><div><span className="eyebrow">NAV</span><h2>账户净值</h2></div><span className="count-label">{account.nav.length} SESSIONS</span></div>
              <NavChart account={account} />
            </div>
          </section>

          <section className="content-section orders-section">
            <div className="section-heading"><div><span className="eyebrow">Intents & fills</span><h2>订单意图与模拟成交</h2></div><span className="count-label">{account.orders.length} RECORDS</span></div>
            {account.orders.length === 0 ? <EmptyState title="暂无订单记录" description="只有正式发布的排名才能生成冻结订单意图。" /> : (
              <div className="table-scroll"><table className="orders-table"><thead><tr><th>信号日 / 执行日</th><th>股票</th><th>方向</th><th>数量</th><th>状态</th><th>价格 / 费用</th><th>说明</th></tr></thead><tbody>
                {account.orders.map((order) => <tr key={order.id}><td><strong>{order.signal_session}</strong><small>{order.execution_session || '待下一交易日'}</small></td><td><strong>{order.name}</strong><small>{order.symbol}</small></td><td className={order.side === 'buy' ? 'positive' : 'negative'}>{order.side === 'buy' ? '买入' : '卖出'}</td><td>{order.quantity}</td><td><Badge tone={order.status === 'filled' ? 'success' : order.status === 'rejected' ? 'danger' : 'running'}>{order.status === 'filled' ? '已成交' : order.status === 'rejected' ? '已拒绝' : '已冻结'}</Badge></td><td><strong>{order.price === null ? '—' : `¥${order.price.toFixed(2)}`}</strong><small>{order.fees === null ? '—' : `费用 ¥${order.fees.toFixed(2)}`}</small></td><td>{order.reason || '—'}</td></tr>)}
              </tbody></table></div>
            )}
          </section>
        </>
      )}
    </>
  )
}

function NavChart({ account }: { account: PaperAccount }) {
  if (account.nav.length < 2) return <EmptyState title="净值点不足" description="至少完成两个交易日后才显示趋势。" />
  const values = account.nav.map((point) => point.nav)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const points = account.nav.map((point, index) => `${(index / (account.nav.length - 1)) * 100},${100 - ((point.nav - min) / range) * 82 - 9}`).join(' ')
  return (
    <div className="nav-chart">
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="模拟账户净值走势">
        <polyline points={points} vectorEffect="non-scaling-stroke" />
      </svg>
      <div><span>{account.nav[0]?.session}</span><strong>{account.nav.at(-1)?.nav.toFixed(4)}</strong><span>{account.nav.at(-1)?.session}</span></div>
    </div>
  )
}
