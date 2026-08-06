import createNextIntlPlugin from 'next-intl/plugin';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Required for the Hugging Face Spaces Docker container: emits a self-contained
  // server (.next/standalone/server.js) that we run with `node server.js`.
  output: 'standalone',
  images: {
    remotePatterns: [
      // Supabase Storage public buckets
      { protocol: 'https', hostname: '*.supabase.co' },
      { protocol: 'https', hostname: '*.supabase.in' }
    ]
  }
};

export default withNextIntl(nextConfig);
