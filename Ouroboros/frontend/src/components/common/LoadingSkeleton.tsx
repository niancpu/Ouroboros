interface LoadingSkeletonProps {
  label?: string;
}

export function LoadingSkeleton({ label }: LoadingSkeletonProps) {
  return (
    <div className="loading-skeleton" role="status">
      <div className="loading-line" />
      <div className="loading-line" />
      <div className="loading-line" />
      {label && <span className="loading-label">{label}</span>}
    </div>
  );
}
