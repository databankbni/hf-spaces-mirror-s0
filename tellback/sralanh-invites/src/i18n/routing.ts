import { defineRouting } from 'next-intl/routing';
import { createNavigation } from 'next-intl/navigation';

export const routing = defineRouting({
  locales: ['en', 'km'],
  defaultLocale: 'en',
  // Always show the locale prefix (/en, /km) so links are unambiguous.
  localePrefix: 'always'
});

export type AppLocale = (typeof routing.locales)[number];

// Locale-aware navigation helpers — use these instead of next/link & next/navigation
// inside the (main) marketplace so the active locale is preserved.
export const { Link, redirect, usePathname, useRouter, getPathname } =
  createNavigation(routing);
