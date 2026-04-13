import type { InputHTMLAttributes } from "react";
import { cn } from "./cn";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  caret?: boolean;
}

export function Input({
  label,
  error,
  caret = false,
  className,
  id,
  ...props
}: InputProps) {
  const inputId = id ?? (label ? `input-${label.toLowerCase().replace(/\s+/g, "-")}` : undefined);
  return (
    <div className="flex flex-col gap-3 w-full">
      {label ? (
        <label
          htmlFor={inputId}
          className="font-mono text-mono-label uppercase tracking-wide text-text-secondary"
        >
          {label}
        </label>
      ) : null}
      <div
        className={cn(
          "flex items-center gap-6 bg-surface-raised border-2 px-6 py-4 w-full",
          error ? "border-accent" : "border-border focus-within:border-accent",
        )}
      >
        {caret ? <span aria-hidden className="w-[4px] h-10 bg-accent shrink-0" /> : null}
        <input
          id={inputId}
          className={cn(
            "flex-1 bg-transparent outline-none font-sans text-body text-text-primary",
            "placeholder:text-text-secondary",
            className,
          )}
          {...props}
        />
      </div>
      {error ? (
        <p className="font-mono text-mono-xs text-accent">{error}</p>
      ) : null}
    </div>
  );
}
