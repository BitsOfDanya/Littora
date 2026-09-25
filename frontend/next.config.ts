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

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  typedRoutes: true,
  devIndicators: false,
  output: "standalone",
  async rewrites() {
    if (!apiProxyTarget) return [];
    return [{ source: "/api/:path*", destination: `${apiProxyTarget}/api/:path*` }];
  },
};

export default nextConfig;
