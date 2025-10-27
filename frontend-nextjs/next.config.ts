import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  serverExternalPackages: ['axios'],
  experimental: {
    serverActions: {
      bodySizeLimit: '50mb', // Tăng giới hạn kích thước file upload lên 50MB
    }
  }
};

export default nextConfig;