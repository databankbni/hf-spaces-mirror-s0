import { Intent, IntentResult } from '../types';
import { normalize, tokenize, containsPhrase } from '../utils/text.parser';

/**
 * Intent Engine
 * --------------
 * Rule-based + keyword-weighted intent detection. NO machine learning.
 *
 * Each intent owns a set of bilingual (English + Swahili) keyword phrases,
 * each with a weight. We score every intent by summing the weights of the
 * phrases present in the (normalized) message, then convert the winning raw
 * score into a 0..1 confidence. This handles mixed-language input naturally
 * because English and Swahili keywords live in the same bucket.
 *
 * `explain_food` is special: it usually carries a dish-name entity ("tell me
 * about pilau"), so it gets a boost when an explain-trigger phrase is present.
 */

interface KeywordRule {
  phrase: string;
  weight: number;
}

/**
 * Keyword tables. Phrases are matched as whole words/phrases against the
 * normalized message. Swahili and English share the same list per intent.
 */
const KEYWORDS: Record<Exclude<Intent, 'unknown'>, KeywordRule[]> = {
  explain_food: [
    { phrase: 'tell me about', weight: 3 },
    { phrase: 'what is', weight: 2 },
    { phrase: "what's", weight: 2 },
    { phrase: 'what about', weight: 2 },
    { phrase: 'how about', weight: 2 },
    { phrase: 'describe', weight: 3 },
    { phrase: 'explain', weight: 3 },
    { phrase: 'details', weight: 2 },
    { phrase: 'info', weight: 1 },
    { phrase: 'ingredients of', weight: 2 },
    { phrase: 'is there', weight: 1 },
    { phrase: 'do you have', weight: 1 },
    // Swahili
    { phrase: 'niambie kuhusu', weight: 3 },
    { phrase: 'ni nini', weight: 2 },
    { phrase: 'ni chakula gani', weight: 2 },
    { phrase: 'eleza', weight: 3 },
    { phrase: 'maelezo', weight: 2 },
    { phrase: 'kuhusu', weight: 1 },
    { phrase: 'vipi kuhusu', weight: 2 },
  ],
  low_calorie: [
    { phrase: 'low calorie', weight: 3 },
    { phrase: 'low calories', weight: 3 },
    { phrase: 'low cal', weight: 2 },
    { phrase: 'fewer calories', weight: 2 },
    { phrase: 'light meal', weight: 2 },
    { phrase: 'light food', weight: 2 },
    { phrase: 'diet', weight: 2 },
    { phrase: 'less calories', weight: 2 },
    // Swahili (guests often mix "calories" with Swahili)
    { phrase: 'kalori chache', weight: 3 },
    { phrase: 'kalori ndogo', weight: 3 },
    { phrase: 'calories chache', weight: 3 },
    { phrase: 'calories ndogo', weight: 3 },
    { phrase: 'calorie chache', weight: 3 },
    { phrase: 'chakula chepesi', weight: 2 },
    { phrase: 'kitu chepesi', weight: 2 },
  ],
  vegetarian: [
    { phrase: 'vegetarian', weight: 3 },
    { phrase: 'veggie', weight: 2 },
    { phrase: 'no meat', weight: 2 },
    { phrase: 'without meat', weight: 2 },
    { phrase: 'meat free', weight: 2 },
    // Swahili
    { phrase: 'mboga', weight: 2 },
    { phrase: 'bila nyama', weight: 3 },
    { phrase: 'mlo wa mboga', weight: 3 },
  ],
  vegan: [
    { phrase: 'vegan', weight: 3 },
    { phrase: 'plant based', weight: 3 },
    { phrase: 'no animal', weight: 2 },
    { phrase: 'no dairy', weight: 1 },
    // Swahili
    { phrase: 'mboga tu', weight: 2 },
    { phrase: 'bila mazao ya wanyama', weight: 3 },
  ],
  allergen_check: [
    { phrase: 'allergy', weight: 3 },
    { phrase: 'allergic', weight: 3 },
    { phrase: 'allergen', weight: 3 },
    { phrase: 'without', weight: 1 },
    { phrase: 'no nuts', weight: 3 },
    { phrase: 'no gluten', weight: 3 },
    { phrase: 'gluten free', weight: 3 },
    { phrase: 'no dairy', weight: 2 },
    { phrase: 'no shellfish', weight: 3 },
    { phrase: 'free from', weight: 2 },
    // Swahili
    { phrase: 'mzio', weight: 3 },
    { phrase: 'aleji', weight: 3 },
    { phrase: 'bila', weight: 1 },
  ],
  recommendation: [
    { phrase: 'recommend', weight: 3 },
    { phrase: 'recommendation', weight: 3 },
    { phrase: 'suggest', weight: 3 },
    { phrase: 'what should i', weight: 3 },
    { phrase: 'what should i eat', weight: 3 },
    { phrase: 'what should i order', weight: 3 },
    { phrase: 'what do you suggest', weight: 3 },
    { phrase: 'best dish', weight: 2 },
    { phrase: 'whats good', weight: 2 },
    { phrase: 'whats nice', weight: 2 },
    { phrase: 'whats best', weight: 2 },
    { phrase: 'surprise me', weight: 2 },
    { phrase: 'help me choose', weight: 2 },
    { phrase: 'i dont know what to eat', weight: 2 },
    // Swahili
    { phrase: 'pendekeza', weight: 3 },
    { phrase: 'nipendekezee', weight: 3 },
    { phrase: 'unashauri', weight: 3 },
    { phrase: 'unashauri nini', weight: 3 },
    { phrase: 'nichague nini', weight: 2 },
    { phrase: 'nisaidie kuchagua', weight: 2 },
    { phrase: 'kitu kizuri', weight: 2 },
    { phrase: 'nipe kizuri', weight: 2 },
    // "Filling" requests — treat as a recommendation ask.
    { phrase: 'something filling', weight: 3 },
    { phrase: 'filling', weight: 2 },
    { phrase: 'kushiba', weight: 3 },
    { phrase: 'cha kushiba', weight: 3 },
    { phrase: 'nishibe', weight: 3 },
  ],
  popular_foods: [
    { phrase: 'popular', weight: 3 },
    { phrase: 'most ordered', weight: 3 },
    { phrase: 'best seller', weight: 3 },
    { phrase: 'bestseller', weight: 3 },
    { phrase: 'trending', weight: 2 },
    { phrase: 'favourite', weight: 2 },
    { phrase: 'favorite', weight: 2 },
    { phrase: 'top dishes', weight: 2 },
    // Swahili
    { phrase: 'maarufu', weight: 3 },
    { phrase: 'inayopendwa', weight: 3 },
    { phrase: 'zinazouzwa zaidi', weight: 3 },
  ],
  menu_overview: [
    { phrase: 'menu', weight: 2 },
    { phrase: 'what do you have', weight: 3 },
    { phrase: 'what do you serve', weight: 3 },
    { phrase: 'what do you offer', weight: 3 },
    { phrase: 'show me the menu', weight: 3 },
    { phrase: 'show me what you have', weight: 3 },
    { phrase: 'whats available', weight: 2 },
    { phrase: 'what is available', weight: 2 },
    { phrase: 'whats on the menu', weight: 3 },
    { phrase: 'whats cooking', weight: 2 },
    { phrase: 'dishes of today', weight: 3 },
    { phrase: 'todays dishes', weight: 3 },
    { phrase: 'todays menu', weight: 3 },
    { phrase: 'todays special', weight: 2 },
    { phrase: 'what are the dishes', weight: 3 },
    { phrase: 'what can i eat', weight: 2 },
    { phrase: 'what can i order', weight: 2 },
    { phrase: 'food today', weight: 2 },
    { phrase: 'options', weight: 1 },
    // Swahili
    { phrase: 'menyu', weight: 2 },
    { phrase: 'mna nini', weight: 3 },
    { phrase: 'mnauza nini', weight: 3 },
    { phrase: 'mna vyakula gani', weight: 3 },
    { phrase: 'orodha ya chakula', weight: 3 },
    { phrase: 'orodha', weight: 1 },
    { phrase: 'chakula cha leo', weight: 3 },
    { phrase: 'vyakula vya leo', weight: 3 },
    { phrase: 'mna chakula gani', weight: 2 },
  ],
  cheapest_food: [
    { phrase: 'cheapest', weight: 3 },
    { phrase: 'cheap', weight: 2 },
    { phrase: 'lowest price', weight: 3 },
    { phrase: 'affordable', weight: 2 },
    { phrase: 'budget', weight: 2 },
    { phrase: 'least expensive', weight: 3 },
    // Swahili
    { phrase: 'rahisi zaidi', weight: 3 },
    { phrase: 'bei nafuu', weight: 3 },
    { phrase: 'bei rahisi', weight: 3 },
  ],
  spicy_food: [
    { phrase: 'spicy', weight: 3 },
    { phrase: 'hot food', weight: 2 },
    { phrase: 'pilipili', weight: 3 },
    { phrase: 'chilli', weight: 2 },
    { phrase: 'chili', weight: 2 },
    // Swahili
    { phrase: 'kali', weight: 2 },
    { phrase: 'chenye pilipili', weight: 3 },
  ],
  greeting: [
    // Low weight on purpose: a real request in the same message should win.
    { phrase: 'hello', weight: 2 },
    { phrase: 'hi', weight: 2 },
    { phrase: 'hey', weight: 2 },
    { phrase: 'good morning', weight: 2 },
    { phrase: 'good afternoon', weight: 2 },
    { phrase: 'good evening', weight: 2 },
    { phrase: 'greetings', weight: 2 },
    // Swahili
    { phrase: 'habari', weight: 2 },
    { phrase: 'habari yako', weight: 2 },
    { phrase: 'mambo', weight: 2 },
    { phrase: 'mambo vipi', weight: 2 },
    { phrase: 'vipi', weight: 1 },
    { phrase: 'hujambo', weight: 2 },
    { phrase: 'salama', weight: 1 },
    { phrase: 'shikamoo', weight: 2 },
    { phrase: 'niaje', weight: 2 },
    // Thanks / goodbyes — also handled with a warm waiter reply.
    { phrase: 'thank you', weight: 2 },
    { phrase: 'thanks', weight: 2 },
    { phrase: 'asante', weight: 2 },
    { phrase: 'shukrani', weight: 2 },
    { phrase: 'bye', weight: 2 },
    { phrase: 'goodbye', weight: 2 },
    { phrase: 'kwaheri', weight: 2 },
  ],
  healthy_food: [
    { phrase: 'healthy', weight: 3 },
    { phrase: 'health', weight: 2 },
    { phrase: 'nutritious', weight: 3 },
    { phrase: 'good for me', weight: 2 },
    { phrase: 'clean eating', weight: 2 },
    { phrase: 'fit', weight: 1 },
    // Swahili
    { phrase: 'afya', weight: 3 },
    { phrase: 'chenye afya', weight: 3 },
    { phrase: 'chakula cha afya', weight: 3 },
    { phrase: 'lishe', weight: 2 },
  ],
};

/**
 * Phrases that, when present, indicate the user is asking us to describe a
 * specific dish. Used to lift `explain_food` when a dish name is also present.
 */
const EXPLAIN_TRIGGERS = [
  'tell me about',
  'what is',
  "what's",
  'what about',
  'how about',
  'describe',
  'explain',
  'niambie kuhusu',
  'eleza',
  'ni nini',
  'ni chakula gani',
  'kuhusu',
  'vipi kuhusu',
];

/**
 * Map of raw winning score -> confidence. We squash with a simple saturating
 * curve so a single strong keyword (weight 3) already yields high confidence,
 * while weak/ambiguous matches stay modest.
 */
function toConfidence(rawScore: number): number {
  if (rawScore <= 0) return 0;
  // saturating curve: 3 -> ~0.82, 6 -> ~0.92, asymptotes to ~0.97
  const conf = 1 - Math.exp(-rawScore / 2.2);
  return Math.min(0.97, Math.round(conf * 100) / 100);
}

/**
 * Attempt to extract a dish-name entity for `explain_food` by removing the
 * trigger phrases and common filler words, leaving the candidate name. The
 * menu filter later fuzzy-matches this against real menu items.
 */
function extractExplainEntity(message: string): string | null {
  let text = ` ${normalize(message)} `;
  for (const trigger of EXPLAIN_TRIGGERS) {
    text = text.replace(` ${normalize(trigger)} `, ' ');
  }
  const filler = new Set([
    'the', 'a', 'an', 'me', 'please', 'your', 'this', 'that',
    'dish', 'food', 'meal', 'tafadhali', 'chakula', 'hicho', 'hii',
  ]);
  const remaining = text
    .trim()
    .split(' ')
    .filter((w) => w && !filler.has(w));

  const entity = remaining.join(' ').trim();
  return entity.length ? entity : null;
}

/**
 * Set of every individual token that appears in any intent's keyword phrases.
 * Used to tell "is this leftover a real dish name?" apart from "is it just
 * another intent's keywords?" (e.g. the entity "cheapest" in
 * "what is the cheapest food" is a keyword, not a dish name).
 */
const ALL_KEYWORD_TOKENS: Set<string> = (() => {
  const set = new Set<string>();
  for (const rules of Object.values(KEYWORDS)) {
    for (const rule of rules) {
      for (const tok of normalize(rule.phrase).split(' ')) {
        if (tok) set.add(tok);
      }
    }
  }
  return set;
})();

/**
 * A leftover entity looks like a real dish name only if it contains at least
 * one token that is NOT a known intent keyword. This prevents "cheapest food",
 * "healthy meal" etc. from being mistaken for dish names.
 */
function looksLikeDishName(entity: string | null): boolean {
  if (!entity) return false;
  return normalize(entity)
    .split(' ')
    .some((tok) => tok.length > 1 && !ALL_KEYWORD_TOKENS.has(tok));
}

/**
 * Detect the intent of a user message.
 *
 * @param message Raw user message (any language / mixed).
 * @returns IntentResult with intent, confidence (0..1), matched keywords and
 *          an optional extracted entity.
 */
export function detectIntent(message: string): IntentResult {
  const normalized = normalize(message);

  if (!normalized) {
    return { intent: 'unknown', confidence: 0, matchedKeywords: [], entity: null };
  }

  const scores: Partial<Record<Intent, { score: number; matched: string[] }>> = {};

  for (const [intent, rules] of Object.entries(KEYWORDS) as [
    Exclude<Intent, 'unknown'>,
    KeywordRule[],
  ][]) {
    let score = 0;
    const matched: string[] = [];
    for (const rule of rules) {
      if (containsPhrase(normalized, rule.phrase)) {
        score += rule.weight;
        matched.push(rule.phrase);
      }
    }
    if (score > 0) scores[intent] = { score, matched };
  }

  // No keyword hit at all -> unknown.
  const entries = Object.entries(scores) as [
    Exclude<Intent, 'unknown'>,
    { score: number; matched: string[] },
  ][];
  if (entries.length === 0) {
    return { intent: 'unknown', confidence: 0.2, matchedKeywords: [], entity: null };
  }

  // Pick the highest scoring intent. Ties broken by declaration order in KEYWORDS.
  entries.sort((a, b) => b[1].score - a[1].score);
  let [winner, winnerData] = entries[0];

  // ── explain_food disambiguation ──────────────────────────────────────────
  // If an explain-trigger is present AND there's a leftover entity (likely a
  // dish name), strongly prefer explain_food. This resolves cases like
  // "what is the healthiest pilau" leaning to explain when a name is named.
  const hasExplainTrigger = EXPLAIN_TRIGGERS.some((t) => containsPhrase(normalized, t));
  const rawEntity = hasExplainTrigger ? extractExplainEntity(message) : null;
  // Only treat the leftover as a dish name (and prefer explain_food) when it
  // isn't simply another intent's keywords.
  const explainEntity = looksLikeDishName(rawEntity) ? rawEntity : null;

  if (hasExplainTrigger && explainEntity) {
    const explainScore = scores.explain_food?.score ?? 0;
    // Boost explain_food so a dish-name question wins over generic mentions.
    if (explainScore + 2 >= winnerData.score) {
      winner = 'explain_food';
      winnerData = {
        score: explainScore + 2,
        matched: scores.explain_food?.matched ?? ['(explain trigger + dish name)'],
      };
    }
  }

  const entity = winner === 'explain_food' ? explainEntity : null;

  return {
    intent: winner,
    confidence: toConfidence(winnerData.score),
    matchedKeywords: winnerData.matched,
    entity,
  };
}

/** Exposed for testing / debugging. */
export const __internals = { toConfidence, extractExplainEntity, tokenize, KEYWORDS };
