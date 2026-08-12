interface MetricProps {
  label: string
  value: string
  detail?: string
  tone?: 'default' | 'positive' | 'negative'
}

export function Metric({ label, value, detail, tone = 'default' }: MetricProps) {
  return (
    <div className={`metric metric--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  )
}
