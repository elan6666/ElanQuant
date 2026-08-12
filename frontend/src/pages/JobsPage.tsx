import { Badge } from '../components/Badge'
import { EmptyState } from '../components/EmptyState'
import { JobProgress } from '../components/JobProgress'
import { formatDateTime, jobStateLabel, stageLabel } from '../format'
import type { Job } from '../types'

export function JobsPage({ jobs, submitting, onRetry }: { jobs: Job[]; submitting: boolean; onRetry: (id: string) => void }) {
  if (jobs.length === 0) {
    return (
      <PageFrame>
        <EmptyState title="还没有服务器任务" description="任务只由总览页的主按钮创建。提交后可关闭浏览器；VPN断连存活能力需先通过服务器linger部署验证。" />
      </PageFrame>
    )
  }

  return (
    <PageFrame>
      <div className="jobs-layout">
        <JobProgress job={jobs[0]!} />
        <div className="job-history">
          <div className="section-heading">
            <div><span className="eyebrow">Durable history</span><h2>不可变任务记录</h2></div>
            <span className="count-label">{jobs.length} JOBS</span>
          </div>
          {jobs.map((job) => (
            <article className="history-row" key={job.id}>
              <div className="history-row__main">
                <code>{job.id}</code>
                <strong>{stageLabel[job.stage]}</strong>
                <span>{formatDateTime(job.requested_at)} · {job.as_of || '交易日待确认'}</span>
                {job.run_id ? <small>OUTPUT RUN · {job.run_id}</small> : null}
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
        <h1>任务与运行阶段</h1>
        <p>网页只负责提交和查看；服务器Worker独立领取任务。断开VPN前，部署页必须已确认linger和断连恢复测试通过。</p>
      </header>
      {children}
    </>
  )
}
