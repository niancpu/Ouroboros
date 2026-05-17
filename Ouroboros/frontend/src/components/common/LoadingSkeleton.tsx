interface LoadingSkeletonProps {
  label?: string;
}

export function LoadingSkeleton({ label }: LoadingSkeletonProps) {
  return (
    <div className="loading-skeleton" role="status" aria-live="polite">
      <div className="loading-line" />
      <div className="loading-line" />
      <div className="loading-line" />
      {label && (
        <span className="loading-label">
          {label}
          <span className="loading-dots" aria-hidden="true" />
        </span>
      )}
    </div>
  );
}
