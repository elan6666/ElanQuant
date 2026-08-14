import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import type { ApiClient, HistoricalHoldingsSnapshot } from './types'
import {
  finalTestHistoricalBacktest,
  finalTestHistoricalTop3Backtest,
  incompleteJob,
  historicalBacktest,
  historicalTop3Backtest,
  paperAccount,
  paperSummary,
  passedSmallCell,
  runningJob,
  snapshot,
  successRun,
} from './test/fixtures'

const clientFor = (value: ReturnType<typeof snapshot>): ApiClient => ({
  getSnapshot: vi.fn().mockResolvedValue(value),
  getHistoricalHoldings: vi.fn().mockResolvedValue(null),
  submitUpdateInfer: vi.fn().mockResolvedValue({ job_id: 'job-new', coalesced: false, execution_profile: 'legacy-yilangliu' }),
  retryJob: vi.fn().mockResolvedValue({ job_id: 'job-retry', coalesced: false, execution_profile: 'legacy-yilangliu' }),
})

describe('ElanQuant dashboard states', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '#/overview')
  })

  it('renders a truthful empty first-run state and primary action', async () => {
    render(<App client={clientFor(snapshot())} />)
    expect(await screen.findByRole('button', { name: /提交到远程服务器/ })).toBeEnabled()
    expect(screen.getByText('还没有推理结果')).toBeInTheDocument()
    expect(screen.getByText(/不会用示例数据冒充成功/)).toBeInTheDocument()
    expect(screen.getByText('无真实账户')).toBeInTheDocument()
  })

  it('submits the selected execution profile through the real job contract', async () => {
    const initial = snapshot()
    const client = clientFor(snapshot({
      system: {
        ...initial.system,
        active_execution_profile: 'local-apple-silicon',
        default_execution_location: 'local',
        execution_profiles: {
          local: { available: true, profile_id: 'local-apple-silicon', reason: null },
          remote: { available: false, profile_id: null, reason: '请从远程 profile 启动 ElanQuant' },
        },
      },
    }))
    render(<App client={client} />)
    fireEvent.click(await screen.findByRole('button', { name: /用本机更新并推理/ }))
    await waitFor(() => expect(client.submitUpdateInfer).toHaveBeenCalledWith('local-apple-silicon'))
  })

  it('shows durable running progress and disables duplicate submission', async () => {
    render(<App client={clientFor(snapshot({ jobs: [runningJob] }))} />)
    const button = await screen.findByRole('button', { name: /任务正在运行/ })
    expect(button).toBeDisabled()
    expect(screen.getByText(/任务已提交，可以离开此页面/)).toBeInTheDocument()
    expect(screen.queryByText(/linger|Worker|VPN|SQLite/)).not.toBeInTheDocument()
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
    expect(screen.getByText('精确模型身份见下方审计信息')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '方法说明' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '实验矩阵' }))
    expect(screen.getByRole('heading', { name: 'Small 与 Base 四格对照' })).toBeInTheDocument()
    expect(screen.getAllByText('待运行')).toHaveLength(4)
    expect(screen.queryByText('严格PIT适配')).not.toBeInTheDocument()
    expect(screen.queryByText(/small-strict-pit/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '股票排名' }))
    expect(screen.getAllByText('浦发银行')).toHaveLength(2)
    expect(screen.getByText(/未来10日尚未结束/)).toBeInTheDocument()
    expect(screen.getAllByText('2.04%').length).toBeGreaterThan(0)
    expect(screen.getByText(/2.04% 表示预测的10日平均收盘价比当前收盘价高 2.04%/)).toBeInTheDocument()
    expect(screen.getAllByText(/不是已实现收益，也不是上涨概率/).length).toBeGreaterThan(0)
    expect(screen.getByText('¥10.00')).toBeInTheDocument()
    expect(screen.getByText('¥10.20')).toBeInTheDocument()
    expect(screen.getByText(/封存主模型用于本次排名/)).toBeInTheDocument()
    expect(screen.queryByText(/严格PIT轨驱动排名/)).not.toBeInTheDocument()

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
            research_catalog: [
              passedSmallCell,
              { ...passedSmallCell, id: 'small-strict-pit', track: 'strict_pit' },
            ],
            research_catalog_available: true,
            paper: paperAccount,
            paper_summary: paperSummary,
          }),
        )}
      />,
    )
    await screen.findByText('在线预测 · 尚不可评分')
    fireEvent.click(screen.getByRole('button', { name: '实验矩阵' }))
    expect(screen.getByText('18,000 条股票样本 · 60 个交易日截面')).toBeInTheDocument()
    expect(screen.getAllByText(/2026 已查看测试（只描述）/)).toHaveLength(4)
    expect(screen.queryByText('严格PIT适配')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '模拟账户' }))
    expect(screen.getByText('证据不足')).toBeInTheDocument()
    expect(screen.getByText('资金不足一手')).toBeInTheDocument()
    expect(screen.getByText(/不足以买入 A 股最小的 100 股整手/)).toBeInTheDocument()
  })

  it('compares the exact historical 2x2 matrix without conflating online Top3', async () => {
    render(
      <App
        client={clientFor(
          snapshot({
            historical_backtests: [historicalBacktest, historicalTop3Backtest, finalTestHistoricalBacktest, finalTestHistoricalTop3Backtest],
            historical_backtest_available: true,
            historical_backtest_series: {
              [historicalBacktest.id]: [
                { session: '2025-01-02', strategy: 0, benchmark: 0, excess: 0, strategy_nav: 1, benchmark_nav: 1 },
                { session: '2025-12-31', strategy: 0.12, benchmark: 0.08, excess: 0.04, strategy_nav: 1.12, benchmark_nav: 1.08 },
              ],
              [finalTestHistoricalBacktest.id]: [
                { session: '2026-01-05', strategy: 0, benchmark: 0, excess: 0, strategy_nav: 1, benchmark_nav: 1 },
                { session: '2026-07-29', strategy: 0.04, benchmark: 0.03, excess: 0.01, strategy_nav: 1.04, benchmark_nav: 1.03 },
              ],
              [historicalTop3Backtest.id]: [
                { session: '2025-01-02', strategy: 0, benchmark: 0, excess: 0, strategy_nav: 1, benchmark_nav: 1 },
                { session: '2025-12-31', strategy: 0.1, benchmark: 0.08, excess: 0.02, strategy_nav: 1.1, benchmark_nav: 1.08 },
              ],
              [finalTestHistoricalTop3Backtest.id]: [
                { session: '2026-01-05', strategy: 0, benchmark: 0, excess: 0, strategy_nav: 1, benchmark_nav: 1, turnover: 0.02, position_count: 2 },
                { session: '2026-07-29', strategy: 0.06, benchmark: 0.03, excess: 0.03, strategy_nav: 1.06, benchmark_nav: 1.03, turnover: 0.04, position_count: 4 },
              ],
            },
          }),
        )}
      />,
    )
    fireEvent.click(await screen.findByRole('button', { name: '历史回测' }))
    expect(screen.getByRole('heading', { name: /历史组合.*对照回测/ })).toBeInTheDocument()
    expect(screen.getByText('在线 Top3 模拟账户')).toBeInTheDocument()
    expect(screen.getByText(/历史 Top3 不等同在线 Top3/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Strict PIT/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /官方对齐 Top50/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/已修正未来成分\/\u7f3a行条件/)).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /官方对齐Top50、历史Qlib Top3与沪深300/ })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /历史 Qlib Top3/ }))
    expect(screen.getByText(/2026 窗口已开封.*不用于选模/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '历史 Top3 组合参数' })).toBeInTheDocument()
    expect(screen.getByText('2 – 4 只，中位数 3')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /2025 训练验证/ }))
    expect(screen.getByText(/2025 已在查看后构建.*不用于选模/)).toBeInTheDocument()
  })

  it('routes the removed methods hash back to overview', async () => {
    window.history.replaceState(null, '', '#/methods')
    render(<App client={clientFor(snapshot())} />)
    expect(await screen.findByRole('heading', { name: '更新数据，生成今天的研究结果' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '方法说明' })).not.toBeInTheDocument()
  })

  it('filters retired Strict PIT backtests before choosing a fallback model', async () => {
    render(
      <App
        client={clientFor(
          snapshot({
            historical_backtests: [
              {
                ...historicalBacktest,
                id: 'retired-small-strict-pit',
                model_cell_id: 'small-strict-pit',
              },
            ],
            historical_backtest_available: true,
          }),
        )}
      />,
    )
    fireEvent.click(await screen.findByRole('button', { name: '历史回测' }))
    expect(screen.getByText('官方对齐回测正在服务器生成')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Strict PIT/ })).not.toBeInTheDocument()
  })

  it('loads sealed holdings by keyboard-accessible session and keeps legacy empty state honest', async () => {
    const client = clientFor(snapshot({
      historical_backtests: [finalTestHistoricalBacktest, finalTestHistoricalTop3Backtest],
      historical_backtest_available: true,
      historical_backtest_series: {
        [finalTestHistoricalBacktest.id]: [
          { session: '2026-07-28', strategy: 0.03, benchmark: 0.02, excess: 0.01, strategy_nav: 1.03, benchmark_nav: 1.02 },
          { session: '2026-07-29', strategy: 0.04, benchmark: 0.03, excess: 0.01, strategy_nav: 1.04, benchmark_nav: 1.03 },
        ],
        [finalTestHistoricalTop3Backtest.id]: [
          { session: '2026-07-28', strategy: 0.05, benchmark: 0.02, excess: 0.03, strategy_nav: 1.05, benchmark_nav: 1.02 },
          { session: '2026-07-29', strategy: 0.06, benchmark: 0.03, excess: 0.03, strategy_nav: 1.06, benchmark_nav: 1.03 },
        ],
      },
    }))
    client.getHistoricalHoldings = vi.fn(async (backtestId: string, session?: string) => {
      if (backtestId === finalTestHistoricalBacktest.id) return null
      const selected = session ?? '2026-07-29'
      return {
        backtest_id: finalTestHistoricalTop3Backtest.id,
        available: true,
        signal: 'mean',
        empty: false,
        sessions: ['2026-07-28', '2026-07-29'],
        default_session: '2026-07-29',
        selected_session: selected,
        source: { artifact_sha256: 'a'.repeat(64), receipt_sha256: 'b'.repeat(64), backtest_receipt_sha256: 'c'.repeat(64) },
        holdings: selected === '2026-07-29'
          ? [
              { instrument: 'SH600000', amount: 1_000, weight: 0.6, value: 12_500 },
              { instrument: 'SZ000001', amount: 800, weight: 0.4, value: 8_100 },
            ]
          : [{ instrument: 'SH600000', amount: 900, weight: 1, value: 11_000 }],
      } satisfies HistoricalHoldingsSnapshot
    })

    render(<App client={client} />)
    fireEvent.click(await screen.findByRole('button', { name: '历史回测' }))
    expect(await screen.findByText('该回测没有封存持仓工件')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /历史 Qlib Top3/ }))
    const sessionSelect = await screen.findByRole('combobox', { name: '持仓交易日' })
    expect(screen.getByRole('rowheader', { name: 'SH600000' })).toBeInTheDocument()
    expect(screen.getByText('2 只')).toBeInTheDocument()
    expect(screen.getByText('3 只')).toBeInTheDocument()
    expect(screen.getByText(/实际持仓数与目标不同/)).toBeInTheDocument()

    fireEvent.change(sessionSelect, { target: { value: '2026-07-28' } })
    await waitFor(() => expect(screen.getByText('900')).toBeInTheDocument())
    expect(client.getHistoricalHoldings).toHaveBeenCalledWith(
      finalTestHistoricalTop3Backtest.id,
      '2026-07-28',
      expect.any(AbortSignal),
    )
  })
})
