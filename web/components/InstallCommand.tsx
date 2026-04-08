"use client";

import { useState } from "react";

const CURL_COMMAND = "curl -fsSL https://schemagic.design/install.sh | bash";

function CopyIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="5.5" y="5.5" width="8" height="8" rx="0" />
      <path d="M10.5 5.5V3.5C10.5 2.95 10.05 2.5 9.5 2.5H3.5C2.95 2.5 2.5 2.95 2.5 3.5V9.5C2.5 10.05 2.95 10.5 3.5 10.5H5.5" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M3 8.5L6.5 12L13 4" />
    </svg>
  );
}

export default function InstallCommand() {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(CURL_COMMAND);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="inline-flex items-center border border-border bg-surface-raised max-w-[480px] w-full">
      <div className="flex items-center gap-3 px-[24px] py-[12px] flex-1 min-w-0">
        <span className="font-mono text-sm text-text-secondary select-none">
          $
        </span>
        <code className="font-mono text-sm text-text-primary truncate">
          {CURL_COMMAND}
        </code>
      </div>
      <button
        onClick={handleCopy}
        className="flex items-center justify-center w-[48px] h-[48px] border-l border-border text-text-secondary hover:text-accent transition-colors shrink-0 cursor-pointer"
        aria-label={copied ? "Copied" : "Copy to clipboard"}
      >
        {copied ? <CheckIcon /> : <CopyIcon />}
      </button>
    </div>
  );
}
