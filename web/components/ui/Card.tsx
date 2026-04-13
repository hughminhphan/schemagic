import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  header?: ReactNode;
  children: ReactNode;
}

export function Card({ header, children, className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "bg-surface-raised border border-border flex flex-col",
        className,
      )}
      {...props}
    >
      {header ? (
        <div className="border-b border-border px-6 py-4 font-mono text-mono-label uppercase tracking-wider text-text-secondary">
          {header}
        </div>
      ) : null}
      <div className="flex flex-col">{children}</div>
    </div>
  );
}

export interface CardRowProps extends HTMLAttributes<HTMLDivElement> {
  label: ReactNode;
  value: ReactNode;
}

export function CardRow({ label, value, className, ...props }: CardRowProps) {
  return (
    <div
      className={cn(
        "flex items-center justify-between px-6 py-4 border-b border-border last:border-b-0",
        className,
      )}
      {...props}
    >
      <span className="font-sans text-body text-text-secondary">{label}</span>
      <span className="font-sans text-body text-text-primary">{value}</span>
    </div>
  );
}
