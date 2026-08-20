import { Badge } from '../components/Badge'
import { EmptyState } from '../components/EmptyState'
import { JobProgress } from '../components/JobProgress'
import { formatDateTime, jobStateLabel, stageLabel } from '../format'
import type { CrossModelComparison, Job } from '../types'

export function JobsPage({ jobs, comparison, submitting, onRetry }: { jobs: Job[]; comparison?: CrossModelComparison; submitting: boolean; onRetry: (id: string) => void }) {
  if (jobs.length === 0) {
    return (
      <PageFrame>
        {comparison?.available ? <section className="state-panel"><span className="eyebrow">Imported model evidence</span><h2>并列模型研究证据</h2><p>iTransformer B2 与 Kronos Base 的严格周频回执已导入；这不是在线任务。</p></section> : null}
        <EmptyState title="还没有任务" description="从总览启动一次推理后，任务会显示在这里。" />
      </PageFrame>
    )
  }

  return (
    <PageFrame>
      <div className="jobs-layout">
        {comparison?.available ? <section className="state-panel"><span className="eyebrow">Imported model evidence</span><h2>并列模型研究证据</h2><p>iTransformer B2 与 Kronos Base 的严格周频回执已导入；这是封存历史研究，不是在线任务或模拟账户订单。</p><div className="matrix-key">{comparison.models.map((model) => <div key={model.id}><b>{model.family === 'itransformer_b2' ? 'B2' : 'KB'}</b><span><strong>{model.label}</strong><small>过去 {model.input.lookback_sessions} 个交易日输入 · {comparison.protocol?.signal_end} 最新封存锚点</small></span></div>)}</div></section> : null}
        <JobProgress job={jobs[0]!} />
        <div className="job-history">
          <div className="section-heading">
            <div><span className="eyebrow">History</span><h2>历史任务</h2></div>
            <span className="count-label">{jobs.length} JOBS</span>
          </div>
          {jobs.map((job) => (
            <article className="history-row" key={job.id}>
              <div className="history-row__main">
                <code>{job.id}</code>
                <strong>{stageLabel[job.stage]}</strong>
                <span>{formatDateTime(job.requested_at)} · {job.as_of || '交易日待确认'}</span>
                <small>运行位置 · {job.execution_profile === 'local-apple-silicon' ? '本机' : '远程服务器'}</small>
                {job.run_id ? <small>结果编号 · {job.run_id}</small> : null}
              </div>
              <div className="history-row__state">
                <Badge state={job.state}>{jobStateLabel[job.state]}</Badge>
                {job.coalesced ? <small>重复请求已合并</small> : null}
              </div>
              {['failed', 'interrupted', 'data_incomplete'].includes(job.state) ? (
                <button className="outline-button" type="button" onClick={() => onRetry(job.id)} disabled={submitting}>
                  明确重试
                </button>
              ) : null}
              {job.events.length > 0 ? (
                <details>
                  <summary>查看 {job.events.length} 条事件</summary>
                  <ol className="event-log">
                    {job.events.map((event) => (
                      <li key={event.id}>
                        <time>{formatDateTime(event.created_at)}</time>
                        <b>{stageLabel[event.stage]}</b>
                        <span>{event.message}</span>
                      </li>
                    ))}
                  </ol>
                </details>
              ) : null}
            </article>
          ))}
        </div>
      </div>
    </PageFrame>
  )
}

function PageFrame({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="page-heading">
        <span className="eyebrow">02 / Jobs</span>
        <h1>任务进度</h1>
        <p>这里显示每次更新的进度和结果。</p>
      </header>
      {children}
    </>
  )
}
