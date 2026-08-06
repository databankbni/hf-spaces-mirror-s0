import { notFound } from 'next/navigation';
import { createSupabaseAdminClient } from '@/lib/supabase/server';
import { InviteContentSchema } from '@/types/content';
import { getTemplate } from '@/data/templates';
import { EditorForm } from '@/components/editor/EditorForm';

export const dynamic = 'force-dynamic';

export default async function EditorPage({
  params
}: {
  params: { inviteId: string; locale: string };
}) {
  const admin = createSupabaseAdminClient();
  const { data: invite } = await admin
    .from('invites')
    .select('id, slug, subdomain, content_json, status, order_id')
    .eq('id', params.inviteId)
    .maybeSingle();

  if (!invite) notFound();

  // Tier drives which premium controls the editor unlocks.
  const { data: order } = await admin
    .from('orders')
    .select('tier_purchased')
    .eq('id', invite.order_id)
    .maybeSingle();
  const tier = order?.tier_purchased === 'premium' ? 'premium' : 'basic';

  // Coerce stored JSON into a valid, fully-defaulted content object.
  const parsed = InviteContentSchema.safeParse(invite.content_json);
  const content = parsed.success
    ? parsed.data
    : InviteContentSchema.parse({ templateSlug: 'modern-minimalist', theme: 'sand' });

  const template = getTemplate(content.templateSlug);

  return (
    <EditorForm
      inviteId={invite.id}
      slug={invite.slug}
      initialContent={content}
      initialSubdomain={invite.subdomain ?? ''}
      tier={tier}
      themes={template?.themes ?? []}
      alreadyPublished={invite.status === 'published'}
    />
  );
}
