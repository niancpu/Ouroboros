import type { ReactNode } from "react";

interface IconButtonProps {
  label: string;
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
}

export function IconButton({
  label,
  onClick,
  children,
  disabled = false,
  type = "button",
}: IconButtonProps) {
  return (
    <button
      className="icon-button"
      type={type}
      onClick={onClick}
      title={label}
      aria-label={label}
      disabled={disabled}
    >
      {children}
    </button>
  );
}
