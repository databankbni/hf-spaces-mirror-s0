import { ConversationState } from '../services/conversation.service';
import { normalize, containsPhrase } from '../utils/text.parser';

/**
 * Follow-up Engine
 * ----------------
 * Detects when a message is a CONTEXTUAL reference to the previous turn rather
 * than a brand-new request, so the waiter can hold a conversation. NO ML —
 * just keyword + ordinal heuristics (English + Swahili), exactly like the
 * intent engine.
 *
 * Recognised follow-ups:
 *  - `more`    → "show me more", "others", "zaidi", "nyingine"  (paginate)
 *  - `explain` → "the second one", "number 2", "ya kwanza",
 *                "tell me more about it / hiyo"                 (pick an item)
 *
 * Returns null when the message isn't a follow-up, so the normal intent
 * pipeline runs instead.
 */

export type Followup =
  | { kind: 'more' }
  /** index >= 0 → that position in lastResults; index === -1 → the lastItem. */
  | { kind: 'explain'; index: number };

const MORE_KEYWORDS = [
  'more', 'show more', 'see more', 'more options', 'other options', 'others',
  'another', 'what else', 'anything else', 'next', 'more please',
  // Swahili
  'zaidi', 'nyingine', 'vingine', 'nyingineyo', 'nionyeshe zaidi', 'kuna vingine',
];

const PRONOUNS = [
  'it', 'that', 'that one', 'this', 'this one', 'them', 'those', 'the one',
  // Swahili
  'hiyo', 'hicho', 'hilo', 'hizo', 'ile', 'kile', 'huo',
];

const EXPLAIN_TRIGGERS = [
  'tell me', 'tell me about', 'tell me more', 'more about', 'what about',
  'describe', 'explain', 'details', 'info about',
  // Swahili
  'niambie', 'eleza', 'kuhusu', 'maelezo', 'niambie zaidi',
];

/** Word → zero-based index for ordinal references. */
const ORDINALS: Record<string, number> = {
  first: 0, '1st': 0, second: 1, '2nd': 1, third: 2, '3rd': 2,
  fourth: 3, '4th': 3, fifth: 4, '5th': 4,
  // Swahili "ya kwanza / pili / tatu / nne / tano"
  kwanza: 0, pili: 1, tatu: 2, nne: 3, tano: 4,
};

/**
 * Parse an ordinal / numeric reference to a list position. Handles "first",
 * "the 2nd", "number 3", "#4", bare digits, "last"/"mwisho", and the Swahili
 * ordinals. Returns a zero-based index or null.
 */
function parseOrdinal(norm: string, listLength: number): number | null {
  if (containsPhrase(norm, 'last') || containsPhrase(norm, 'mwisho')) {
    return listLength - 1;
  }
  // "number 2", "namba 3", "no 4", "#5", or a bare small number.
  const numMatch = norm.match(/\b(?:number|namba|no|nambari|#)?\s*(\d{1,2})\b/);
  if (numMatch) {
    const idx = parseInt(numMatch[1], 10) - 1;
    if (idx >= 0) return idx;
  }
  for (const [word, idx] of Object.entries(ORDINALS)) {
    if (containsPhrase(norm, word)) return idx;
  }
  return null;
}

/**
 * Decide whether `message` is a follow-up to the previous turn.
 *
 * @param message Raw user message.
 * @param state   Previous conversation state (may have empty lastResults).
 */
export function resolveFollowup(
  message: string,
  state: ConversationState | null,
): Followup | null {
  if (!state || (state.lastResults.length === 0 && !state.lastItem)) return null;

  const norm = normalize(message);
  if (!norm) return null;

  const tokenCount = norm.split(' ').length;
  const hasExplainTrigger = EXPLAIN_TRIGGERS.some((t) => containsPhrase(norm, t));
  const hasPronoun = PRONOUNS.some((p) => containsPhrase(norm, p));

  // 1. Ordinal / numeric selection → explain that item from the last list.
  //    Checked first so "the second one" wins over any stray keywords.
  const ord = parseOrdinal(norm, state.lastResults.length);
  if (ord !== null && ord >= 0 && ord < state.lastResults.length) {
    // Only treat as a reference when it's short, or clearly a reference
    // (explain trigger / pronoun) — avoids hijacking sentences that merely
    // contain a number.
    if (hasExplainTrigger || hasPronoun || tokenCount <= 5) {
      return { kind: 'explain', index: ord };
    }
  }

  // 2. Pronoun reference with an explain trigger → explain the most recently
  //    referenced item (index -1), e.g. "tell me more about it / kuhusu hiyo".
  //    This runs BEFORE the "more" check because phrases like "tell me more
  //    about it" contain the word "more" but are explain requests, not "next page".
  if (hasExplainTrigger && hasPronoun) {
    return { kind: 'explain', index: -1 };
  }

  // 3. "more" / "others" → paginate, but only if items remain unshown.
  const wantsMore = MORE_KEYWORDS.some((k) => containsPhrase(norm, k));
  if (wantsMore && state.shownCount < state.lastResults.length) {
    // Keep it simple: short messages or an explicit "more/zaidi" win.
    if (tokenCount <= 5 || containsPhrase(norm, 'more') || containsPhrase(norm, 'zaidi')) {
      return { kind: 'more' };
    }
  }

  return null;
}
