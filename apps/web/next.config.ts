import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  experimental: {
    // The sandboxed demo build cannot capture a detached `tsc --showConfig`
    // child process, so use Next's TypeScript compiler API integration.
    useTypeScriptCli: false,
  },
};

export default nextConfig;
