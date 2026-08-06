import { notFound } from 'next/navigation';
import { getTranslations } from 'next-intl/server';
import { getTemplate } from '@/data/templates';
import { getTemplateComponent } from '@/templates';
import { MOCK_INVITE } from '@/data/mock-invite';
import { BuyPanel } from '@/components/BuyPanel';

export default async function TemplatePreviewPage({
  params
}: {
  params: { slug: string; locale: string };
}) {
  const template = getTemplate(params.slug);
  if (!template) notFound();

  const t = await getTranslations('template');
  const TemplateComponent = getTemplateComponent(template.slug);

  // Render the template with demo data + this template's first preset theme.
  const demoContent = {
    ...MOCK_INVITE,
    templateSlug: template.slug,
    theme: template.themes[0]?.key ?? 'sand'
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_320px]">
        {/* Live preview */}
        <div>
          <p className="mb-3 text-sm uppercase tracking-wide text-brand-ink/50">
            {t('livePreview')} — {template.name}
          </p>
          <div className="overflow-hidden rounded-2xl border border-black/10 shadow-sm">
            <TemplateComponent content={demoContent} />
          </div>
        </div>

        {/* Buy panel (sticky on desktop) */}
        <div className="lg:sticky lg:top-20 lg:self-start">
          <BuyPanel template={template} />
        </div>
      </div>
    </div>
  );
}
