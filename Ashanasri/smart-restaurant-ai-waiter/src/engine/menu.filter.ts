import { IntentResult, MenuItem } from '../types';
import { normalize, containsPhrase, bestNameMatch } from '../utils/text.parser';

/**
 * Menu Filter Engine
 * -------------------
 * Pure functions that take the LIVE menu (from the backend) plus the detected
 * intent and return the subset of items that answer the user's request.
 *
 * GUARANTEES:
 *  - Never invents items. Every returned item is a reference to a real
 *    backend-provided MenuItem.
 *  - Never assumes missing data. Null calories/price are handled explicitly.
 *  - Only available items are surfaced (except menu_overview, which can note
 *    unavailable ones, and explain_food which can still describe an item).
 */

const LOW_CALORIE_THRESHOLD = 500;
/** Items in this band are considered "balanced/healthy" when no other signal exists. */
const HEALTHY_CALORIE_MAX = 650;

/** Common allergen vocabulary used to interpret allergen_check requests. */
const KNOWN_ALLERGENS = [
  'nut', 'nuts', 'peanut', 'peanuts',
  'gluten', 'wheat',
  'dairy', 'milk', 'lactose',
  'egg', 'eggs',
  'soy', 'soya',
  'shellfish', 'shrimp', 'prawn', 'crab',
  'fish',
  'sesame',
];

function isAvailable(item: MenuItem): boolean {
  return item.is_available === true;
}

function hasTag(item: MenuItem, tag: string): boolean {
  const target = normalize(tag);
  return item.tags.some((t) => normalize(t) === target);
}

/** True if any of the item's tags loosely matches any of the given tags. */
function hasAnyTag(item: MenuItem, tags: string[]): boolean {
  return tags.some((t) => hasTag(item, t));
}

/**
 * Extract the allergen(s) the user wants to avoid from their message/entity.
 * Falls back to scanning the whole message for known allergen words.
 */
export function extractAllergens(message: string): string[] {
  const norm = normalize(message);
  const found = new Set<string>();
  for (const allergen of KNOWN_ALLERGENS) {
    if (containsPhrase(norm, allergen)) found.add(allergen);
  }
  return [...found];
}

/** Does the item declare / contain a given allergen (via allergens or ingredients)? */
function itemContainsAllergen(item: MenuItem, allergen: string): boolean {
  const a = normalize(allergen);
  return (
    containsPhrase(item.allergens, a) ||
    containsPhrase(item.ingredients, a) ||
    item.tags.some((t) => containsPhrase(t, a))
  );
}

/* ----------------------------------------------------------------------------
 * Per-intent filters
 * ------------------------------------------------------------------------- */

function filterLowCalorie(items: MenuItem[]): MenuItem[] {
  // A guest asking for low-calorie FOOD doesn't want to be told "drink water" —
  // exclude beverages; a real waiter recommends light meals, not drinks.
  return items
    .filter(isAvailable)
    .filter((i) => !isDrink(i))
    .filter(
      (i) =>
        hasTag(i, 'low-calorie') ||
        hasTag(i, 'low calorie') ||
        (i.calories !== null && i.calories < LOW_CALORIE_THRESHOLD),
    )
    .sort((a, b) => (a.calories ?? Infinity) - (b.calories ?? Infinity));
}

function filterByTag(items: MenuItem[], tags: string[]): MenuItem[] {
  return items.filter(isAvailable).filter((i) => hasAnyTag(i, tags));
}

function filterCheapest(items: MenuItem[]): MenuItem[] {
  return items
    .filter(isAvailable)
    .filter((i) => i.price !== null)
    .sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
}

function filterAllergenSafe(items: MenuItem[], allergens: string[]): MenuItem[] {
  const available = items.filter(isAvailable);
  if (allergens.length === 0) {
    // No specific allergen detected: return items that explicitly declare no allergens.
    return available.filter((i) => normalize(i.allergens) === '');
  }
  return available.filter((i) => !allergens.some((a) => itemContainsAllergen(i, a)));
}

/** Category names we treat as drinks — excluded from FOOD recommendations. */
const DRINK_CATEGORIES = [
  'beverages', 'drinks', 'beverage', 'drink', 'juices', 'juice',
  'smoothies', 'hot drinks', 'cold drinks', 'vinywaji',
];

function categoryName(item: MenuItem): string {
  return normalize(item.category?.name ?? '');
}

/** Is this item a drink (by category or tag)? */
function isDrink(item: MenuItem): boolean {
  const cat = categoryName(item);
  if (DRINK_CATEGORIES.some((d) => cat.includes(d))) return true;
  return item.tags.some((t) => /beverage|drink|juice|smoothie|soda|coffee|tea/i.test(t));
}

/**
 * Health score for an item. Higher = healthier. We reward explicit health
 * signals (tags, veg, low calories) and penalize sugary desserts, so a waiter
 * recommends real nutritious food first — not soda just because it's low-cal.
 */
function healthScore(item: MenuItem): number {
  let score = 0;
  if (hasAnyTag(item, ['healthy', 'nutritious'])) score += 4;
  if (hasTag(item, 'low-calorie')) score += 2;
  if (hasAnyTag(item, ['vegetarian', 'vegan'])) score += 1.5;

  if (item.calories !== null) {
    if (item.calories <= 400) score += 1.5;
    else if (item.calories <= HEALTHY_CALORIE_MAX) score += 0.5;
    else if (item.calories > 800) score -= 1.5;
  }

  // Sugary desserts aren't "healthy" unless explicitly tagged so.
  if (categoryName(item) === 'desserts' && !hasAnyTag(item, ['healthy', 'low-calorie'])) {
    score -= 2;
  }
  return score;
}

/**
 * Healthy food = nutritious *food* recommendations. We exclude drinks (a glass
 * of water isn't a "healthy meal"), score the rest, keep only positively-scored
 * items, and order by health score (then by calories ascending as a tiebreak).
 */
function filterHealthy(items: MenuItem[]): MenuItem[] {
  return items
    .filter(isAvailable)
    .filter((i) => !isDrink(i)) // food only
    .map((item) => ({ item, score: healthScore(item) }))
    .filter((s) => s.score > 0)
    .sort((a, b) =>
      b.score !== a.score
        ? b.score - a.score
        : (a.item.calories ?? Infinity) - (b.item.calories ?? Infinity),
    )
    .map((s) => s.item);
}

/**
 * Recommendation = blend of "popular", balanced calories and availability.
 * We score each available item and return the top picks.
 */
function filterRecommendation(items: MenuItem[]): MenuItem[] {
  const available = items.filter(isAvailable);

  const scored = available.map((item) => {
    let score = 0;
    if (hasAnyTag(item, ['popular', 'best-seller', 'bestseller', 'recommended'])) score += 3;
    if (hasAnyTag(item, ['healthy', 'nutritious'])) score += 1.5;
    // Reward balanced calories (not too light, not too heavy).
    if (item.calories !== null) {
      if (item.calories >= 350 && item.calories <= HEALTHY_CALORIE_MAX) score += 1.5;
      else if (item.calories < 350) score += 0.5;
    }
    // Mild reward for having a description (better waiter explanation).
    if (normalize(item.description).length > 0) score += 0.25;
    return { item, score };
  });

  scored.sort((a, b) => b.score - a.score);

  // If nothing scored above zero, fall back to first few available items
  // (still real menu items — never invented).
  const positive = scored.filter((s) => s.score > 0);
  const chosen = (positive.length ? positive : scored).slice(0, 5);
  return chosen.map((s) => s.item);
}

/**
 * Find a real menu item the text refers to. A waiter "knows the menu", so we
 * match generously:
 *   1. A full item name appearing as a phrase in the text (strongest).
 *   2. Otherwise a fuzzy best-match over item names (typo / partial tolerant).
 * Returns null when nothing clears the bar — we never invent a dish.
 */
export function findItemByName(
  items: MenuItem[],
  text: string,
  threshold = 0.62,
): MenuItem | null {
  const query = (text ?? '').trim();
  if (!query) return null;

  // 1. Direct containment — "...cha pilau ni..." contains "Pilau".
  //    Prefer the longest name match so "coconut fish curry" beats "fish".
  let contained: MenuItem | null = null;
  for (const it of items) {
    if (containsPhrase(query, it.name)) {
      if (!contained || it.name.length > contained.name.length) contained = it;
    }
  }
  if (contained) return contained;

  // 2. Fuzzy match over names.
  const match = bestNameMatch(query, items.map((i) => i.name), threshold);
  if (match) return items.find((i) => i.name === match.value) ?? null;

  // 3. Content-word match across name + description + ingredients. Lets the
  //    waiter recognise a dish from its qualities ("white rice" → "Plain Rice"
  //    whose description is "Steamed white rice"). Guarded to avoid weak hits.
  const STOP = new Set([
    'what', 'about', 'how', 'the', 'a', 'an', 'is', 'are', 'do', 'you', 'have',
    'want', 'need', 'some', 'something', 'of', 'today', 'please', 'and', 'or',
    'me', 'give', 'with', 'for', 'this', 'that', 'dish', 'food', 'meal', 'any',
    'cha', 'ya', 'wa', 'na', 'ni', 'chakula', 'gani', 'hapa', 'tafadhali', 'nipe',
    'nataka', 'kuna', 'mna',
  ]);
  const qWords = normalize(query)
    .split(' ')
    .filter((w) => w.length >= 3 && !STOP.has(w));

  if (qWords.length) {
    let best: { item: MenuItem; score: number; nameHit: boolean } | null = null;
    for (const it of items) {
      const name = normalize(it.name);
      const hay = normalize(`${it.description} ${it.ingredients}`);
      let score = 0;
      let nameHit = false;
      for (const w of qWords) {
        if (containsPhrase(name, w)) {
          score += 2;
          nameHit = true;
        } else if (containsPhrase(hay, w)) {
          score += 1;
        }
      }
      if (!best || score > best.score) best = { item: it, score, nameHit };
    }
    // Require a confident signal: a name-word hit, or several content hits.
    if (best && (best.score >= 3 || (best.nameHit && best.score >= 2))) {
      return best.item;
    }
  }

  return null;
}

/**
 * explain_food: locate the single item the user asked about. Tries the
 * extracted entity first, then falls back to scanning the whole message.
 */
function findExplainTarget(
  items: MenuItem[],
  intent: IntentResult,
  originalMessage: string,
): MenuItem[] {
  const fromEntity = intent.entity ? findItemByName(items, intent.entity, 0.6) : null;
  const target = fromEntity ?? findItemByName(items, originalMessage, 0.66);
  return target ? [target] : [];
}

/* ----------------------------------------------------------------------------
 * Public entry point
 * ------------------------------------------------------------------------- */

export interface FilterOutput {
  items: MenuItem[];
  /** Allergens detected (only for allergen_check), for the response builder. */
  allergens?: string[];
  /** True when the user named a dish we could not find (explain_food). */
  notFound?: boolean;
}

/**
 * Apply the correct filter for the given intent over the live menu.
 */
export function filterMenu(
  items: MenuItem[],
  intent: IntentResult,
  originalMessage: string,
): FilterOutput {
  switch (intent.intent) {
    case 'low_calorie':
      return { items: filterLowCalorie(items) };

    case 'vegetarian':
      return { items: filterByTag(items, ['vegetarian', 'veggie']) };

    case 'vegan':
      return { items: filterByTag(items, ['vegan', 'plant-based']) };

    case 'spicy_food':
      return { items: filterByTag(items, ['spicy', 'hot']) };

    case 'popular_foods':
      return { items: filterByTag(items, ['popular', 'best-seller', 'bestseller']) };

    case 'cheapest_food':
      return { items: filterCheapest(items) };

    case 'healthy_food':
      return { items: filterHealthy(items) };

    case 'recommendation':
      return { items: filterRecommendation(items) };

    case 'allergen_check': {
      const allergens = intent.entity
        ? extractAllergens(intent.entity).length
          ? extractAllergens(intent.entity)
          : extractAllergens(originalMessage)
        : extractAllergens(originalMessage);
      return { items: filterAllergenSafe(items, allergens), allergens };
    }

    case 'explain_food': {
      const target = findExplainTarget(items, intent, originalMessage);
      return { items: target, notFound: target.length === 0 };
    }

    case 'menu_overview':
      // For an overview we surface available items (ordered by category name).
      return {
        items: items
          .filter(isAvailable)
          .sort((a, b) =>
            (a.category?.name ?? '').localeCompare(b.category?.name ?? ''),
          ),
      };

    case 'unknown':
    default:
      return { items: [] };
  }
}

export const __internals = {
  LOW_CALORIE_THRESHOLD,
  HEALTHY_CALORIE_MAX,
  itemContainsAllergen,
  filterRecommendation,
};
