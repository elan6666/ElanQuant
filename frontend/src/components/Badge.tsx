import type { ExperimentState, JobState } from '../types'

type BadgeTone = 'neutral' | 'running' | 'success' | 'danger' | 'warning' | 'stale'

const stateTone = (state: JobState | ExperimentState): BadgeTone => {
  if (state === 'running') return 'running'
  if (state === 'succeeded' || state === 'passed') return 'success'
  if (state === 'failed' || state === 'interrupted') return 'danger'
  if (state === 'data_incomplete' || state === 'blocked') return 'warning'
  return 'neutral'
}

interface BadgeProps {
  children: React.ReactNode
  tone?: BadgeTone
  state?: JobState | ExperimentState
}

export function Badge({ children, tone = 'neutral', state }: BadgeProps) {
  return <span className={`badge badge--${state ? stateTone(state) : tone}`}>{children}</span>
}
