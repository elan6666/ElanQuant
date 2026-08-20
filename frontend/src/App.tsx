import { useState } from 'react'
import { createApiClient } from './api'
import { Shell, type PageKey } from './components/Shell'
import { CrossModelComparisonPanel } from './components/CrossModelComparisonPanel'
import { JobsPage } from './pages/JobsPage'
import { HistoricalBacktestPage } from './pages/HistoricalBacktestPage'
import { OverviewPage } from './pages/OverviewPage'
import { PaperPage } from './pages/PaperPage'
import { RankingPage } from './pages/RankingPage'
import { ResearchPage } from './pages/ResearchPage'
import type { ApiClient } from './types'
import { useDashboard } from './useDashboard'

const productionClient = createApiClient()

const validPages: PageKey[] = ['overview', 'jobs', 'research', 'backtest', 'ranking', 'paper']

const initialPage = (): PageKey => {
  const candidate = window.location.hash.replace('#/', '') as PageKey
  return validPages.includes(candidate) ? candidate : 'overview'
}

export function App({ client = productionClient }: { client?: ApiClient }) {
  const [page, setPage] = useState<PageKey>(initialPage)
  const dashboard = useDashboard(client)

  const navigate = (next: PageKey) => {
    setPage(next)
    window.history.replaceState(null, '', `#/${next}`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  if (dashboard.loading && !dashboard.snapshot) {
    return (
      <div className="boot-screen" role="status">
        <div className="brand__seal">EQ</div>
        <span className="eyebrow">ElanQuant / Connecting</span>
        <h1>正在读取运行服务状态</h1>
        <p>正在建立安全连接。</p>
        <div className="boot-line"><span /></div>
      </div>
    )
  }

  if (!dashboard.snapshot) {
    return (
      <div className="connection-screen">
        <span className="eyebrow">Connection unavailable</span>
        <h1>无法读取 ElanQuant 运行服务</h1>
        <p>{dashboard.error || '没有收到运行服务响应。'}</p>
        <p>请确认已配置的本机或远程运行服务可用，然后重试。</p>
        <button className="primary-action" type="button" onClick={() => void dashboard.refresh()}>
          <span>重新连接</span><b>↻</b>
        </button>
        <small>已有任务不会因为这个页面断线而停止。</small>
      </div>
    )
  }

  const snapshot = dashboard.snapshot
  return (
    <Shell
      page={page}
      onPageChange={navigate}
      serviceState={snapshot.system.service_state}
      refreshing={dashboard.refreshing}
      onRefresh={() => void dashboard.refresh()}
      executionProfile={snapshot.system.active_execution_profile}
    >
      {dashboard.error ? (
        <div className="error-banner" role="alert">
          <strong>刷新失败，当前显示上一次已确认状态</strong>
          <span>{dashboard.error}</span>
        </div>
      ) : null}
      {page === 'overview' ? (
        <OverviewPage
          snapshot={snapshot}
          submitting={dashboard.submitting}
          receipt={dashboard.receipt}
          onSubmit={(profile) => void dashboard.submit(profile)}
        />
      ) : null}
      {page === 'jobs' ? (
        <JobsPage jobs={snapshot.jobs} comparison={snapshot.cross_model_comparison} submitting={dashboard.submitting} onRetry={(id) => void dashboard.retry(id)} />
      ) : null}
      {page === 'research' ? (
        <ResearchPage
          run={snapshot.latest_run}
          catalog={snapshot.research_catalog}
          catalogAvailable={snapshot.research_catalog_available}
          runs={snapshot.runs}
          diff={snapshot.run_diff}
          comparison={snapshot.cross_model_comparison}
        />
      ) : null}
      {page === 'backtest' ? (
        <>
          <CrossModelComparisonPanel comparison={snapshot.cross_model_comparison} />
          <HistoricalBacktestPage
            backtests={snapshot.historical_backtests}
            available={snapshot.historical_backtest_available}
            seriesById={snapshot.historical_backtest_series}
            onLoadHoldings={client.getHistoricalHoldings}
          />
        </>
      ) : null}
      {page === 'ranking' ? <RankingPage run={snapshot.latest_run} comparison={snapshot.cross_model_comparison} onLoadWeeklyRanking={client.getWeeklyModelRanking} /> : null}
      {page === 'paper' ? (
        <PaperPage account={snapshot.paper} summary={snapshot.paper_summary} />
      ) : null}
    </Shell>
  )
}
