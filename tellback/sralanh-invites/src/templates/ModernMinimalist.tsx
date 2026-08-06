import Image from 'next/image';
import type { TemplateProps } from '@/types/content';
import { Countdown } from '@/components/invite/Countdown';
import { Divider } from '@/components/invite/Divider';
import { BackgroundMusic } from '@/components/invite/BackgroundMusic';
import {
  personName,
  formatTime,
  toEmbedMapUrl,
  eventDateTime,
  dateParts,
  monogram
} from '@/lib/format';
import { addToCalendarUrl } from '@/lib/calendar';
import { inviteLabels } from '@/lib/invite-labels';

/** Constrained palettes — keys match data/templates.ts `themes`. */
const PALETTES: Record<string, { bg: string; panel: string; text: string; accent: string }> = {
  sand: { bg: '#f6f1ea', panel: '#ffffff', text: '#2b2b2b', accent: '#b39a72' },
  sage: { bg: '#f0f2ec', panel: '#ffffff', text: '#2b3226', accent: '#7c8d6b' },
  ink: { bg: '#f4f4f4', panel: '#ffffff', text: '#1c1c1c', accent: '#2b2b2b' },
  blush: { bg: '#fbf1f0', panel: '#ffffff', text: '#2b2222', accent: '#c98d86' }
};

/**
 * Modern Minimalist — neutral, clean, bilingual-safe. Renders entirely from the
 * `content` JSON. Mobile-first (designed at 375px), scales up gracefully.
 */
export default function ModernMinimalist({ content }: TemplateProps) {
  const p = PALETTES[content.theme] ?? PALETTES.sand;
  const L = inviteLabels(content.language);
  const bride = personName(content.bride, content.language);
  const groom = personName(content.groom, content.language);
  const dp = dateParts(content.event.dateGregorian, content.language);
  const timeStr = formatTime(content.event.time, content.language);
  const mapEmbed = toEmbedMapUrl(content.event.mapUrl);
  const isKhmer = content.language === 'km';
  const title = `${groom.primary} & ${bride.primary} — Wedding`;
  const calUrl = addToCalendarUrl(content, title);

  return (
    <div
      className={isKhmer ? 'font-khmer' : 'font-sans'}
      style={{ backgroundColor: p.bg, color: p.text }}
    >
      <div className="mx-auto max-w-2xl px-5 py-12 sm:py-20">
        {/* Hero */}
        <header className="text-center">
          <div
            className="mx-auto flex h-16 w-16 items-center justify-center rounded-full border text-sm tracking-widest"
            style={{ borderColor: p.accent, color: p.accent }}
          >
            {monogram(groom.primary, bride.primary)}
          </div>
          <p className="mt-6 text-xs sm:text-sm uppercase tracking-[0.35em]" style={{ color: p.accent }}>
            {L.saveTheDate}
          </p>
          <p className="mt-4 text-xs uppercase tracking-[0.2em] opacity-60">{L.youAreInvited}</p>

          <div className="mt-6 sm:mt-8">
            <CoupleName person={groom} parents={content.groom.parents} accent={p.accent} />
            <div className="my-3 sm:my-4 text-2xl sm:text-3xl" style={{ color: p.accent }} aria-hidden>
              {L.and}
            </div>
            <CoupleName person={bride} parents={content.bride.parents} accent={p.accent} />
          </div>

          <p className="mt-6 text-xs uppercase tracking-[0.2em] opacity-50">{L.withFamilies}</p>

          {content.rsvpEnabled && (
            <a
              href="#rsvp"
              className="mt-8 inline-block rounded-full px-6 py-2.5 text-sm font-medium text-white"
              style={{ backgroundColor: p.accent }}
            >
              {L.rsvp}
            </a>
          )}
        </header>

        {content.coverPhoto && (
          <div className="mt-10 overflow-hidden rounded-2xl">
            <Image
              src={content.coverPhoto}
              alt=""
              width={1200}
              height={1500}
              className="h-auto w-full object-cover"
              priority
            />
          </div>
        )}

        <Divider color={p.accent} className="mt-12" />

        {/* When & where */}
        <section className="mt-10 grid gap-8 sm:grid-cols-2">
          <div className="text-center">
            <h2 className="text-xs uppercase tracking-[0.2em]" style={{ color: p.accent }}>
              {L.when}
            </h2>
            {dp ? (
              <div className="mt-3">
                <p className="text-sm opacity-70">{dp.weekday}</p>
                <p className="mt-1 font-display text-4xl leading-none">{dp.day}</p>
                <p className="mt-1 text-lg">{dp.month} {dp.year}</p>
                {timeStr && <p className="mt-1 text-sm opacity-80">{timeStr}</p>}
                {content.event.lunarNote && (
                  <p className="mt-2 text-xs opacity-60 font-khmer">{content.event.lunarNote}</p>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm opacity-50">—</p>
            )}
          </div>

          <div className="text-center">
            <h2 className="text-xs uppercase tracking-[0.2em]" style={{ color: p.accent }}>
              {L.venue}
            </h2>
            {content.event.venueName && (
              <p className="mt-3 font-display text-xl">{content.event.venueName}</p>
            )}
            {content.event.venueAddress && (
              <p className="mt-1 text-sm opacity-80">{content.event.venueAddress}</p>
            )}
          </div>
        </section>

        {/* Actions */}
        {(calUrl || content.event.mapUrl) && (
          <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
            {calUrl && (
              <a
                href={calUrl}
                target="_blank"
                rel="noreferrer"
                className="rounded-full border px-5 py-2 text-sm"
                style={{ borderColor: p.accent, color: p.accent }}
              >
                {L.addToCalendar}
              </a>
            )}
            {content.event.mapUrl && (
              <a
                href={content.event.mapUrl}
                target="_blank"
                rel="noreferrer"
                className="rounded-full px-5 py-2 text-sm text-white"
                style={{ backgroundColor: p.accent }}
              >
                {L.getDirections}
              </a>
            )}
          </div>
        )}

        {mapEmbed && (
          <div className="mt-6 overflow-hidden rounded-2xl border" style={{ borderColor: `${p.accent}55` }}>
            <iframe title="map" src={mapEmbed} className="h-64 w-full" loading="lazy" />
          </div>
        )}

        {/* Countdown */}
        <div className="mt-12">
          <Countdown target={eventDateTime(content)} labels={L.countdown} />
        </div>

        {/* Story */}
        {content.loveStory && (
          <section className="mt-14 text-center">
            <Divider color={p.accent} />
            <h2 className="mt-6 text-sm uppercase tracking-[0.2em]" style={{ color: p.accent }}>
              {L.ourStory}
            </h2>
            <p className="mx-auto mt-4 max-w-prose leading-relaxed opacity-90">{content.loveStory}</p>
          </section>
        )}

        {/* Gallery */}
        {content.photos.length > 0 && (
          <section className="mt-14 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {content.photos.map((src, i) => (
              <div key={i} className="aspect-square overflow-hidden rounded-xl">
                <Image src={src} alt="" width={600} height={600} className="h-full w-full object-cover" />
              </div>
            ))}
          </section>
        )}

        {/* Footer */}
        <footer className="mt-16 text-center">
          <p className="text-sm" style={{ color: p.accent }}>
            {L.thankYou}
          </p>
          <p className="mt-2 font-display text-lg">
            {groom.primary} {L.and} {bride.primary}
          </p>
          {content.hashtag && (
            <p className="mt-2 text-xs uppercase tracking-widest opacity-50">
              #{content.hashtag.replace(/^#/, '')}
            </p>
          )}
        </footer>
      </div>

      {content.musicUrl && <BackgroundMusic src={content.musicUrl} color={p.accent} />}
    </div>
  );
}

function CoupleName({
  person,
  parents,
  accent
}: {
  person: { primary: string; secondary?: string };
  parents?: string;
  accent: string;
}) {
  return (
    <div>
      <h1 className="font-display text-3xl sm:text-5xl leading-tight">{person.primary}</h1>
      {person.secondary && (
        <p className="mt-1 font-khmer text-xl sm:text-2xl" style={{ color: accent }}>
          {person.secondary}
        </p>
      )}
      {parents && <p className="mt-1 text-xs opacity-60">{parents}</p>}
    </div>
  );
}
