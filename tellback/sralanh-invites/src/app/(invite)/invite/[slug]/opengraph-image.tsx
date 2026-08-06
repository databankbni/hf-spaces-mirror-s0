import { ImageResponse } from 'next/og';
import { createSupabaseAdminClient } from '@/lib/supabase/server';
import { InviteContentSchema } from '@/types/content';
import { personName } from '@/lib/format';

export const runtime = 'nodejs';
export const alt = 'Wedding invitation';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

// Auto-generates the social-share card so links look good in Telegram /
// Messenger / Facebook. NOTE: the default ImageResponse fonts don't include
// Khmer glyphs — we render the Latin names here. TODO: embed a Khmer webfont
// (fetch Battambang .ttf and pass via `fonts`) to show Khmer names on the card.
export default async function OgImage({ params }: { params: { slug: string } }) {
  const admin = createSupabaseAdminClient();
  const { data } = await admin
    .from('invites')
    .select('content_json')
    .eq('slug', params.slug)
    .maybeSingle();

  const parsed = data ? InviteContentSchema.safeParse(data.content_json) : null;
  const content = parsed?.success ? parsed.data : null;

  const groom = content ? personName(content.groom, 'en').primary : '';
  const bride = content ? personName(content.bride, 'en').primary : '';
  const names = groom && bride ? `${groom} & ${bride}` : 'You are invited';
  const cover = content?.coverPhoto;

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #7a1f2b 0%, #b8912f 100%)',
          color: 'white',
          position: 'relative'
        }}
      >
        {cover && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={cover}
            alt=""
            width={size.width}
            height={size.height}
            style={{ position: 'absolute', inset: 0, objectFit: 'cover', opacity: 0.35 }}
          />
        )}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', zIndex: 1 }}>
          <div style={{ fontSize: 28, letterSpacing: 6, opacity: 0.9 }}>THE WEDDING OF</div>
          <div style={{ fontSize: 84, fontWeight: 700, marginTop: 16, textAlign: 'center' }}>
            {names}
          </div>
        </div>
      </div>
    ),
    { ...size }
  );
}
