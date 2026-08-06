/** @type {import('next').NextConfig} */
const nextConfig = {
  // output: 'export',
  serverExternalPackages: ["@duckdb/node-api"],
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  experimental: {
    // SWC server minifier miscompiles the detail pages → prod-only 500. Server-only flag.
    serverMinification: false,
  },
}

export default nextConfig
