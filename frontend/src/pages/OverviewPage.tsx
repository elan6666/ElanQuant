import { useState } from 'react'
import { formatDateTime, formatSession, shortHash } from '../format'
import type {
  DashboardSnapshot,
  ExecutionLocation,
  ExecutionProfile,
  SubmitJobReceipt,
} from '../types'
import { Badge } from '../components/Badge'
import { EmptyState } from '../components/EmptyState'
import { JobProgress } from '../components/JobProgress'
import { Metric } from '../components/Metric'
import { MetricHelp } from '../components/MetricHelp'

interface OverviewPageProps {
  snapshot: DashboardSnapshot
  submitting: boolean
  receipt: SubmitJobReceipt | null
  onSubmit: (profile: ExecutionProfile) => void
}

export function OverviewPage({ snapshot, submitting, receipt, onSubmit }: OverviewPageProps) {
  const [selectedLocation, setSelectedLocation] = useState<ExecutionLocation>(
    snapshot.system.default_execution_location,
  )
  const activeJob = snapshot.jobs.find((job) => job.state === 'queued' || job.state === 'running')
  const latestJob = snapshot.jobs[0]
  const latestRun = snapshot.latest_run
  const isStale = Boolean(
    latestRun &&
      (latestRun.status === 'stale' || latestRun.as_of !== snapshot.system.latest_closed_session),
  )
  const blockedJob = latestJob?.state === 'data_incomplete' ? latestJob : null
  const fallbackLocation = (['local', 'remote'] as const).find(
    (location) => snapshot.system.execution_profiles[location].available,
  )
  const activeLocation = snapshot.system.execution_profiles[selectedLocation].available
    ? selectedLocation
    : fallbackLocation
  const activeProfile = activeLocation
    ? snapshot.system.execution_profiles[activeLocation].profile_id
    : null

  return (
    <>
      <section className="hero">
        <div className="hero__copy">
          <span className="eyebrow">收盘后按需运行</span>
          <h1>更新数据，生成今天的研究结果</h1>
          <p>选择运行位置后，系统会检查最新收盘数据，并生成股票排名和模拟账户记录。</p>
        </div>
        <div className="hero__action">
          <span className="hero__action-index">RUN / 01</span>
          <fieldset className="profile-picker">
            <legend>运行位置</legend>
            {(['local', 'remote'] as const).map((location) => {
              const availability = snapshot.system.execution_profiles[location]
              return (
                <button
                  aria-pressed={activeLocation === location}
                  disabled={!availability.available || submitting || Boolean(activeJob)}
                  key={location}
                  onClick={() => setSelectedLocation(location)}
                  type="button"
                >
                  <strong>{location === 'local' ? '本机' : '远程服务器'}</strong>
                  <small>
                    {availability.available
                      ? location === 'local'
                        ? '这台 Mac · 默认 Small'
                        : '已配置的 GPU 主机'
                      : availability.reason || '未配置'}
                  </small>
                </button>
              )
            })}
          </fieldset>
          <button
            className="primary-action"
            type="button"
            onClick={() => activeProfile && onSubmit(activeProfile)}
            disabled={submitting || Boolean(activeJob) || !activeProfile}
          >
            <span>
              {submitting
                ? '正在提交…'
                : activeJob
                  ? '任务正在运行'
                  : activeLocation === 'local'
                    ? '用本机更新并推理'
                    : '提交到远程服务器'}
            </span>
            <b aria-hidden="true">↗</b>
          </button>
          <small>
            {activeJob
              ? '任务已提交，可以离开此页面；稍后到“任务”查看进度。'
              : '不会重新训练模型，不会连接真实账户；重复点击会合并为同一任务。'}
          </small>
          <a className="reproduction-link" href="https://github.com/elan6666/ElanQuant#选择运行位置" rel="noreferrer" target="_blank">第一次使用？查看 README 复现指南 ↗</a>
          {receipt ? (
            <div className="receipt-note" role="status">
              {receipt.coalesced
                ? '已复用正在运行的任务'
                : `${activeLocation === 'local' ? '本机' : '远程服务器'}已接受任务`} · {receipt.job_id}
            </div>
          ) : null}
        </div>
      </section>

      <section className="risk-strip" aria-label="风险提示">
        <strong>模拟研究</strong>
        <span>无真实账户</span>
        <span>无真实订单</span>
        <span>不构成投资建议</span>
        <span>最新在线预测尚未拥有未来10日标签</span>
      </section>

      <section className="metric-grid">
        <Metric label="最近已验证数据日" value={formatSession(snapshot.system.latest_closed_session)} detail="来自封存快照；按钮刷新后才能确认市场最新性" />
        <Metric label={`${activeLocation === 'local' ? '本机' : '远程'}数据截止`} value={formatSession(snapshot.system.data_as_of)} detail="完整性通过后才可推理" />
        <Metric label="最近推理日期" value={formatSession(snapshot.system.inference_as_of)} detail={isStale ? '早于最近已验证快照' : '与最近已验证快照一致'} />
        <Metric label="当前研究版本" value={snapshot.system.primary_model ? '已封存' : '尚未选择'} detail="精确模型身份见下方审计信息" />
      </section>

      {latestRun?.data_health ? (
        <section className="data-health-strip">
          <div><span className="eyebrow">Data health / 数据健康</span><h2>{latestRun.data_health.eligible_symbols ?? '—'} / {latestRun.data_health.membership_count ?? '—'} 只通过准入</h2></div>
          <dl>
            <div><dt>收盘终值化</dt><dd>{latestRun.data_health.generated_after_market_finalization ? 'PASS' : 'UNPROVEN'}</dd></div>
            <div><dt>排除数</dt><dd>{Object.values(latestRun.data_health.excluded_counts).reduce((sum, count) => sum + count, 0)}</dd></div>
            <div><dt>成分可用日</dt><dd>{latestRun.data_health.membership_available_session || '—'}</dd></div>
            <div><dt>快照逻辑</dt><dd><code>{shortHash(latestRun.data_health.snapshot_logic_sha256)}</code></dd></div>
          </dl>
          <p>{latestRun.data_health.membership_revision_limitation || '当前快照未记录成分修订限制。'}</p>
          {latestRun.data_health.transport_caveat ? <small>{latestRun.data_health.transport_caveat}</small> : null}
          <MetricHelp
            title="数据数字怎么算"
            items={[
              { term: '通过准入', description: '符合本次数据要求的股票数 ÷ 当日成分股票总数。' },
              { term: '排除数', description: '各类不完整或不合格输入的排除数量合计。' },
            ]}
          />
        </section>
      ) : null}

      {snapshot.system.warnings.length > 0 ? (
        <section className="warning-panel">
          <span className="eyebrow">系统警告</span>
          {snapshot.system.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </section>
      ) : null}

      {blockedJob ? (
        <section className="state-panel state-panel--warning">
          <div>
            <Badge state="data_incomplete">数据不完整</Badge>
            <h2>本次运行已安全停止</h2>
          </div>
          <p>{blockedJob.message || '数据覆盖率或字段完整性未通过。系统没有生成新的股票推荐。'}</p>
          <code>{blockedJob.error_code || 'DATA_INCOMPLETE'}</code>
        </section>
      ) : null}

      {activeJob ? (
        <section className="content-section">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Live job</span>
              <h2>{activeJob.execution_profile === 'local-apple-silicon' ? '本机正在工作' : '远程服务器正在工作'}</h2>
            </div>
            <Badge state={activeJob.state}>{activeJob.state === 'queued' ? '等待开始' : '运行中'}</Badge>
          </div>
          <JobProgress job={activeJob} compact />
        </section>
      ) : null}

      <section className="content-section">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Latest evidence</span>
              <h2>最近研究结果</h2>
            </div>
            {latestRun ? <Badge tone={isStale ? 'stale' : 'success'}>{isStale ? '历史快照' : '已验证快照'}</Badge> : null}
          </div>
          {latestRun ? (
            <>
              <div className="evidence-list evidence-list--summary">
                <div><span>As-of</span><strong>{latestRun.as_of}</strong></div>
                <div><span>发布于</span><strong>{formatDateTime(latestRun.created_at)}</strong></div>
                <div><span>评估身份</span><strong>{latestRun.scoreable ? '已拥有10日标签' : '在线预测 · 尚不可评分'}</strong></div>
                <div><span>运行位置</span><strong>{latestJob?.execution_profile === 'local-apple-silicon' ? '本机' : '远程服务器'}</strong></div>
              </div>
              <details className="audit-details">
                <summary>查看审计信息</summary>
                <div className="evidence-list">
                  <div><span>模型</span><strong>{latestRun.model_id}</strong></div>
                  <div><span>数据Hash</span><code title={latestRun.data_hash}>{shortHash(latestRun.data_hash)}</code></div>
                  <div><span>模型Hash</span><code title={latestRun.model_hash}>{shortHash(latestRun.model_hash)}</code></div>
                  <div><span>Tokenizer Hash</span><code title={latestRun.tokenizer_hash}>{shortHash(latestRun.tokenizer_hash)}</code></div>
                  <div><span>配置Hash</span><code title={latestRun.config_hash}>{shortHash(latestRun.config_hash)}</code></div>
                  <div><span>代码Hash</span><code title={latestRun.code_hash}>{shortHash(latestRun.code_hash)}</code></div>
                  <div><span>评估Hash</span><code title={latestRun.evaluation_hash}>{shortHash(latestRun.evaluation_hash)}</code></div>
                </div>
              </details>
            </>
          ) : (
            <EmptyState title="还没有推理结果" description="第一次点击主按钮后，已配置的运行位置会生成真实结果；页面不会用示例数据冒充成功。" />
          )}
      </section>
    </>
  )
}
