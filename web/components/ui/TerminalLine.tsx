import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export interface TerminalLineProps extends HTMLAttributes<HTMLParagraphElement> {
  children: ReactNode;
  prefix?: string;
}

export function TerminalLine({
  children,
  prefix = ">",
  className,
  ...props
}: TerminalLineProps) {
  return (
    <p
      className={cn(
        "font-mono text-mono-xs leading-[14px] text-text-secondary",
        className,
      )}
      {...props}
    >
      <span className="text-accent">{prefix}</span>
      <span className="whitespace-pre"> {children}</span>
    </p>
  );
}

export function TerminalBlock({
  children,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "bg-surface border-2 border-accent flex flex-col gap-3 px-6 py-5 font-mono",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}
