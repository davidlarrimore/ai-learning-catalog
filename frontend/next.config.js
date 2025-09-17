const path = require('path');

const API_PROXY_TARGET = process.env.API_PROXY_TARGET || 'http://backend:8000';

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  outputFileTracingRoot: path.join(__dirname, '..'),
  async rewrites() {
    if (process.env.NEXT_PUBLIC_API_BASE && process.env.NEXT_PUBLIC_API_BASE !== '/api') {
      return [];
    }
    return [
      {
        source: '/api/:path*',
        destination: `${API_PROXY_TARGET.replace(/\/$/, '')}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
