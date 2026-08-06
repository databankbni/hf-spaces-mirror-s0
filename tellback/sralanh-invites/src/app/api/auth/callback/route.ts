import { NextResponse } from 'next/server';
import type { EmailOtpType } from '@supabase/supabase-js';
import { createSupabaseServerClient } from '@/lib/supabase/server';

export const runtime = 'nodejs';

/**
 * Base URL for redirects. Behind the HF Spaces proxy the request Host is the
 * internal bind address (0.0.0.0:7860), so we must use the configured public
 * URL instead of `new URL(request.url).origin`.
 */
function siteBase(request: Request): string {
  const configured = process.env.NEXT_PUBLIC_SITE_URL;
  if (configured) return configured.replace(/\/$/, '');
  // Fallback: reconstruct from forwarded headers, then request origin.
  const host = request.headers.get('x-forwarded-host') ?? request.headers.get('host');
  const proto = request.headers.get('x-forwarded-proto') ?? 'https';
  if (host) return `${proto}://${host}`;
  return new URL(request.url).origin;
}

/**
 * Auth callback. Handles two link styles:
 *  - `?code=...`                 → browser magic-link / OAuth (PKCE): exchangeCodeForSession
 *  - `?token_hash=...&type=...`  → server-verifiable email OTP link (e.g. admin
 *                                  generateLink, or a custom email template): verifyOtp
 * On success, sets the session cookie and redirects to `next`.
 */
export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get('code');
  const tokenHash = searchParams.get('token_hash');
  const type = searchParams.get('type') as EmailOtpType | null;
  const next = searchParams.get('next') ?? '/en/dashboard';
  const base = siteBase(request);

  const supabase = createSupabaseServerClient();

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(`${base}${next}`);
  } else if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
    if (!error) return NextResponse.redirect(`${base}${next}`);
  }

  return NextResponse.redirect(`${base}${next}?authError=1`);
}
