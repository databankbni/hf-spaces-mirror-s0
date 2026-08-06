'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import type { InviteContent } from '@/types/content';
import type { ThemePreset } from '@/data/templates';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { compressForUpload } from '@/lib/image-compress';
import { LivePreview } from './LivePreview';

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

const BUCKET = process.env.NEXT_PUBLIC_SUPABASE_PHOTOS_BUCKET ?? 'invite-photos';
const MAX_PHOTOS = 8;

export function EditorForm({
  inviteId,
  slug,
  initialContent,
  initialSubdomain,
  tier,
  themes,
  alreadyPublished
}: {
  inviteId: string;
  slug: string;
  initialContent: InviteContent;
  initialSubdomain: string;
  tier: 'basic' | 'premium';
  themes: ThemePreset[];
  alreadyPublished: boolean;
}) {
  const t = useTranslations('editor');
  const isPremium = tier === 'premium';
  const [content, setContent] = useState<InviteContent>(initialContent);
  const [subdomain, setSubdomain] = useState(initialSubdomain);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [published, setPublished] = useState(alreadyPublished);
  const [uploading, setUploading] = useState(false);
  const firstRender = useRef(true);

  // ---- Field helpers -------------------------------------------------------
  const patch = useCallback((updater: (c: InviteContent) => InviteContent) => {
    setContent((prev) => updater(structuredClone(prev)));
  }, []);

  // ---- Debounced autosave --------------------------------------------------
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    setSaveState('saving');
    const id = setTimeout(async () => {
      try {
        const res = await fetch(`/api/invites/${inviteId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(isPremium ? { content, subdomain } : { content })
        });
        setSaveState(res.ok ? 'saved' : 'error');
      } catch {
        setSaveState('error');
      }
    }, 1200);
    return () => clearTimeout(id);
  }, [content, subdomain, inviteId, isPremium]);

  // ---- Photo upload --------------------------------------------------------
  async function uploadFiles(files: FileList, onUrl: (url: string) => void) {
    setUploading(true);
    try {
      const supabase = createSupabaseBrowserClient();
      for (const file of Array.from(files)) {
        const compressed = await compressForUpload(file);
        const path = `${inviteId}/${Date.now()}-${compressed.name.replace(/[^\w.-]+/g, '_')}`;
        const { error } = await supabase.storage.from(BUCKET).upload(path, compressed, {
          upsert: true,
          contentType: compressed.type
        });
        if (error) {
          console.error('upload failed', error.message);
          continue;
        }
        const { data } = supabase.storage.from(BUCKET).getPublicUrl(path);
        onUrl(data.publicUrl);
      }
    } finally {
      setUploading(false);
    }
  }

  async function publish() {
    setSaveState('saving');
    const res = await fetch(`/api/invites/${inviteId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(isPremium ? { content, publish: true, subdomain } : { content, publish: true })
    });
    if (res.ok) {
      setPublished(true);
      setSaveState('saved');
    } else {
      setSaveState('error');
    }
  }

  const saveLabel =
    saveState === 'saving'
      ? t('saving')
      : saveState === 'saved'
        ? t('saved')
        : saveState === 'error'
          ? '⚠︎'
          : '';

  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-display text-2xl sm:text-3xl">{t('title')}</h1>
        <span className="text-sm text-brand-ink/50">{saveLabel}</span>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        {/* ---- Form ---- */}
        <div className="space-y-8">
          {/* Language mode */}
          <div className="flex gap-2">
            {(['bilingual', 'km', 'en'] as const).map((lang) => (
              <button
                key={lang}
                onClick={() => patch((c) => ({ ...c, language: lang }))}
                className={`rounded-full border px-3 py-1 text-sm capitalize ${
                  content.language === lang
                    ? 'border-brand-royal bg-brand-royal text-white'
                    : 'border-black/10'
                }`}
              >
                {lang}
              </button>
            ))}
          </div>

          <Section title={t('coupleSection')}>
            <Field label={t('groomNameLatin')}>
              <input
                className={inputClass}
                value={content.groom.nameLatin ?? ''}
                onChange={(e) => patch((c) => ({ ...c, groom: { ...c.groom, nameLatin: e.target.value } }))}
              />
            </Field>
            <Field label={t('groomNameKm')}>
              <input
                className={`${inputClass} font-khmer`}
                value={content.groom.nameKm ?? ''}
                onChange={(e) => patch((c) => ({ ...c, groom: { ...c.groom, nameKm: e.target.value } }))}
              />
            </Field>
            <Field label={t('groomParents')}>
              <input
                className={inputClass}
                value={content.groom.parents ?? ''}
                onChange={(e) => patch((c) => ({ ...c, groom: { ...c.groom, parents: e.target.value } }))}
              />
            </Field>
            <Field label={t('brideNameLatin')}>
              <input
                className={inputClass}
                value={content.bride.nameLatin ?? ''}
                onChange={(e) => patch((c) => ({ ...c, bride: { ...c.bride, nameLatin: e.target.value } }))}
              />
            </Field>
            <Field label={t('brideNameKm')}>
              <input
                className={`${inputClass} font-khmer`}
                value={content.bride.nameKm ?? ''}
                onChange={(e) => patch((c) => ({ ...c, bride: { ...c.bride, nameKm: e.target.value } }))}
              />
            </Field>
            <Field label={t('brideParents')}>
              <input
                className={inputClass}
                value={content.bride.parents ?? ''}
                onChange={(e) => patch((c) => ({ ...c, bride: { ...c.bride, parents: e.target.value } }))}
              />
            </Field>
          </Section>

          <Section title={t('eventSection')}>
            <Field label={t('date')}>
              <input
                type="date"
                className={inputClass}
                value={content.event.dateGregorian ?? ''}
                onChange={(e) => patch((c) => ({ ...c, event: { ...c.event, dateGregorian: e.target.value } }))}
              />
            </Field>
            <Field label={t('time')}>
              <input
                type="time"
                className={inputClass}
                value={content.event.time ?? ''}
                onChange={(e) => patch((c) => ({ ...c, event: { ...c.event, time: e.target.value } }))}
              />
            </Field>
            <Field label={t('lunarNote')}>
              <input
                className={`${inputClass} font-khmer`}
                placeholder={t('lunarNotePlaceholder')}
                value={content.event.lunarNote ?? ''}
                onChange={(e) => patch((c) => ({ ...c, event: { ...c.event, lunarNote: e.target.value } }))}
              />
            </Field>
            <Field label={t('venueName')}>
              <input
                className={inputClass}
                value={content.event.venueName ?? ''}
                onChange={(e) => patch((c) => ({ ...c, event: { ...c.event, venueName: e.target.value } }))}
              />
            </Field>
            <Field label={t('venueAddress')}>
              <input
                className={inputClass}
                value={content.event.venueAddress ?? ''}
                onChange={(e) => patch((c) => ({ ...c, event: { ...c.event, venueAddress: e.target.value } }))}
              />
            </Field>
            <Field label={t('mapUrl')}>
              <input
                className={inputClass}
                placeholder="https://www.google.com/maps?q=…&output=embed"
                value={content.event.mapUrl ?? ''}
                onChange={(e) => patch((c) => ({ ...c, event: { ...c.event, mapUrl: e.target.value } }))}
              />
            </Field>
          </Section>

          <Section title={t('photosSection')}>
            <p className="text-xs text-brand-ink/50">{t('photosHint')}</p>

            <Field label={t('coverPhoto')}>
              <input
                type="file"
                accept="image/*"
                className="text-sm"
                onChange={(e) => {
                  if (e.target.files?.length)
                    uploadFiles(e.target.files, (url) => patch((c) => ({ ...c, coverPhoto: url })));
                }}
              />
            </Field>

            <div className="mt-2">
              <input
                type="file"
                accept="image/*"
                multiple
                className="text-sm"
                disabled={content.photos.length >= MAX_PHOTOS}
                onChange={(e) => {
                  if (e.target.files?.length)
                    uploadFiles(e.target.files, (url) =>
                      patch((c) =>
                        c.photos.length >= MAX_PHOTOS ? c : { ...c, photos: [...c.photos, url] }
                      )
                    );
                }}
              />
              {uploading && <span className="ml-2 text-xs text-brand-ink/50">…</span>}
              <div className="mt-3 grid grid-cols-4 gap-2">
                {content.photos.map((url, i) => (
                  <div key={i} className="relative">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={url} alt="" className="aspect-square w-full rounded object-cover" />
                    <button
                      onClick={() =>
                        patch((c) => ({ ...c, photos: c.photos.filter((_, j) => j !== i) }))
                      }
                      className="absolute -right-1 -top-1 h-5 w-5 rounded-full bg-black/70 text-xs text-white"
                      aria-label="remove"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </Section>

          <Section title={t('loveStory')}>
            <textarea
              className={`${inputClass} min-h-24`}
              value={content.loveStory ?? ''}
              onChange={(e) => patch((c) => ({ ...c, loveStory: e.target.value }))}
            />
            <Field label={t('hashtag')}>
              <div className="flex items-center gap-1">
                <span className="text-brand-ink/40">#</span>
                <input
                  className={`${inputClass} flex-1`}
                  placeholder="DaraAndSopheak2026"
                  value={content.hashtag ?? ''}
                  onChange={(e) =>
                    patch((c) => ({ ...c, hashtag: e.target.value.replace(/^#/, '') }))
                  }
                />
              </div>
            </Field>
          </Section>

          <Section title={t('themeSection')}>
            <div className="flex flex-wrap gap-3">
              {themes.map((th) => (
                <button
                  key={th.key}
                  onClick={() => patch((c) => ({ ...c, theme: th.key }))}
                  className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm ${
                    content.theme === th.key ? 'border-brand-ink' : 'border-black/10'
                  }`}
                >
                  <span className="h-4 w-4 rounded-full" style={{ backgroundColor: th.swatch }} />
                  {th.label}
                </button>
              ))}
            </div>
          </Section>

          {/* Premium features */}
          {isPremium ? (
            <Section title="Premium">
              <Toggle
                label="Enable RSVP"
                checked={content.rsvpEnabled}
                onChange={(v) => patch((c) => ({ ...c, rsvpEnabled: v }))}
              />
              <Toggle
                label="Enable guestbook / wishes wall"
                checked={content.guestbookEnabled}
                onChange={(v) => patch((c) => ({ ...c, guestbookEnabled: v }))}
              />
              <Field label="Background music URL (optional)">
                <input
                  className={inputClass}
                  placeholder="https://…/song.mp3"
                  value={content.musicUrl ?? ''}
                  onChange={(e) => patch((c) => ({ ...c, musicUrl: e.target.value }))}
                />
              </Field>
              <Field label="Custom subdomain">
                <div className="flex items-center gap-1">
                  <input
                    className={`${inputClass} flex-1`}
                    placeholder="dara-sopheak"
                    value={subdomain}
                    onChange={(e) => setSubdomain(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                  />
                  <span className="text-xs text-brand-ink/50">
                    .{process.env.NEXT_PUBLIC_ROOT_DOMAIN ?? 'sralanh.com'}
                  </span>
                </div>
              </Field>
            </Section>
          ) : (
            <div className="rounded-xl border border-dashed border-black/15 p-4 opacity-70">
              <p className="text-sm font-medium">RSVP · Guestbook · Music · Custom subdomain</p>
              <p className="mt-1 text-xs text-brand-ink/50">{t('premiumLocked')}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={publish}
              className="rounded-full bg-brand-royal px-6 py-3 font-medium text-white hover:opacity-90"
            >
              {published ? t('published') : t('publish')}
            </button>
            {published && (
              <a
                href={`/invite/${slug}`}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-medium text-brand-royal underline"
              >
                {t('viewLive')} →
              </a>
            )}
          </div>
        </div>

        {/* ---- Live preview ---- */}
        <div className="lg:sticky lg:top-20 lg:self-start">
          <LivePreview content={content} />
        </div>
      </div>
    </div>
  );
}

const inputClass =
  'w-full rounded-lg border border-black/10 bg-white px-3 py-2 text-sm outline-none focus:border-brand-royal';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-brand-ink/60">
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-brand-ink/60">{label}</span>
      {children}
    </label>
  );
}

function Toggle({
  label,
  checked,
  onChange
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between rounded-lg border border-black/10 bg-white px-3 py-2">
      <span className="text-sm">{label}</span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}
