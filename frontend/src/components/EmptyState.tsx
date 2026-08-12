interface EmptyStateProps {
  eyebrow?: string
  title: string
  description: string
}

export function EmptyState({ eyebrow = '等待证据', title, description }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <span className="eyebrow">{eyebrow}</span>
      <div className="empty-state__mark" aria-hidden="true">
        00
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  )
}
