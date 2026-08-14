import { formatDateTime, jobStateLabel, stageLabel } from '../format'
import type { Job, JobStage } from '../types'
import { Badge } from './Badge'

const commonStages: JobStage[] = [
  'queued',
  'resolving_session',
  'updating_data',
  'validating_data',
]

export function JobProgress({ job, compact = false }: { job: Job; compact?: boolean }) {
  const isBaseResearch =
    job.stage === 'infer_base' ||
    job.stage === 'research_only' ||
    job.events.some((event) => event.stage === 'infer_base' || event.stage === 'research_only')
  const orderedStages: JobStage[] = [
    ...commonStages,
    isBaseResearch ? 'infer_base' : 'infer_small',
    'scoring',
    isBaseResearch ? 'research_only' : 'paper_ledger',
    'completed',
  ]
  const activeIndex = orderedStages.indexOf(job.stage)
  return (
    <article className={`job-progress ${compact ? 'job-progress--compact' : ''}`}>
      <div className="job-progress__head">
        <div>
          <span className="eyebrow">任务 {job.id.slice(0, 12)}</span>
          <h3>{stageLabel[job.stage]}</h3>
        </div>
        <Badge state={job.state}>{jobStateLabel[job.state]}</Badge>
      </div>

      <div
        aria-label={`任务进度 ${Math.round(job.progress * 100)}%`}
        aria-valuemax={100}
        aria-valuemin={0}
        aria-valuenow={Math.round(job.progress * 100)}
        className="progress-track"
        role="progressbar"
      >
        <span style={{ width: `${Math.min(100, Math.max(0, job.progress * 100))}%` }} />
      </div>

      <div className="job-progress__meta">
        <span>提交 {formatDateTime(job.requested_at)}</span>
        <span>数据日 {job.as_of || '确认中'}</span>
        <span>{Math.round(job.progress * 100)}%</span>
      </div>
      <small className="progress-note">进度表示已完成阶段占全部阶段的比例，不是预计剩余时间。</small>

      {job.message ? <p className="job-progress__message">{job.message}</p> : null}

      {!compact ? (
        <ol className="stage-list">
          {orderedStages.map((stage, index) => {
            const done = index < activeIndex || job.state === 'succeeded'
            const active = stage === job.stage && job.state !== 'succeeded'
            return (
              <li className={done ? 'is-done' : active ? 'is-active' : ''} key={stage}>
                <span>{done ? '✓' : String(index + 1).padStart(2, '0')}</span>
                {stageLabel[stage]}
              </li>
            )
          })}
        </ol>
      ) : null}
    </article>
  )
}
