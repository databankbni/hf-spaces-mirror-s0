import { z } from 'zod';

/**
 * Shared type contracts for the AI Waiter Service.
 *
 * The shapes here mirror the data returned by the existing Django backend
 * (`GET /api/restaurants/:slug/menu/`). We validate the backend payload with
 * Zod so a malformed/partial response can never crash the engine — anything
 * unexpected is coerced to a safe default instead of being trusted blindly.
 */

/* ----------------------------------------------------------------------------
 * Intents
 * ------------------------------------------------------------------------- */

export const INTENTS = [
  'explain_food',
  'low_calorie',
  'vegetarian',
  'vegan',
  'allergen_check',
  'recommendation',
  'popular_foods',
  'menu_overview',
  'cheapest_food',
  'spicy_food',
  'healthy_food',
  'greeting',
  'unknown',
] as const;

export type Intent = (typeof INTENTS)[number];

/** Result of running the intent engine over a user message. */
export interface IntentResult {
  intent: Intent;
  confidence: number; // 0..1
  /** Matched keyword tokens, kept for debugging / transparency. */
  matchedKeywords: string[];
  /**
   * Free-text entity the user referred to (e.g. a dish name for
   * `explain_food`, or an allergen for `allergen_check`). May be null.
   */
  entity: string | null;
}

/* ----------------------------------------------------------------------------
 * Menu domain models (validated against the backend response)
 * ------------------------------------------------------------------------- */

export const CategorySchema = z
  .object({
    name: z.string().default('Uncategorized'),
  })
  .passthrough();

/**
 * `tags`, `allergens` and `ingredients` come from the backend in slightly
 * inconsistent shapes across environments (string vs array vs null). We
 * normalize them via preprocessors so the engine always sees clean data.
 */
const TagsSchema = z.preprocess((val) => {
  if (Array.isArray(val)) return val.map((t) => String(t));
  if (typeof val === 'string') {
    return val
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean);
  }
  return [];
}, z.array(z.string()));

const TextOrEmpty = z.preprocess((val) => {
  if (val === null || val === undefined) return '';
  return String(val);
}, z.string());

const NullableNumber = z.preprocess((val) => {
  if (val === null || val === undefined || val === '') return null;
  const n = Number(val);
  return Number.isFinite(n) ? n : null;
}, z.number().nullable());

export const MenuItemSchema = z
  .object({
    id: z.union([z.string(), z.number()]).transform((v) => String(v)),
    name: z.string().default('Unnamed item'),
    description: TextOrEmpty,
    price: NullableNumber,
    calories: NullableNumber,
    // Auto-computed nutrition from the backend (grams per portion), when present.
    protein: NullableNumber,
    fat: NullableNumber,
    carbs: NullableNumber,
    ingredients: TextOrEmpty,
    allergens: TextOrEmpty,
    tags: TagsSchema,
    is_available: z.preprocess(
      (v) => (v === undefined || v === null ? true : Boolean(v)),
      z.boolean(),
    ),
    /** Photo URL of the dish (backend may send image / image_url / photo). */
    image: TextOrEmpty,
    category: CategorySchema.nullable().default(null),
  })
  .passthrough();

export type MenuItem = z.infer<typeof MenuItemSchema>;

export const RestaurantSchema = z
  .object({
    name: z.string().optional(),
    slug: z.string().optional(),
  })
  .passthrough();

export type Restaurant = z.infer<typeof RestaurantSchema>;

export const MenuResponseSchema = z.object({
  restaurant: RestaurantSchema.nullable().default(null),
  // Accept both `menuItems` (documented) and `menu_items` (snake_case) just in case.
  menuItems: z.array(MenuItemSchema).default([]),
});

export type MenuResponse = z.infer<typeof MenuResponseSchema>;

/* ----------------------------------------------------------------------------
 * Chat API contract
 * ------------------------------------------------------------------------- */

export const ChatRequestSchema = z.object({
  restaurantSlug: z
    .string()
    .trim()
    .min(1, 'restaurantSlug is required')
    .max(200)
    .regex(/^[a-zA-Z0-9._~-]+$/, 'restaurantSlug contains invalid characters'),
  message: z.string().trim().min(1, 'message is required').max(1000),
  // Optional conversation id. Omit on the first message; the service returns
  // one in the response, and the client sends it back on follow-up messages
  // so the waiter can remember the conversation.
  sessionId: z
    .string()
    .trim()
    .max(100)
    .regex(/^[a-zA-Z0-9._-]+$/, 'sessionId contains invalid characters')
    .optional(),
});

export type ChatRequest = z.infer<typeof ChatRequestSchema>;

/** A trimmed-down menu item returned to the frontend in `results`. */
export interface ResultItem {
  id: string;
  name: string;
  description: string;
  price: number | null;
  calories: number | null;
  protein: number | null;
  fat: number | null;
  carbs: number | null;
  category: string;
  tags: string[];
  is_available: boolean;
  /** Photo URL ('' when the backend has no image for this dish). */
  image: string;
}

export interface ChatResponse {
  /** Conversation id. Echo this back on the next message to keep context. */
  sessionId: string;
  intent: Intent;
  confidence: number;
  results: ResultItem[];
  reply: string;
  suggestions: string[];
  /** Which brain produced the reply: Groq LLM or the rule-based fallback. */
  engine: 'llm' | 'rules';
  /**
   * Present when this turn added items to the guest's cart. The frontend
   * should add these to the app cart (by menu item `id`); the guest then
   * completes the order themselves in the Cart section (table number etc.).
   */
  cart?: {
    items: {
      id: string;
      name: string;
      quantity: number;
      price: number | null;
      subtotal: number | null;
    }[];
    total: number;
  } | null;
}
