'use client';

import { useState } from 'react';
import type { InviteContent } from '@/types/content';

const T = {
  en: {
    title: 'Will you join us?',
    name: 'Your name',
    attending: 'Joyfully accepts',
    declining: 'Regretfully declines',
    guests: 'Number of guests',
    meal: 'Meal preference (optional)',
    note: 'Note (optional)',
    submit: 'Send RSVP',
    thanks: 'Thank you! Your RSVP has been received.'
  },
  km: {
    title: 'តើអ្នកនឹងចូលរួមទេ?',
    name: 'ឈ្មោះរបស់អ្នក',
    attending: 'ចូលរួមដោយក្តីរីករាយ',
    declining: 'សុំទោស មិនអាចចូលរួម',
    guests: 'ចំនួនភ្ញៀវ',
    meal: 'ជម្រើសម្ហូប (ស្រេចចិត្ត)',
    note: 'ចំណាំ (ស្រេចចិត្ត)',
    submit: 'ផ្ញើ RSVP',
    thanks: 'អរគុណ! ការឆ្លើយតបរបស់អ្នកត្រូវបានទទួល។'
  }
};

export function RsvpSection({
  inviteId,
  language
}: {
  inviteId: string;
  language: InviteContent['language'];
}) {
  const t = language === 'km' ? T.km : T.en;
  const [attending, setAttending] = useState(true);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    try {
      const res = await fetch('/api/rsvp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          inviteId,
          guestName: String(form.get('guestName') ?? ''),
          attending,
          guestCount: Number(form.get('guestCount') ?? 1),
          mealPref: String(form.get('mealPref') ?? '') || undefined,
          note: String(form.get('note') ?? '') || undefined
        })
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.error ?? 'Failed');
      }
      setDone(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className={`mx-auto max-w-md px-5 py-12 ${language === 'km' ? 'font-khmer' : ''}`}>
      <h2 className="text-center font-display text-2xl">{t.title}</h2>
      {done ? (
        <p className="mt-6 rounded-xl bg-black/5 p-4 text-center text-sm">{t.thanks}</p>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 space-y-3">
          <input name="guestName" required placeholder={t.name} className={inputClass} />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setAttending(true)}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm ${attending ? 'border-black bg-black text-white' : 'border-black/15'}`}
            >
              {t.attending}
            </button>
            <button
              type="button"
              onClick={() => setAttending(false)}
              className={`flex-1 rounded-lg border px-3 py-2 text-sm ${!attending ? 'border-black bg-black text-white' : 'border-black/15'}`}
            >
              {t.declining}
            </button>
          </div>
          {attending && (
            <>
              <label className="block text-sm">
                <span className="mb-1 block opacity-70">{t.guests}</span>
                <input name="guestCount" type="number" min={1} max={20} defaultValue={1} className={inputClass} />
              </label>
              <input name="mealPref" placeholder={t.meal} className={inputClass} />
            </>
          )}
          <textarea name="note" placeholder={t.note} className={`${inputClass} min-h-16`} />
          {error && <p className="text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-full bg-black px-5 py-3 font-medium text-white disabled:opacity-50"
          >
            {t.submit}
          </button>
        </form>
      )}
    </section>
  );
}

const inputClass = 'w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm outline-none focus:border-black';
