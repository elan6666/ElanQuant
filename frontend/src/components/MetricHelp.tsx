export interface MetricDefinition {
  term: string
  description: string
}

export function MetricHelp({
  items,
  title = '查看指标口径',
}: {
  items: MetricDefinition[]
  title?: string
}) {
  return (
    <details className="metric-help">
      <summary>{title}</summary>
      <dl>
        {items.map((item) => (
          <div key={item.term}>
            <dt>{item.term}</dt>
            <dd>{item.description}</dd>
          </div>
        ))}
      </dl>
    </details>
  )
}
