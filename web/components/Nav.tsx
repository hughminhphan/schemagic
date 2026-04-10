"use client";

import { usePathname } from "next/navigation";

export default function Nav() {
  const pathname = usePathname();
  const isApp = pathname.startsWith("/app");

  return (
    <nav className="border-b border-border">
      <div className="mx-auto max-w-6xl flex items-center justify-between px-6 h-[48px]">
        <a href={isApp ? "/app" : "/"} className="font-mono text-sm font-medium tracking-wider hover:opacity-80 transition-opacity">
          sche<span className="text-accent">MAGIC</span>
        </a>
        <div className="flex items-center gap-[24px]">
          {!isApp && (
            <>
              <a
                href="#pricing"
                className="text-sm text-text-secondary hover:text-text-primary transition-colors"
              >
                Pricing
              </a>
              <a
                href="#download"
                className="text-sm text-text-secondary hover:text-text-primary transition-colors"
              >
                Download
              </a>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
