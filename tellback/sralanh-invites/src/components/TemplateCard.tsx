import { useTranslations } from 'next-intl';
import { Link } from '@/i18n/routing';
import type { TemplateMeta } from '@/data/templates';

export function TemplateCard({ template }: { template: TemplateMeta }) {
  const t = useTranslations('gallery');
  return (
    <div className="group overflow-hidden rounded-2xl border border-black/5 bg-white shadow-sm transition hover:shadow-md">
      <Link href={`/templates/${template.slug}`} className="block">
        <div className="relative aspect-[3/4] bg-gradient-to-br from-brand-gold/10 to-brand-royal/10">
          {/* Preview art is a TODO asset; show a tasteful placeholder for now. */}
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="font-display text-2xl text-brand-ink/40">{template.name}</span>
          </div>
          {!template.implemented && (
            <span className="absolute right-3 top-3 rounded-full bg-black/60 px-2 py-1 text-[10px] uppercase tracking-wide text-white">
              soon
            </span>
          )}
        </div>
      </Link>
      <div className="p-4">
        <div className="flex items-baseline justify-between">
          <h3 className="font-medium">{template.name}</h3>
          <span className="text-sm text-brand-ink/60">
            {t('from')} ${template.basePrice}
          </span>
        </div>
        <p className="mt-1 line-clamp-2 text-sm text-brand-ink/60">{template.description}</p>
        <div className="mt-3 flex flex-wrap gap-1">
          {template.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="rounded-full bg-black/5 px-2 py-0.5 text-[11px] text-brand-ink/70">
              {tag}
            </span>
          ))}
        </div>
        <Link
          href={`/templates/${template.slug}`}
          className="mt-4 inline-block rounded-full bg-brand-ink px-4 py-2 text-sm text-white transition group-hover:bg-brand-royal"
        >
          {t('preview')}
        </Link>
      </div>
    </div>
  );
}
