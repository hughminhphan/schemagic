import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

type Variant = "accent" | "secondary";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

const base =
  "inline-flex items-center justify-center font-sans font-medium text-body leading-none " +
  "px-6 py-3 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent " +
  "disabled:opacity-40 disabled:cursor-not-allowed";

const variants: Record<Variant, string> = {
  accent: "bg-accent text-text-primary hover:bg-accent-hover",
  secondary:
    "bg-surface-raised text-text-primary border-2 border-border hover:border-text-secondary",
};

export function Button({
  variant = "accent",
  className,
  children,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button type={type} className={cn(base, variants[variant], className)} {...props}>
      {children}
    </button>
  );
}
