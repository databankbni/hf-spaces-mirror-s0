import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { dirname } from 'path';
import { config } from '../config';
import { Intent } from '../types';

/**
 * Learning Service — MLO learns from every guest conversation.
 * ------------------------------------------------------------
 * True model fine-tuning is neither possible (hosted models) nor desirable
 * for an MVP. Instead this layer does what production assistants actually do:
 * it distils every interaction into durable knowledge and feeds it back into
 * the waiter's brain (the LLM prompt) — so MLO genuinely improves with use.
 *
 * What is learned, per restaurant:
 *  - dishAsks      : which dishes guests ask about most (trending)
 *  - missingAsks   : dishes guests request that are NOT on the menu — gold for
 *                    the owner ("40 guests asked for chapati — add it!") and
 *                    lets MLO apologize fast and pivot to alternatives.
 *  - intents       : what guests mostly want (recommendations? calories? …)
 *  - unanswered    : recent messages the engine could not understand.
 *  - langCounts    : guest language mix (sw vs en).
 *
 * The knowledge is:
 *  1. Injected into the LLM prompt (GUEST INSIGHTS + trending) every turn.
 *  2. Exposed at GET /api/ai/insights?slug=… for owner dashboards / the
 *     backend to harvest and store permanently.
 *  3. Persisted to a local JSON file so restarts don't lose it. (On ephemeral
 *     hosts like free HF Spaces, pair this with periodic harvesting via the
 *     insights endpoint, or mount persistent storage / Redis later — the
 *     interface stays the same.)
 */

interface RestaurantLearning {
  dishAsks: Record<string, number>;
  missingAsks: Record<string, number>;
  intents: Partial<Record<Intent, number>>;
  unanswered: string[];
  langCounts: { sw: number; en: number };
  updatedAt: number;
}

interface TurnRecord {
  intent: Intent;
  lang: 'sw' | 'en';
  /** Menu dish the guest asked about (explain_food, resolved). */
  askedDish?: string;
  /** What the guest asked for that is NOT on the menu (explain_food notFound). */
  missingQuery?: string;
  /** Raw message when the engine could not understand it (unknown intent). */
  unansweredMessage?: string;
}

const MAX_KEYS = 200; // cap per counter map
const MAX_UNANSWERED = 50;

export class LearningService {
  private store = new Map<string, RestaurantLearning>();
  private saveTimer: NodeJS.Timeout | null = null;
  private warnedWrite = false;

  constructor(private readonly file: string = config.learningFile) {
    this.load();
  }

  /* ── persistence ─────────────────────────────────────────────── */

  private load(): void {
    if (!this.file) return;
    try {
      if (existsSync(this.file)) {
        const raw = JSON.parse(readFileSync(this.file, 'utf8'));
        for (const [slug, data] of Object.entries(raw)) {
          this.store.set(slug, data as RestaurantLearning);
        }
      }
    } catch {
      // Corrupt/unreadable file — start fresh rather than crash.
    }
  }

  private saveSoon(): void {
    if (!this.file || this.saveTimer) return;
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      try {
        mkdirSync(dirname(this.file), { recursive: true });
        writeFileSync(this.file, JSON.stringify(Object.fromEntries(this.store)));
      } catch {
        if (!this.warnedWrite) {
          this.warnedWrite = true;
          console.warn('[learning] cannot persist to file; learning stays in-memory only');
        }
      }
    }, 5000);
  }

  /* ── helpers ─────────────────────────────────────────────────── */

  private forSlug(slug: string): RestaurantLearning {
    let r = this.store.get(slug);
    if (!r) {
      r = {
        dishAsks: {},
        missingAsks: {},
        intents: {},
        unanswered: [],
        langCounts: { sw: 0, en: 0 },
        updatedAt: Date.now(),
      };
      this.store.set(slug, r);
    }
    return r;
  }

  private static bump(map: Record<string, number>, key: string): void {
    map[key] = (map[key] ?? 0) + 1;
    // Keep the map bounded: drop the rarest entries when oversized.
    const keys = Object.keys(map);
    if (keys.length > MAX_KEYS) {
      keys
        .sort((a, b) => map[a] - map[b])
        .slice(0, keys.length - MAX_KEYS)
        .forEach((k) => delete map[k]);
    }
  }

  private static top(map: Record<string, number>, n: number, min = 2): string[] {
    return Object.entries(map)
      .filter(([, c]) => c >= min)
      .sort((a, b) => b[1] - a[1])
      .slice(0, n)
      .map(([k]) => k);
  }

  /* ── public API ──────────────────────────────────────────────── */

  /** Record one conversation turn. Called by the orchestrator every message. */
  public recordTurn(slug: string, t: TurnRecord): void {
    const r = this.forSlug(slug);
    r.intents[t.intent] = (r.intents[t.intent] ?? 0) + 1;
    r.langCounts[t.lang]++;
    if (t.askedDish) LearningService.bump(r.dishAsks, t.askedDish);
    if (t.missingQuery) {
      const q = t.missingQuery.toLowerCase().trim().slice(0, 60);
      if (q) LearningService.bump(r.missingAsks, q);
    }
    if (t.unansweredMessage) {
      r.unanswered.push(t.unansweredMessage.slice(0, 120));
      if (r.unanswered.length > MAX_UNANSWERED) {
        r.unanswered.splice(0, r.unanswered.length - MAX_UNANSWERED);
      }
    }
    r.updatedAt = Date.now();
    this.saveSoon();
  }

  /** Most asked-about menu dishes (for the trending prompt block). */
  public trendingDishes(slug: string, n = 3): string[] {
    const r = this.store.get(slug);
    return r ? LearningService.top(r.dishAsks, n) : [];
  }

  /** Compact insight lines injected into the waiter's prompt. */
  public promptInsights(slug: string): string[] {
    const r = this.store.get(slug);
    if (!r) return [];
    const lines: string[] = [];

    const missing = LearningService.top(r.missingAsks, 3);
    if (missing.length) {
      lines.push(
        `Guests often ask for items NOT on the menu: ${missing.join(', ')}. ` +
          'If asked for one of these, apologize warmly right away and suggest the closest real dish.',
      );
    }
    const total = r.langCounts.sw + r.langCounts.en;
    if (total >= 10) {
      const swPct = Math.round((r.langCounts.sw / total) * 100);
      if (swPct >= 70) lines.push('Most guests here speak Swahili.');
      else if (swPct <= 30) lines.push('Most guests here speak English.');
    }
    return lines;
  }

  /** Full analytics snapshot — for owner dashboards / backend harvesting. */
  public snapshot(slug: string): {
    slug: string;
    topAskedDishes: { name: string; count: number }[];
    requestedButMissing: { query: string; count: number }[];
    intents: Partial<Record<Intent, number>>;
    languages: { sw: number; en: number };
    recentUnanswered: string[];
    updatedAt: number | null;
  } {
    const r = this.store.get(slug);
    const toSorted = (m: Record<string, number>) =>
      Object.entries(m)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 25)
        .map(([k, c]) => ({ name: k, count: c }));
    return {
      slug,
      topAskedDishes: r ? toSorted(r.dishAsks) : [],
      requestedButMissing: r
        ? toSorted(r.missingAsks).map(({ name, count }) => ({ query: name, count }))
        : [],
      intents: r?.intents ?? {},
      languages: r?.langCounts ?? { sw: 0, en: 0 },
      recentUnanswered: r?.unanswered.slice(-10) ?? [],
      updatedAt: r?.updatedAt ?? null,
    };
  }

  public clear(): void {
    this.store.clear();
  }
}

export const learningService = new LearningService();
