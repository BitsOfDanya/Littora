import path from "node:path";
import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

loadEnvConfig(
  path.resolve(process.cwd(), ".."),
  process.env.NODE_ENV !== "production",
  console,
  true,
);

const apiProxyTarget = process.env.LITTORA_API_PROXY_TARGET?.replace(/\/$/, "");
const ANALYSIS_PROXY_TIMEOUT_MS = 180_000;

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  typedRoutes: true,
  devIndicators: false,
  output: "standalone",
  experimental: { proxyTimeout: ANALYSIS_PROXY_TIMEOUT_MS },
  async rewrites() {
    if (!apiProxyTarget) return [];
    return [{ source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` }];
  },
};

export default nextConfig;
