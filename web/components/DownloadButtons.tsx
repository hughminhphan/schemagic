function AppleIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 16 16"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M11.182.008C11.148-.03 9.923.023 8.857 1.18c-1.066 1.156-.902 2.482-.878 2.516.024.034 1.52.087 2.475-1.258.955-1.345.762-2.391.728-2.43zm3.314 11.733c-.048-.096-2.325-1.234-2.113-3.422.212-2.189 1.675-2.789 1.698-2.854.023-.065-.597-.79-1.254-1.157a3.692 3.692 0 0 0-1.563-.434c-.108-.003-.483-.095-1.254.116-.508.139-1.653.589-1.968.607-.316.018-1.256-.522-2.267-.665-.647-.125-1.333.131-1.824.328-.49.196-1.422.754-2.074 2.237-.652 1.482-.311 3.83-.067 4.56.244.729.625 1.924 1.273 2.796.576.984 1.34 1.667 1.659 1.899.319.232 1.219.386 1.843.067.502-.308 1.408-.485 1.766-.472.357.013 1.061.154 1.782.539.571.197 1.111.115 1.652-.105.541-.221 1.324-1.059 2.238-2.758.347-.79.505-1.217.473-1.282z" />
    </svg>
  );
}

function WindowsIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 16 16"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M6.555 1.375 0 2.237v5.45h6.555V1.375zM0 13.795l6.555.933V8.313H0v5.482zm7.278-5.4.026 6.378L16 16V8.395H7.278zM16 0 7.213 1.249v6.059H16V0z" />
    </svg>
  );
}

export default function DownloadButtons() {
  const base =
    "inline-flex items-center justify-center gap-3 px-[24px] h-[48px] border border-border font-mono text-sm transition-colors cursor-pointer min-w-[180px]";

  return (
    <div className="flex flex-col sm:flex-row gap-[16px]">
      <a
        href="/api/download/mac"
        className={`${base} bg-accent text-black border-accent hover:opacity-90`}
      >
        <AppleIcon />
        Download for Mac
      </a>
      <a
        href="/api/download/windows"
        className={`${base} bg-surface-raised text-text-primary hover:border-accent hover:text-accent`}
      >
        <WindowsIcon />
        Download for Windows
      </a>
    </div>
  );
}
