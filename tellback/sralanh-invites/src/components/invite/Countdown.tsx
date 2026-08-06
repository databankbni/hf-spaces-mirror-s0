'use client';

import { useEffect, useState } from 'react';

interface CountdownProps {
  /** ISO date (and optional time) to count down to. */
  target?: string;
  labels: { days: string; hours: string; minutes: string; seconds: string };
}

function diff(target: number) {
  const now = Date.now();
  const delta = Math.max(0, target - now);
  const days = Math.floor(delta / 86_400_000);
  const hours = Math.floor((delta % 86_400_000) / 3_600_000);
  const minutes = Math.floor((delta % 3_600_000) / 60_000);
  const seconds = Math.floor((delta % 60_000) / 1000);
  return { days, hours, minutes, seconds };
}

export function Countdown({ target, labels }: CountdownProps) {
  const targetMs = target ? new Date(target).getTime() : NaN;
  const [time, setTime] = useState(() => (Number.isNaN(targetMs) ? null : diff(targetMs)));

  useEffect(() => {
    if (Number.isNaN(targetMs)) return;
    setTime(diff(targetMs));
    const id = setInterval(() => setTime(diff(targetMs)), 1000);
    return () => clearInterval(id);
  }, [targetMs]);

  if (!time) return null;

  const cells = [
    { value: time.days, label: labels.days },
    { value: time.hours, label: labels.hours },
    { value: time.minutes, label: labels.minutes },
    { value: time.seconds, label: labels.seconds }
  ];

  return (
    <div className="flex items-center justify-center gap-3 sm:gap-6">
      {cells.map((c) => (
        <div key={c.label} className="flex flex-col items-center">
          <span className="tabular-nums text-2xl sm:text-4xl font-semibold">
            {String(c.value).padStart(2, '0')}
          </span>
          <span className="mt-1 text-[10px] sm:text-xs uppercase tracking-widest opacity-70">
            {c.label}
          </span>
        </div>
      ))}
    </div>
  );
}
