interface EmptyStateProps {
  label: string;
}

export function EmptyState({ label }: EmptyStateProps) {
  return <div className="empty-state">{label}</div>;
}
