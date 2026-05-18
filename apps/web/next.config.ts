import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  // Locked-down image sources — we'll allow more when we add real content
  images: {
    remotePatterns: [],
  },

  async rewrites() {
    // In dev, forward /api/* to the FastAPI backend on :8000.
    // In prod this is handled by the reverse proxy.
    const apiBase = process.env.DEEVAI_API_BASE_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiBase}/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
