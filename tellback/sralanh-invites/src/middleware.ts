import { type NextRequest } from 'next/server';
import createIntlMiddleware from 'next-intl/middleware';
import { createServerClient } from '@supabase/ssr';
import { routing } from './i18n/routing';

const intlMiddleware = createIntlMiddleware(routing);

export async function middleware(request: NextRequest) {
  // 1) Locale routing (may redirect to add a /en|/km prefix).
  const response = intlMiddleware(request);

  // 2) Refresh the Supabase auth session cookie on the same response, so
  //    Server Components see a fresh session. Best-effort: never let an auth
  //    hiccup (or placeholder env in local dev) break navigation.
  try {
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet: { name: string; value: string; options?: Record<string, unknown> }[]) {
            cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
          }
        }
      }
    );
    await supabase.auth.getUser();
  } catch {
    /* ignore — auth not configured yet */
  }

  return response;
}

export const config = {
  // See note in the previous version: skip /api, framework internals, /invite
  // (public locale-agnostic pages) and static assets.
  matcher: ['/((?!api|_next|_vercel|invite|.*\\..*).*)']
};
