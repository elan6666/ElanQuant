import type { ExecutionProfile, ServiceState } from '../types'

export type PageKey = 'overview' | 'jobs' | 'research' | 'backtest' | 'ranking' | 'paper'

const navItems: { key: PageKey; label: string; index: string }[] = [
  { key: 'overview', label: '总览', index: '01' },
  { key: 'jobs', label: '任务', index: '02' },
  { key: 'research', label: '实验矩阵', index: '03' },
  { key: 'backtest', label: '历史回测', index: '04' },
  { key: 'ranking', label: '股票排名', index: '05' },
  { key: 'paper', label: '模拟账户', index: '06' },
]

interface ShellProps {
  page: PageKey
  onPageChange: (page: PageKey) => void
  serviceState: ServiceState | 'connecting'
  refreshing: boolean
  onRefresh: () => void
  executionProfile: ExecutionProfile
  children: React.ReactNode
}

const serviceLabel: Record<ShellProps['serviceState'], string> = {
  connecting: '正在连接',
  ready: '运行服务就绪',
  degraded: '服务降级',
  offline: '运行服务离线',
}

export function Shell({
  page,
  onPageChange,
  serviceState,
  refreshing,
  onRefresh,
  executionProfile,
  children,
}: ShellProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand__seal">EQ</div>
          <div>
            <strong>ElanQuant</strong>
            <span>研究控制台 / v0</span>
          </div>
        </div>

        <nav className="nav" aria-label="主要导航">
          {navItems.map((item) => (
            <button
              className={page === item.key ? 'nav__item nav__item--active' : 'nav__item'}
              key={item.key}
              onClick={() => onPageChange(item.key)}
              type="button"
              aria-current={page === item.key ? 'page' : undefined}
            >
              <span>{item.index}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar__notice">
          <span className="eyebrow">研究边界</span>
          <p>仅用于模型研究与模拟交易，不连接真实证券账户，不构成投资建议。</p>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="topbar__connection">
            <span className={`connection-dot connection-dot--${serviceState}`} aria-hidden="true" />
            <span>{serviceLabel[serviceState]}</span>
            <small>{executionProfile === 'local-apple-silicon' ? '本机运行 · Apple Silicon' : '远程运行 · Linux / NVIDIA'}</small>
          </div>
          <button className="text-button" type="button" onClick={onRefresh} disabled={refreshing}>
            {refreshing ? '刷新中…' : '刷新状态'}
          </button>
        </header>
        <main className="page" id="main-content">
          {children}
        </main>
        <nav className="mobile-nav" aria-label="移动端导航">
          {navItems.map((item) => (
            <button
              className={page === item.key ? 'mobile-nav__item mobile-nav__item--active' : 'mobile-nav__item'}
              key={item.key}
              onClick={() => onPageChange(item.key)}
              type="button"
              aria-label={item.label}
              aria-current={page === item.key ? 'page' : undefined}
            >
              <span>{item.index}</span>
              <small>{item.label}</small>
            </button>
          ))}
        </nav>
      </div>
    </div>
  )
}
