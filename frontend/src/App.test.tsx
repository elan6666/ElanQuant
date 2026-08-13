import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import type { ApiClient } from './types'
import {
  incompleteJob,
  historicalBacktest,
  paperAccount,
  paperSummary,
  passedSmallCell,
  runningJob,
  snapshot,
  successRun,
} from './test/fixtures'

const clientFor = (value: ReturnType<typeof snapshot>): ApiClient => ({
  getSnapshot: vi.fn().mockResolvedValue(value),
  submitUpdateInfer: vi.fn().mockResolvedValue({ job_id: 'job-new', coalesced: false }),
  retryJob: vi.fn().mockResolvedValue({ job_id: 'job-retry', coalesced: false }),
})

describe('ElanQuant dashboard states', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '#/overview')
  })

  it('renders a truthful empty first-run state and primary action', async () => {
    render(<App client={clientFor(snapshot())} />)
    expect(await screen.findByRole('button', { name: /更新数据并运行推理/ })).toBeEnabled()
    expect(screen.getByText('还没有推理结果')).toBeInTheDocument()
    expect(screen.getByText(/不会用示例数据冒充成功/)).toBeInTheDocument()
    expect(screen.getByText('无真实账户')).toBeInTheDocument()
  })

  it('shows durable running progress and disables duplicate submission', async () => {
    render(<App client={clientFor(snapshot({ jobs: [runningJob] }))} />)
    const button = await screen.findByRole('button', { name: /任务正在服务器运行/ })
    expect(button).toBeDisabled()
    expect(screen.getByText(/关闭网页不影响任务.*linger部署检查/)).toBeInTheDocument()
    expect(screen.getByText('Small模型推理')).toBeInTheDocument()
  })

  it('fails closed when data is incomplete', async () => {
    render(<App client={clientFor(snapshot({ jobs: [incompleteJob] }))} />)
    expect(await screen.findByText('本次运行已安全停止')).toBeInTheDocument()
    expect(screen.getByText(/amount 覆盖率/)).toBeInTheDocument()
    expect(screen.getByText('AMOUNT_COVERAGE')).toBeInTheDocument()
  })

  it('renders success surfaces without treating online predictions as scored', async () => {
    render(<App client={clientFor(snapshot({ latest_run: successRun, paper: paperAccount }))} />)
    expect(await screen.findByText('在线预测 · 尚不可评分')).toBeInTheDocument()
    expect(screen.getByText('严格PIT合规资格 · 非验证集最优声明')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '实验矩阵' }))
    expect(screen.getByRole('heading', { name: 'Small 与 Base 六格实验' })).toBeInTheDocument()
    expect(screen.getAllByText('待运行')).toHaveLength(6)

    fireEvent.click(screen.getByRole('button', { name: '股票排名' }))
    expect(screen.getAllByText('浦发银行')).toHaveLength(2)
    expect(screen.getByText(/未来10日尚未结束/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '模拟账户' }))
    expect(screen.getByText('¥101,000')).toBeInTheDocument()
    expect(screen.getByText('完全模拟 · 无券商连接')).toBeInTheDocument()
  })

  it('offers explicit retry for a terminal failure', async () => {
    const failed = { ...incompleteJob, state: 'failed' as const, error_code: 'INFERENCE_FAILED' }
    const client = clientFor(snapshot({ jobs: [failed] }))
    render(<App client={client} />)
    await screen.findByText('本次运行已安全停止').catch(() => undefined)
    fireEvent.click(screen.getByRole('button', { name: '任务' }))
    fireEvent.click(await screen.findByRole('button', { name: '明确重试' }))
    await waitFor(() => expect(client.retryJob).toHaveBeenCalledWith(failed.id))
  })

  it('shows split-aware experiment and explicit paper decision evidence', async () => {
    render(
      <App
        client={clientFor(
          snapshot({
            latest_run: successRun,
            research_catalog: [passedSmallCell],
            research_catalog_available: true,
            paper: paperAccount,
            paper_summary: paperSummary,
          }),
        )}
      />,
    )
    await screen.findByText('在线预测 · 尚不可评分')
    fireEvent.click(screen.getByRole('button', { name: '实验矩阵' }))
    expect(screen.getByText('18,000 rows · 60 sections')).toBeInTheDocument()
    expect(screen.getAllByText(/TEST_VIEWED \/ 2026/)).toHaveLength(6)

    fireEvent.click(screen.getByRole('button', { name: '模拟账户' }))
    expect(screen.getByText('证据不足')).toBeInTheDocument()
    expect(screen.getByText('资金不足一手')).toBeInTheDocument()
    expect(screen.getByText(/不足以买入 A 股最小的 100 股整手/)).toBeInTheDocument()
  })

  it('adds the official-aligned backtest without replacing the Top3 product', async () => {
    render(
      <App
        client={clientFor(
          snapshot({
            historical_backtest: historicalBacktest,
            historical_backtest_available: true,
            historical_backtest_series: [
              { session: '2025-01-02', strategy: 0, benchmark: 0, excess: 0, strategy_nav: 1, benchmark_nav: 1 },
              { session: '2025-12-31', strategy: 0.12, benchmark: 0.08, excess: 0.04, strategy_nav: 1.12, benchmark_nav: 1.08 },
            ],
          }),
        )}
      />,
    )
    fireEvent.click(await screen.findByRole('button', { name: '历史回测' }))
    expect(screen.getByRole('heading', { name: /官方对齐版.*历史回测/ })).toBeInTheDocument()
    expect(screen.getByText('Top3 在线模拟')).toBeInTheDocument()
    expect(screen.getByText('TOP50 / DROP5 / HOLD5')).toBeInTheDocument()
    expect(screen.getByText('5条（官方）')).toBeInTheDocument()
    expect(screen.getByText('明确禁止同次递补')).toBeInTheDocument()
    expect(screen.getByText(/2026 TEST_VIEWED 未用于/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Top50策略与沪深300/ })).toBeInTheDocument()
  })
})
