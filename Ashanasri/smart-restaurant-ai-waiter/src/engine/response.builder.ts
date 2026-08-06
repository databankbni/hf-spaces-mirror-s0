import { Intent, IntentResult, MenuItem } from '../types';
import { FilterOutput } from './menu.filter';

/**
 * Response Builder (Waiter Persona)
 * ---------------------------------
 * Turns filtered menu data into a warm, polite, professional waiter reply.
 *
 * Principles:
 *  - Never emit raw JSON to the user.
 *  - Never invent items — only describe what the filter returned.
 *  - Always close with a helpful next-step suggestion.
 *  - Light bilingual flavour (English with the occasional Swahili touch).
 */

/** How many items we list inline in a reply before summarizing the rest. */
export const MAX_LISTED = 5;

function formatPrice(price: number | null): string {
  if (price === null) return '';
  // Professional currency format: "TZS 15,000" (currency first, separators).
  return ` — TZS ${price.toLocaleString('en-US')}`;
}

function formatCalories(calories: number | null): string {
  if (calories === null) return '';
  return ` (${calories} cal)`;
}

/** Render a single menu line: "1. Pilau — 15,000 TZS (650 cal)" */
function line(index: number, item: MenuItem): string {
  return `${index + 1}. ${item.name}${formatPrice(item.price)}${formatCalories(item.calories)}`;
}

/** Build a numbered list (capped) plus a "+N more" note when long. */
function bulletList(items: MenuItem[]): string {
  const shown = items.slice(0, MAX_LISTED).map((it, i) => line(i, it));
  let out = shown.join('\n');
  if (items.length > MAX_LISTED) {
    out += `\n…and ${items.length - MAX_LISTED} more on the menu.`;
  }
  return out;
}

/* ----------------------------------------------------------------------------
 * Suggestions (follow-up actions) per intent
 * ------------------------------------------------------------------------- */

const SUGGESTIONS: Record<Intent, string[]> = {
  explain_food: [
    'Would you like me to recommend something similar?',
    'Shall I add this to your order?',
  ],
  low_calorie: [
    'Would you like vegetarian or high-protein options as well?',
    'Shall I show you our healthiest dishes?',
  ],
  vegetarian: [
    'Would you like to see vegan options too?',
    'Shall I recommend a popular vegetarian dish?',
  ],
  vegan: [
    'Would you like to see vegetarian options as well?',
    'Shall I tell you more about any of these?',
  ],
  allergen_check: [
    'Would you like me to double-check another ingredient?',
    'Shall I recommend a safe popular dish?',
  ],
  recommendation: [
    'Would you like a lighter or a heartier option?',
    'Shall I tell you more about any of these?',
  ],
  popular_foods: [
    'Would you like me to describe any of these?',
    'Shall I suggest something healthy instead?',
  ],
  menu_overview: [
    'Would you like recommendations?',
    'Are you in the mood for something healthy, popular, or spicy?',
  ],
  cheapest_food: [
    'Would you like to see our most popular dishes?',
    'Shall I recommend the best value meal?',
  ],
  spicy_food: [
    'Would you like something milder instead?',
    'Shall I pair this with a cooling side?',
  ],
  healthy_food: [
    'Would you like low-calorie or vegetarian options?',
    'Shall I recommend a balanced full meal?',
  ],
  greeting: [
    'Would you like to see the menu?',
    'Shall I recommend something popular?',
    'Are you in the mood for something healthy or light?',
  ],
  unknown: [
    'Would you like to see the menu?',
    'I can recommend something, find healthy options, or check for allergens — what would you like?',
  ],
};

/** Swahili quick-action suggestions, mirroring SUGGESTIONS per intent. */
const SUGGESTIONS_SW: Record<Intent, string[]> = {
  explain_food: ['Niwekee hii kwenye order', 'Nipendekezee kingine kama hiki'],
  low_calorie: ['Nionyeshe vya mboga pia', 'Nipendekezee mlo kamili wenye afya'],
  vegetarian: ['Nionyeshe vya vegan pia', 'Nipendekezee cha mboga kinachopendwa'],
  vegan: ['Nionyeshe vya vegetarian pia', 'Niambie zaidi kuhusu mojawapo'],
  allergen_check: ['Nikagulie kiungo kingine', 'Nipendekezee chakula salama'],
  recommendation: ['Nipe chepesi zaidi', 'Niambie zaidi kuhusu mojawapo'],
  popular_foods: ['Nieleze mojawapo', 'Nipendekezee chenye afya badala yake'],
  menu_overview: ['Nipendekezee chakula', 'Nataka chenye afya'],
  cheapest_food: ['Nionyeshe vinavyopendwa', 'Nipendekezee bora kwa bei'],
  spicy_food: ['Nipe kisicho kali sana', 'Niongezee kinywaji cha kupoza'],
  healthy_food: ['Nionyeshe vya kalori chache', 'Nipendekezee mlo kamili'],
  greeting: ['Nionyeshe menu', 'Nipendekezee chakula kinachopendwa'],
  unknown: ['Nionyeshe menu', 'Nipendekezee chakula'],
};

/** Pick the suggestion set matching the guest's language. */
function suggestionsFor(intent: Intent, lang: 'en' | 'sw'): string[] {
  const table = lang === 'sw' ? SUGGESTIONS_SW : SUGGESTIONS;
  return table[intent] ?? table.unknown;
}

/* ----------------------------------------------------------------------------
 * Per-intent reply text
 * ------------------------------------------------------------------------- */

function emptyMenuReply(): string {
  return (
    "I'm sorry, our menu doesn't seem to be available right now. " +
    'Please try again in a moment — samahani kwa usumbufu (sorry for the inconvenience).'
  );
}

function noResultsReply(intent: Intent): string {
  switch (intent) {
    case 'low_calorie':
      return "I'm sorry, I couldn't find any low-calorie dishes on the menu right now. Would you like me to suggest something light instead?";
    case 'vegetarian':
      return "I'm afraid we don't have any dishes marked vegetarian at the moment. Shall I check for other options for you?";
    case 'vegan':
      return "I'm afraid we don't have any vegan dishes available right now. Would you like to see vegetarian options instead?";
    case 'spicy_food':
      return "I'm sorry, I don't see any spicy dishes on the menu at the moment. Would you like a flavourful alternative?";
    case 'popular_foods':
      return "We don't have any dishes specially marked as popular right now, but I'd be happy to recommend something for you.";
    case 'cheapest_food':
      return "I'm sorry, prices don't seem to be listed at the moment. Shall I recommend a dish instead?";
    case 'healthy_food':
      return "I couldn't find dishes specifically marked as healthy right now. Would you like me to suggest a balanced option?";
    case 'allergen_check':
      return "I'm sorry, I couldn't confirm any dishes are free from that ingredient right now. To be safe, please ask our staff before ordering.";
    case 'recommendation':
      return "I'd love to recommend something, but the menu looks empty right now. Please try again shortly.";
    default:
      return "I'm sorry, I couldn't find anything matching that. Would you like to see the full menu?";
  }
}

function headerFor(intent: Intent): string {
  switch (intent) {
    case 'low_calorie':
      return 'Here are some light, low-calorie options:';
    case 'vegetarian':
      return 'Here are our vegetarian dishes:';
    case 'vegan':
      return 'Here are our vegan dishes:';
    case 'spicy_food':
      return 'Here are some dishes with a spicy kick:';
    case 'popular_foods':
      return 'Here are our most popular dishes — favourites with our guests:';
    case 'cheapest_food':
      return 'Here are our most affordable options:';
    case 'healthy_food':
      return 'Here are some healthy, nutritious choices:';
    case 'recommendation':
      return "Based on what our guests love, here's what I'd recommend:";
    case 'menu_overview':
      return "Here's a look at what we're serving today:";
    default:
      return 'Here are some options for you:';
  }
}

/**
 * menu_overview: a waiter wouldn't read out 70 items — they describe the menu
 * by section and name a couple of favourites, then offer to help narrow down.
 */
function buildMenuOverviewReply(items: MenuItem[]): BuiltResponse {
  const categories: string[] = [];
  for (const it of items) {
    const c = it.category?.name ?? 'Other';
    if (!categories.includes(c)) categories.push(c);
  }
  const favourites = items
    .filter((i) => i.tags.some((t) => /popular|best.?seller/i.test(t)))
    .slice(0, 3)
    .map((i) => i.name);

  let reply = `We're serving ${items.length} dishes today`;
  if (categories.length) {
    reply += `, across our ${categories.join(', ')} sections`;
  }
  reply += '.';
  if (favourites.length) {
    reply += ` Some guest favourites are ${favourites.join(', ')}.`;
  }
  reply +=
    '\n\nWould you like my recommendations, or are you after a particular kind of dish — something healthy, popular, vegetarian, or spicy?';

  return { reply, suggestions: SUGGESTIONS.menu_overview };
}

/** explain_food: describe a single dish in a warm, detailed way. */
function buildExplainReply(item: MenuItem): string {
  const parts: string[] = [];
  const desc = item.description?.trim();
  parts.push(`${item.name} is ${desc ? desc.replace(/\.$/, '') : 'one of our dishes'}.`);

  if (item.ingredients?.trim()) {
    parts.push(`It's made with ${item.ingredients.trim()}.`);
  }
  if (item.calories !== null) {
    parts.push(`It's around ${item.calories} calories.`);
  }
  if (item.price !== null) {
    parts.push(`It's priced at TZS ${item.price.toLocaleString('en-US')}.`);
  }
  if (item.allergens?.trim()) {
    parts.push(`Please note it contains: ${item.allergens.trim()}.`);
  }
  if (!item.is_available) {
    parts.push("Unfortunately it's not available right now.");
  }

  return parts.join(' ');
}

/** allergen_check: explain what we filtered and gently advise caution. */
function buildAllergenReply(items: MenuItem[], allergens: string[]): string {
  const avoiding = allergens.length
    ? allergens.join(', ')
    : 'common allergens';

  const intro = `Here are dishes that should be safe if you're avoiding ${avoiding}:`;
  const body = bulletList(items);
  const caution =
    "\n\nTo be completely safe, I'd recommend confirming with our kitchen staff before ordering.";
  return `${intro}\n\n${body}${caution}`;
}

/* ----------------------------------------------------------------------------
 * Public entry point
 * ------------------------------------------------------------------------- */

export interface BuiltResponse {
  reply: string;
  suggestions: string[];
}

/**
 * Build a reply for a "show me more" follow-up: continues the numbering from
 * where the previous list left off so references like "the 7th one" stay valid.
 *
 * @param items         The next batch of items to show.
 * @param startIndex    Zero-based index of the first item (for numbering).
 * @param remainingAfter How many items still remain after this batch.
 */
export function buildMoreReply(
  items: MenuItem[],
  startIndex: number,
  remainingAfter: number,
): BuiltResponse {
  if (items.length === 0) {
    return {
      reply:
        "That's everything I have for that. Would you like to try something else?",
      suggestions: SUGGESTIONS.unknown,
    };
  }
  const list = items.map((it, i) => line(startIndex + i, it)).join('\n');
  let reply = `Here are a few more options:\n\n${list}`;
  if (remainingAfter > 0) reply += `\n\n…and ${remainingAfter} more still.`;
  reply += '\n\nWould you like details on any of these?';
  return {
    reply,
    suggestions: ['Would you like details on any of these?', 'Shall I recommend one for you?'],
  };
}

/**
 * Build the final human-readable waiter reply + follow-up suggestions.
 *
 * @param intent     Detected intent.
 * @param filtered   Output of the menu filter.
 * @param menuEmpty  True when the backend returned no menu items at all.
 */
export function buildResponse(
  intent: IntentResult,
  filtered: FilterOutput,
  menuEmpty: boolean,
  lang: 'en' | 'sw' = 'en',
): BuiltResponse {
  const suggestions = suggestionsFor(intent.intent, lang);

  // 1. Greeting — welcome the guest like a real waiter (works even if menu empty).
  if (intent.intent === 'greeting') {
    return {
      reply:
        lang === 'sw'
          ? 'Karibu sana! Mimi ni mhudumu wako leo. Ungependa kuona menu, kupata mapendekezo yangu, au unatafuta kitu maalum — labda chenye afya, kinachopendwa, au cha kienyeji?'
          : "Karibu! Welcome to our restaurant. I'm your waiter today. " +
            "Would you like to see the menu, hear my recommendations, or are you in the mood for something in particular — maybe something healthy, popular, or a local favourite?",
      suggestions,
    };
  }

  // 2. Whole menu unavailable.
  if (menuEmpty) {
    return { reply: emptyMenuReply(), suggestions: suggestionsFor('unknown', lang) };
  }

  // 3. Unknown intent — friendly clarification.
  if (intent.intent === 'unknown') {
    return {
      reply:
        "I'm not quite sure what you're looking for, but I'm happy to help! " +
        'I can recommend dishes, find healthy or vegetarian options, check for allergens, ' +
        'or tell you about anything on the menu. What are you in the mood for?',
      suggestions,
    };
  }

  // 3. explain_food.
  if (intent.intent === 'explain_food') {
    if (filtered.notFound || filtered.items.length === 0) {
      return {
        reply:
          lang === 'sw'
            ? 'Samahani, hicho kimeisha kwa sasa au hakipo kwenye menu yetu leo. Ungependa nikupendekezee kitu kinachofanana nacho?'
            : "I'm sorry, that dish is finished for now or not on our menu today. " +
              'Would you like me to recommend something similar?',
        suggestions: suggestionsFor('recommendation', lang),
      };
    }
    return { reply: buildExplainReply(filtered.items[0]), suggestions };
  }

  // 4. allergen_check.
  if (intent.intent === 'allergen_check') {
    if (filtered.items.length === 0) {
      return { reply: noResultsReply('allergen_check'), suggestions };
    }
    return {
      reply: buildAllergenReply(filtered.items, filtered.allergens ?? []),
      suggestions,
    };
  }

  // 5. Menu overview — describe by section instead of dumping items.
  if (intent.intent === 'menu_overview') {
    if (filtered.items.length === 0) return { reply: emptyMenuReply(), suggestions };
    return buildMenuOverviewReply(filtered.items);
  }

  // 6. List-style intents (low_calorie, vegetarian, popular, etc.).
  if (filtered.items.length === 0) {
    return { reply: noResultsReply(intent.intent), suggestions };
  }

  const reply = `${headerFor(intent.intent)}\n\n${bulletList(filtered.items)}`;
  const closing = suggestions.length ? `\n\n${suggestions[0]}` : '';
  return { reply: `${reply}${closing}`, suggestions };
}
