import type { NextConfig } from "next";

const isStaticExport = process.env.STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  // Static export for Tauri builds (STATIC_EXPORT=1), server mode for Vercel (API routes)
  output: isStaticExport ? "export" : undefined,
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  turbopack: {
    root: import.meta.dirname,
  },
};

export default nextConfig;
