import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { createSupabaseAdminClient } from '@/lib/supabase/server';
import { InviteContentSchema, type InviteContent } from '@/types/content';
import { getTemplateComponent } from '@/templates';
import { personName } from '@/lib/format';
import { inviteLabels } from '@/lib/invite-labels';
import { RsvpSection } from '@/components/invite/RsvpSection';
import { GuestbookSection } from '@/components/invite/GuestbookSection';

export const dynamic = 'force-dynamic';

async function loadInvite(slug: string) {
  const admin = createSupabaseAdminClient();
  const { data } = await admin
    .from('invites')
    .select('id, slug, status, content_json, hosting_expires_at')
    .eq('slug', slug)
    .maybeSingle();
  return data;
}

function parseContent(json: unknown): InviteContent | null {
  const parsed = InviteContentSchema.safeParse(json);
  return parsed.success ? parsed.data : null;
}

function isExpired(invite: { status: string; hosting_expires_at: string | null }) {
  if (invite.status === 'expired') return true;
  if (invite.hosting_expires_at) return new Date(invite.hosting_expires_at) < new Date();
  return false;
}

export async function generateMetadata({
  params
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const invite = await loadInvite(params.slug);
  const content = invite ? parseContent(invite.content_json) : null;
  if (!content) return { title: 'Wedding Invitation' };

  const groom = personName(content.groom, content.language).primary;
  const bride = personName(content.bride, content.language).primary;
  const L = inviteLabels(content.language);
  const title = groom && bride ? `${groom} ${L.and} ${bride}` : 'Wedding Invitation';
  const description = content.event.venueName
    ? `${L.youAreInvited} ${groom} ${L.and} ${bride}`
    : L.youAreInvited;

  return {
    title,
    description,
    openGraph: { title, description, type: 'website' },
    twitter: { card: 'summary_large_image', title, description }
  };
}

export default async function PublicInvitePage({ params }: { params: { slug: string } }) {
  const invite = await loadInvite(params.slug);
  if (!invite || invite.status === 'draft') notFound();

  const content = parseContent(invite.content_json);
  if (!content) notFound();

  if (isExpired(invite)) {
    const km = content.language === 'km';
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#faf8f5] px-6 text-center">
        <div className="text-4xl">🥀</div>
        <h1 className="mt-4 font-display text-2xl">
          {km ? 'សំបុត្រនេះបានផុតកំណត់' : 'This invitation has expired'}
        </h1>
        <p className="mt-2 max-w-sm text-brand-ink/60">
          {km ? 'សូមបន្តសេវាដាក់ផ្សាយ ដើម្បីរក្សាទំព័រនេះ។' : 'Renew hosting to keep this page live.'}
        </p>
      </div>
    );
  }

  const TemplateComponent = getTemplateComponent(content.templateSlug);
  return (
    <>
      <TemplateComponent content={content} />
      {content.rsvpEnabled && (
        <div id="rsvp" className="bg-[#faf8f5] text-brand-ink">
          <RsvpSection inviteId={invite.id} language={content.language} />
        </div>
      )}
      {content.guestbookEnabled && (
        <div className="bg-white text-brand-ink">
          <GuestbookSection inviteId={invite.id} language={content.language} />
        </div>
      )}
    </>
  );
}
