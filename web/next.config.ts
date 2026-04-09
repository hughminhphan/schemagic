import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export for Tauri desktop app (no Node.js server needed)
  output: "export",
  trailingSlash: true,
  images: {
    unoptimized: true,
  },
  turbopack: {
    root: import.meta.dirname,
  },
};

export default nextConfig;
