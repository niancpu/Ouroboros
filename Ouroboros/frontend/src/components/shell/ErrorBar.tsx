import { apiErrorCodeLabels, labelFrom } from "../../i18n/labels";

interface ErrorBarProps {
  code: string;
  message: string;
  onDismiss?: () => void;
}

export function ErrorBar({ code, message, onDismiss }: ErrorBarProps) {
  const codeLabel = labelFrom(apiErrorCodeLabels, code) || code;
  return (
    <div className="error-bar" role="alert">
      <span className="error-bar-code">[{codeLabel}]</span>
      <span className="error-bar-message">{message}</span>
      {onDismiss && (
        <button type="button" className="error-bar-dismiss" onClick={onDismiss}>
          ×
        </button>
      )}
    </div>
  );
}
