import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/**/*.{ts,tsx}'
  ],
  theme: {
    extend: {
      fontFamily: {
        // Wired to next/font CSS variables set in the root layouts.
        // `sans` = Latin UI text, `khmer` = Khmer body, `display` = elegant Latin
        // headings, `moul` = Khmer Muol-style display headings (traditional).
        sans: ['var(--font-latin-sans)', 'var(--font-khmer-body)', 'system-ui', 'sans-serif'],
        khmer: ['var(--font-khmer-body)', 'system-ui', 'sans-serif'],
        display: ['var(--font-latin-display)', 'var(--font-khmer-body)', 'serif'],
        moul: ['var(--font-khmer-display)', 'var(--font-khmer-body)', 'serif']
      },
      colors: {
        // Shared brand tokens; individual templates define their own palettes.
        brand: {
          gold: '#b8912f',
          royal: '#7a1f2b',
          ink: '#1f1b16'
        }
      }
    }
  },
  plugins: []
};

export default config;
