import type { ReactNode } from "react";

type StatusVariant = "info" | "success" | "error" | "neutral";

interface StatusMessageProps {
  message?: ReactNode;
  variant?: StatusVariant;
  className?: string;
}

const variantStyles: Record<StatusVariant, string> = {
  info: "text-slate-600",
  success: "text-emerald-600",
  error: "text-rose-600",
  neutral: "text-slate-500",
};

export function StatusMessage({ message, variant = "info", className }: StatusMessageProps) {
  if (!message) {
    return null;
  }

  const style = `${variantStyles[variant]} ${className ?? ""}`.trim();

  return (
    <p role="status" className={style}>
      {message}
    </p>
  );
}
