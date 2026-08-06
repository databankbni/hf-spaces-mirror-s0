/**
 * Lightweight, dependency-free text utilities used by the intent engine and
 * menu filter. No ML — just normalization, tokenization and fuzzy matching
 * heuristics that work for both English and Swahili input.
 */

/**
 * Lowercase, strip accents/diacritics, collapse whitespace and remove
 * punctuation (keeping intra-word characters). Returns a clean string.
 */
export function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '') // strip diacritics
    .replace(/[^\p{L}\p{N}\s]/gu, ' ') // punctuation -> space
    .replace(/\s+/g, ' ')
    .trim();
}

/** Split normalized text into word tokens. */
export function tokenize(text: string): string[] {
  const n = normalize(text);
  return n.length ? n.split(' ') : [];
}

/**
 * True if `haystack` contains `needle` as a whole word/phrase.
 * Both inputs are normalized first. Multi-word needles are matched as a phrase.
 */
export function containsPhrase(haystack: string, needle: string): boolean {
  const h = normalize(haystack);
  const n = normalize(needle);
  if (!n) return false;
  // word-boundary-ish: surround with spaces to avoid partial-word hits
  return ` ${h} `.includes(` ${n} `);
}

const SWAHILI_MARKERS = new Set([
  'na', 'ya', 'wa', 'kwa', 'ni', 'nataka', 'nipe', 'chakula', 'habari', 'sana',
  'mimi', 'wewe', 'asante', 'tafadhali', 'niambie', 'kuhusu', 'gani', 'vipi',
  'mna', 'naomba', 'yangu', 'za', 'cha', 'vya', 'iko', 'au', 'sawa', 'ndio',
  'hapana', 'nionyeshe', 'nipendekezee', 'leo', 'bei', 'mzio', 'karibu',
]);

const ENGLISH_MARKERS = new Set([
  'the', 'i', 'you', 'want', 'what', 'is', 'are', 'have', 'my', 'me', 'please',
  'food', 'show', 'can', 'do', 'a', 'an', 'give', 'would', 'like', 'need',
  'something', 'healthy', 'menu', 'and', 'or', 'for', 'with',
]);

/**
 * Very light language detection (Swahili vs English) for choosing the
 * language of follow-up suggestions. Mixed input leans English on ties.
 */
export function detectLanguage(text: string): 'sw' | 'en' {
  let sw = 0;
  let en = 0;
  for (const tok of tokenize(text)) {
    if (SWAHILI_MARKERS.has(tok)) sw++;
    if (ENGLISH_MARKERS.has(tok)) en++;
  }
  return sw > en ? 'sw' : 'en';
}

/**
 * Levenshtein edit distance — used for light typo tolerance when matching a
 * user-typed dish name against real menu items. Capped/early-exit friendly.
 */
export function levenshtein(a: string, b: string): number {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;

  let prev = new Array(b.length + 1);
  let curr = new Array(b.length + 1);
  for (let j = 0; j <= b.length; j++) prev[j] = j;

  for (let i = 1; i <= a.length; i++) {
    curr[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost);
    }
    [prev, curr] = [curr, prev];
  }
  return prev[b.length];
}

/**
 * Similarity ratio in 0..1 based on edit distance, normalized by the longer
 * string. 1 = identical.
 */
export function similarity(a: string, b: string): number {
  const x = normalize(a);
  const y = normalize(b);
  if (!x && !y) return 1;
  const maxLen = Math.max(x.length, y.length);
  if (maxLen === 0) return 1;
  return 1 - levenshtein(x, y) / maxLen;
}

/**
 * Given the user message and a list of candidate names (e.g. menu item names),
 * find the best fuzzy match. Returns the candidate plus a score, or null when
 * nothing clears the threshold.
 *
 * Strategy:
 *  1. Exact phrase containment (strongest signal).
 *  2. Token-level fuzzy match against each candidate word.
 */
export function bestNameMatch(
  message: string,
  candidates: string[],
  threshold = 0.72,
): { value: string; score: number } | null {
  const msg = normalize(message);
  if (!msg) return null;

  let best: { value: string; score: number } | null = null;

  for (const candidate of candidates) {
    const cand = normalize(candidate);
    if (!cand) continue;

    let score = 0;

    // 1. Direct phrase containment — e.g. "tell me about pilau" contains "pilau".
    if (containsPhrase(msg, cand)) {
      score = 1;
    } else {
      // 2. Best token-vs-token similarity, lightly rewarding multi-word overlap.
      const candTokens = cand.split(' ');
      const msgTokens = msg.split(' ');
      let tokenScoreSum = 0;
      for (const ct of candTokens) {
        let bestTokenScore = 0;
        for (const mt of msgTokens) {
          bestTokenScore = Math.max(bestTokenScore, similarity(ct, mt));
        }
        tokenScoreSum += bestTokenScore;
      }
      score = tokenScoreSum / candTokens.length;
    }

    if (!best || score > best.score) {
      best = { value: candidate, score };
    }
  }

  if (best && best.score >= threshold) return best;
  return null;
}
