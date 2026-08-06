import { useTranslations } from 'next-intl';
import { TEMPLATES } from '@/data/templates';
import { TemplateCard } from '@/components/TemplateCard';

export default function GalleryPage() {
  const t = useTranslations('gallery');
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:py-14">
      <div className="text-center">
        <h1 className="font-display text-3xl sm:text-4xl">{t('title')}</h1>
        <p className="mx-auto mt-3 max-w-xl text-brand-ink/60">{t('subtitle')}</p>
      </div>

      {/* TODO: wire up style/language/price filters (filter UI is a stub). */}
      <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {TEMPLATES.map((template) => (
          <TemplateCard key={template.slug} template={template} />
        ))}
      </div>
    </div>
  );
}
