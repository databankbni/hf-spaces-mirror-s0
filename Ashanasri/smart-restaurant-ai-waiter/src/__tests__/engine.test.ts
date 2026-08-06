/**
 * Lightweight engine tests using the built-in Node test runner.
 *
 * Run with:  npm run build && node --test dist/__tests__/engine.test.js
 * (or with ts-node if preferred). These cover the deterministic core — intent
 * detection and menu filtering — which is where the real logic lives.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { detectIntent } from '../engine/intent.engine';
import { filterMenu } from '../engine/menu.filter';
import { buildResponse } from '../engine/response.builder';
import { AiService } from '../services/ai.service';
import { ConversationService } from '../services/conversation.service';
import { MenuService } from '../services/menu.service';
import { MenuItem } from '../types';

function item(partial: Partial<MenuItem>): MenuItem {
  return {
    id: partial.id ?? '1',
    name: partial.name ?? 'Test',
    description: partial.description ?? '',
    price: partial.price ?? null,
    calories: partial.calories ?? null,
    ingredients: partial.ingredients ?? '',
    allergens: partial.allergens ?? '',
    tags: partial.tags ?? [],
    is_available: partial.is_available ?? true,
    image: partial.image ?? '',
    protein: partial.protein ?? null,
    fat: partial.fat ?? null,
    carbs: partial.carbs ?? null,
    category: partial.category ?? { name: 'Main Dishes' },
  };
}

const MENU: MenuItem[] = [
  item({ id: '1', name: 'Pilau', description: 'Spiced rice with meat', price: 15000, calories: 650, ingredients: 'Rice, beef, spices', tags: ['popular', 'lunch'] }),
  item({ id: '2', name: 'Vegetable Soup', price: 8000, calories: 180, tags: ['vegetarian', 'low-calorie', 'healthy'] }),
  item({ id: '3', name: 'Fruit Bowl', price: 6000, calories: 220, tags: ['vegan', 'healthy', 'low-calorie'] }),
  item({ id: '4', name: 'Nyama Choma', price: 20000, calories: 800, allergens: '', tags: ['popular', 'spicy'] }),
  item({ id: '5', name: 'Peanut Stew', price: 9000, calories: 500, allergens: 'nuts', ingredients: 'peanuts, vegetables', tags: [] }),
];

test('intent: english healthy', () => {
  assert.equal(detectIntent('I want something healthy').intent, 'healthy_food');
});

test('intent: swahili healthy', () => {
  assert.equal(detectIntent('chakula gani cha afya?').intent, 'healthy_food');
});

test('intent: explain_food extracts dish name', () => {
  const r = detectIntent('tell me about pilau');
  assert.equal(r.intent, 'explain_food');
  assert.equal(r.entity, 'pilau');
});

test('intent: cheapest', () => {
  assert.equal(detectIntent('what is the cheapest food').intent, 'cheapest_food');
});

test('intent: unknown', () => {
  assert.equal(detectIntent('asdfghjkl qwerty').intent, 'unknown');
});

test('intent: confidence between 0 and 1', () => {
  const r = detectIntent('recommend something popular');
  assert.ok(r.confidence > 0 && r.confidence <= 1);
});

test('filter: low_calorie returns items under 500 sorted asc', () => {
  const out = filterMenu(MENU, detectIntent('low calorie please'), 'low calorie please');
  assert.ok(out.items.length >= 2);
  assert.equal(out.items[0].name, 'Vegetable Soup');
  assert.ok(out.items.every((i) => (i.calories ?? 0) < 500 || i.tags.includes('low-calorie')));
});

test('filter: cheapest sorts by price ascending', () => {
  const out = filterMenu(MENU, detectIntent('cheapest food'), 'cheapest food');
  assert.equal(out.items[0].name, 'Fruit Bowl');
});

test('filter: allergen_check excludes nut dishes', () => {
  const out = filterMenu(MENU, detectIntent('I am allergic to nuts'), 'I am allergic to nuts');
  assert.ok(out.items.every((i) => i.name !== 'Peanut Stew'));
});

test('filter: explain_food finds the dish', () => {
  const out = filterMenu(MENU, detectIntent('tell me about pilau'), 'tell me about pilau');
  assert.equal(out.items.length, 1);
  assert.equal(out.items[0].name, 'Pilau');
});

test('filter: explain_food unknown dish -> notFound', () => {
  const out = filterMenu(MENU, detectIntent('tell me about sushi'), 'tell me about sushi');
  assert.equal(out.notFound, true);
});

test('builder: never returns empty reply', () => {
  const intent = detectIntent('I want something healthy');
  const out = filterMenu(MENU, intent, 'I want something healthy');
  const built = buildResponse(intent, out, false);
  assert.ok(built.reply.length > 0);
  assert.ok(built.suggestions.length > 0);
});

test('builder: empty menu handled gracefully', () => {
  const intent = detectIntent('recommend something');
  const built = buildResponse(intent, { items: [] }, true);
  assert.ok(/menu/i.test(built.reply));
});

/* ── Multi-turn conversation memory ─────────────────────────────────────── */

/**
 * A stub MenuService that always returns the given menu (no network).
 * The LLM param is omitted (null) so tests always run the rule-based brain —
 * fast, deterministic, offline.
 */
function makeAi(menu: MenuItem[] = MENU): AiService {
  const stubMenus = {
    getMenu: async () => ({ restaurant: { name: 'Test' }, menuItems: menu }),
    getMenuItems: async () => menu,
  } as unknown as MenuService;
  return new AiService(stubMenus, new ConversationService());
}

/** A larger menu (8 priced items) so pagination has a second page. */
const BIG_MENU: MenuItem[] = Array.from({ length: 8 }, (_, i) =>
  item({ id: `b${i}`, name: `Dish ${i + 1}`, price: 1000 * (i + 1), calories: 300 }),
);

test('conversation: response includes a sessionId', async () => {
  const ai = makeAi();
  const r = await ai.handleChat('demo', 'cheapest food');
  assert.ok(r.sessionId && r.sessionId.length > 0);
});

test('conversation: "the second one" explains item #2 of the previous list', async () => {
  const ai = makeAi();
  const r1 = await ai.handleChat('demo', 'cheapest food');
  const secondName = r1.results[1].name;
  const r2 = await ai.handleChat('demo', 'tell me about the second one', r1.sessionId);
  assert.equal(r2.intent, 'explain_food');
  assert.equal(r2.results.length, 1);
  assert.equal(r2.results[0].name, secondName);
});

test('conversation: "show me more" paginates the previous list', async () => {
  const ai = makeAi(BIG_MENU);
  const r1 = await ai.handleChat('demo', 'cheapest food');
  const firstBatch = new Set(r1.results.slice(0, 5).map((x) => x.name));
  const r2 = await ai.handleChat('demo', 'show me more', r1.sessionId);
  // The "more" batch must be different items than the first 5 shown.
  assert.ok(r2.results.length > 0);
  assert.ok(r2.results.every((x) => !firstBatch.has(x.name)));
});

test('conversation: Swahili "ya pili" selects the second item', async () => {
  const ai = makeAi();
  const r1 = await ai.handleChat('demo', 'popular foods');
  const r2 = await ai.handleChat('demo', 'niambie kuhusu ya pili', r1.sessionId);
  assert.equal(r2.intent, 'explain_food');
  assert.equal(r2.results[0].name, r1.results[1].name);
});

test('conversation: no session context → follow-up words act as new query', async () => {
  const ai = makeAi();
  // "more" with no prior turn should NOT crash; falls through to intent engine.
  const r = await ai.handleChat('demo', 'show me more');
  assert.ok(r.sessionId);
  // unknown/menu-ish, but importantly it returns a valid reply.
  assert.ok(r.reply.length > 0);
});
