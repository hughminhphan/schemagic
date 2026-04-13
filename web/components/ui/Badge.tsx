import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

type Variant = "pro" | "free" | "error" | "success";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: Variant;
  children: ReactNode;
}

const variants: Record<Variant, string> = {
  pro: "bg-accent text-text-primary",
  free: "bg-surface-raised text-text-secondary border border-border",
  error: "bg-surface-raised text-accent border border-accent",
  success: "bg-surface-raised text-success border border-success",
};

export function Badge({
  variant = "free",
  className,
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-3 py-1 font-mono text-mono-xs uppercase tracking-wider",
        variants[variant],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}
