import type { ExperimentState, JobStage, JobState } from './types'

export const formatDateTime = (value: string | null | undefined): string => {
  if (!value) return '尚无记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

export const formatSession = (value: string | null | undefined): string => value || '—'

export const formatPercent = (value: number | null | undefined, digits = 2): string =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`

export const formatNumber = (value: number | null | undefined, digits = 3): string =>
  value === null || value === undefined ? '—' : value.toFixed(digits)

export const formatMoney = (value: number): string =>
  new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    maximumFractionDigits: 0,
  }).format(value)

export const shortHash = (value: string | null | undefined): string =>
  value ? `${value.slice(0, 8)}…${value.slice(-6)}` : '—'

export const jobStateLabel: Record<JobState, string> = {
  queued: '等待中',
  running: '运行中',
  data_incomplete: '数据不完整',
  failed: '失败',
  interrupted: '已中断',
  succeeded: '已完成',
}

export const stageLabel: Record<JobStage, string> = {
  queued: '进入队列',
  resolving_session: '确认最近交易日',
  updating_data: '更新行情数据',
  validating_data: '验证数据与PIT',
  infer_small: 'Small模型推理',
  scoring: '计算评分与排名',
  paper_ledger: '冻结模拟订单',
  completed: '发布结果',
}

export const experimentStateLabel: Record<ExperimentState, string> = {
  pending: '待运行',
  running: '训练 / 评估中',
  passed: '已完成',
  failed: '失败',
  blocked: '未通过准入',
}
