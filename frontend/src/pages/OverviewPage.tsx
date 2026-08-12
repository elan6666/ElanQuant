import { formatDateTime, formatSession, shortHash } from '../format'
import type { DashboardSnapshot, SubmitJobReceipt } from '../types'
import { Badge } from '../components/Badge'
import { EmptyState } from '../components/EmptyState'
import { JobProgress } from '../components/JobProgress'
import { Metric } from '../components/Metric'

interface OverviewPageProps {
  snapshot: DashboardSnapshot
  submitting: boolean
  receipt: SubmitJobReceipt | null
  onSubmit: () => void
}

export function OverviewPage({ snapshot, submitting, receipt, onSubmit }: OverviewPageProps) {
  const activeJob = snapshot.jobs.find((job) => job.state === 'queued' || job.state === 'running')
  const latestJob = snapshot.jobs[0]
  const latestRun = snapshot.latest_run
  const isStale = Boolean(
    latestRun &&
      (latestRun.status === 'stale' || latestRun.as_of !== snapshot.system.latest_closed_session),
  )
  const blockedJob = latestJob?.state === 'data_incomplete' ? latestJob : null

  return (
    <>
      <section className="hero">
        <div className="hero__copy">
          <span className="eyebrow">Owner workflow / 收盘后按需运行</span>
          <h1>
            让每一次推理，
            <em>留下可复核的证据。</em>
          </h1>
          <p>
            更新服务器行情，验证严格PIT边界，运行Kronos Small三条实验轨，最后冻结股票排名和模拟订单。
          </p>
        </div>
        <div className="hero__action">
          <span className="hero__action-index">RUN / 01</span>
          <button
            className="primary-action"
            type="button"
            onClick={onSubmit}
            disabled={submitting || Boolean(activeJob)}
          >
            <span>{submitting ? '正在提交…' : activeJob ? '任务正在服务器运行' : '更新数据并运行推理'}</span>
            <b aria-hidden="true">↗</b>
          </button>
          <small>
            {activeJob
              ? '任务已写入服务器。关闭网页不影响任务；断开最后一个SSH会话后的持续运行，要以服务器linger部署检查为准。'
              : '不会重新训练模型，不会连接真实账户；重复点击会合并为同一任务。'}
          </small>
          {receipt ? (
            <div className="receipt-note" role="status">
              {receipt.coalesced ? '已复用正在运行的任务' : '服务器已接受任务'} · {receipt.job_id}
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
        <Metric label="最近已收盘交易日" value={formatSession(snapshot.system.latest_closed_session)} detail="LATEST_CLOSED_SESSION" />
        <Metric label="服务器数据截止" value={formatSession(snapshot.system.data_as_of)} detail="完整性通过后才可推理" />
        <Metric label="最近推理日期" value={formatSession(snapshot.system.inference_as_of)} detail={isStale ? '历史结果 · 已过期' : '当前结果'} />
        <Metric label="生产候选" value={snapshot.system.primary_model || '尚未选择'} detail="只由验证集结果决定" />
      </section>

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
              <h2>服务器正在工作</h2>
            </div>
            <Badge state={activeJob.state}>{activeJob.state === 'queued' ? '等待Worker' : '运行中'}</Badge>
          </div>
          <JobProgress job={activeJob} compact />
        </section>
      ) : null}

      <section className="two-column">
        <div className="content-section">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Latest evidence</span>
              <h2>最近研究结果</h2>
            </div>
            {latestRun ? <Badge tone={isStale ? 'stale' : 'success'}>{isStale ? '历史 / 过期' : '最新'}</Badge> : null}
          </div>
          {latestRun ? (
            <div className="evidence-list">
              <div><span>As-of</span><strong>{latestRun.as_of}</strong></div>
              <div><span>模型</span><strong>{latestRun.model_id}</strong></div>
              <div><span>数据Hash</span><code title={latestRun.data_hash}>{shortHash(latestRun.data_hash)}</code></div>
              <div><span>模型Hash</span><code title={latestRun.model_hash}>{shortHash(latestRun.model_hash)}</code></div>
              <div><span>发布于</span><strong>{formatDateTime(latestRun.created_at)}</strong></div>
              <div><span>评估身份</span><strong>{latestRun.scoreable ? '已拥有10日标签' : '在线预测 · 尚不可评分'}</strong></div>
            </div>
          ) : (
            <EmptyState title="还没有推理结果" description="第一次点击主按钮后，服务器会生成真实结果；页面不会用示例数据冒充成功。" />
          )}
        </div>

        <div className="content-section onboarding-card">
          <span className="eyebrow">First run / 第一次使用</span>
          <h2>连接只是入口，不是任务电源</h2>
          <ol>
            <li><b>01</b><span>先连接学校 EasyConnect，再建立SSH本地隧道。</span></li>
            <li><b>02</b><span>打开本页面，点击一次“更新数据并运行推理”。</span></li>
            <li><b>03</b><span>收到任务编号后可以关闭网页；先确认服务器已通过linger/断连测试，再主动断开VPN。</span></li>
            <li><b>04</b><span>稍后重连，任务页会从服务器恢复真实进度与结果。</span></li>
          </ol>
        </div>
      </section>
    </>
  )
}
