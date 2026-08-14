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

export const formatPrice = (value: number): string =>
  new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
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

const paperDecisionLabels: Record<string, string> = {
  ORDER_FROZEN: '订单已冻结',
  HELD_EXISTING_POSITION: '已有持仓',
  SKIPPED_PENDING_ORDER: '已有待执行订单',
  SKIPPED_BELOW_BOARD_LOT: '资金不足一手',
  PAPER_PUBLICATION_SKIPPED: '同日重算不改账本',
  LEGACY_NO_ORDER_UNCLASSIFIED: '历史原因未分类',
}

const paperDecisionReasons: Record<string, string> = {
  ORDER_FROZEN: '已按 T 日收盘时可知的信息冻结，等待下一真实交易日执行。',
  HELD_EXISTING_POSITION: '信号冻结时账户已经持有该股票，因此没有新增买单。',
  SKIPPED_PENDING_ORDER: '已有一笔不可改写的待执行订单，因此不重复下单。',
  SKIPPED_BELOW_BOARD_LOT: '等权现金份额不足以买入 A 股最小的 100 股整手。',
  PAPER_PUBLICATION_SKIPPED: '该信号日已由更早的运行冻结；本次只保留研究结果。',
  LEGACY_NO_ORDER_UNCLASSIFIED: '这条历史记录早于显式决策回执，系统保留原状而不猜测原因。',
}

export const paperDecisionLabel = (decision: string | null | undefined): string =>
  decision ? paperDecisionLabels[decision] ?? decision : '尚无回执'

export const paperDecisionReason = (
  decision: string | null | undefined,
  fallback: string | null | undefined,
): string =>
  (decision ? paperDecisionReasons[decision] : undefined) ?? fallback ?? '尚无可解释回执。'
