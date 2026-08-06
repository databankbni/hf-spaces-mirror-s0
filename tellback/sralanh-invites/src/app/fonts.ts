import { Inter, Cormorant_Garamond, Battambang, Moul } from 'next/font/google';

/**
 * Font stacks exposed as CSS variables (consumed in tailwind.config.ts).
 * Google Fonts stand-ins for the Khmer OS family requested in the brief:
 *   - Battambang  ≈ Khmer OS Siemreap / Battambang (body)
 *   - Moul        ≈ Khmer OS Muol (traditional display headings)
 * Swap in the real Khmer OS webfonts via next/font/local later if desired.
 */

export const latinSans = Inter({
  subsets: ['latin'],
  variable: '--font-latin-sans',
  display: 'swap'
});

export const latinDisplay = Cormorant_Garamond({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-latin-display',
  display: 'swap'
});

export const khmerBody = Battambang({
  subsets: ['khmer'],
  weight: ['400', '700'],
  variable: '--font-khmer-body',
  display: 'swap'
});

export const khmerDisplay = Moul({
  subsets: ['khmer'],
  weight: ['400'],
  variable: '--font-khmer-display',
  display: 'swap'
});

/** Convenience: all font CSS-variable classes joined for the <html> element. */
export const fontVariables = [
  latinSans.variable,
  latinDisplay.variable,
  khmerBody.variable,
  khmerDisplay.variable
].join(' ');
