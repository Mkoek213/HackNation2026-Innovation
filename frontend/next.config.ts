import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      { source: "/api/chat", destination: `${backendUrl}/chat` },
      { source: "/api/chat/:path*", destination: `${backendUrl}/chat/:path*` },
    ];
  },
};

export default nextConfig;
