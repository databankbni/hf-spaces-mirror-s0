'use client';

import { useEffect, useState } from 'react';
import type { InviteContent } from '@/types/content';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';

type Entry = { id: string; name: string; message: string; created_at: string };

const T = {
  en: { title: 'Wishes for the couple', name: 'Your name', message: 'Leave a wish…', submit: 'Post', empty: 'Be the first to leave a wish.' },
  km: { title: 'ជូនពរដល់គូស្នេហ៍', name: 'ឈ្មោះរបស់អ្នក', message: 'ទុកពាក្យជូនពរ…', submit: 'ផ្ញើ', empty: 'ក្លាយជាអ្នកជូនពរដំបូង។' }
};

export function GuestbookSection({
  inviteId,
  language
}: {
  inviteId: string;
  language: InviteContent['language'];
}) {
  const t = language === 'km' ? T.km : T.en;
  const [entries, setEntries] = useState<Entry[]>([]);
  const [submitting, setSubmitting] = useState(false);

  async function load() {
    const supabase = createSupabaseBrowserClient();
    const { data } = await supabase
      .from('guestbook_entries')
      .select('id, name, message, created_at')
      .eq('invite_id', inviteId)
      .order('created_at', { ascending: false })
      .limit(100);
    setEntries((data as Entry[]) ?? []);
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inviteId]);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSubmitting(true);
    const formEl = e.currentTarget;
    const form = new FormData(formEl);
    try {
      const res = await fetch('/api/guestbook', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          inviteId,
          name: String(form.get('name') ?? ''),
          message: String(form.get('message') ?? '')
        })
      });
      if (res.ok) {
        formEl.reset();
        await load();
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className={`mx-auto max-w-md px-5 py-12 ${language === 'km' ? 'font-khmer' : ''}`}>
      <h2 className="text-center font-display text-2xl">{t.title}</h2>
      <form onSubmit={onSubmit} className="mt-6 space-y-2">
        <input name="name" required placeholder={t.name} className={inputClass} />
        <textarea name="message" required placeholder={t.message} className={`${inputClass} min-h-16`} />
        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-full bg-black px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {t.submit}
        </button>
      </form>

      <ul className="mt-8 space-y-3">
        {entries.length === 0 && <li className="text-center text-sm opacity-50">{t.empty}</li>}
        {entries.map((e) => (
          <li key={e.id} className="rounded-xl bg-black/5 p-3">
            <p className="text-sm">{e.message}</p>
            <p className="mt-1 text-xs opacity-60">— {e.name}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

const inputClass = 'w-full rounded-lg border border-black/15 bg-white px-3 py-2 text-sm outline-none focus:border-black';
