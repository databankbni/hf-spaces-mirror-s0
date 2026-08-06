import { ChatResponse, IntentResult, MenuItem, ResultItem } from '../types';
import { detectIntent } from '../engine/intent.engine';
import { filterMenu, findItemByName } from '../engine/menu.filter';
import { buildResponse, buildMoreReply, MAX_LISTED } from '../engine/response.builder';
import { resolveFollowup } from '../engine/followup.engine';
import { MenuService, menuService as defaultMenuService } from './menu.service';
import { LlmService, llmService as defaultLlmService } from './llm.service';
import { learningService } from './learning.service';
import { normalize, detectLanguage } from '../utils/text.parser';
import {
  ConversationService,
  ConversationState,
  conversationService as defaultConversationService,
} from './conversation.service';

/**
 * AI Service (Orchestrator)
 * -------------------------
 * The "digital waiter brain" — a HYBRID of two brains:
 *
 *  🧠 Groq LLM (primary): natural, conversational waiter replies, grounded on
 *     the live menu (RAG) + per-session chat history. This is what makes the
 *     waiter feel human and lets it answer anything about the food.
 *
 *  ⚙️ Rule engine (grounding + fallback): deterministic intent detection and
 *     menu filtering. It (a) picks the structured `results` for the frontend,
 *     (b) gives the LLM a relevance hint, and (c) fully takes over whenever
 *     the LLM is unavailable (no key, quota, timeout) — the service never dies.
 *
 * Pipeline per message:
 *   1. Fetch the live menu from the backend (MenuService — later the real
 *      Django DB endpoint; today the mock).
 *   2. Resolve follow-ups ("more", "the second one") via conversation memory.
 *   3. Otherwise detect intent + filter the menu.
 *   4. Ask Groq for the waiter reply (grounded); fall back to rules if needed.
 *   5. Record the turn in session history (the waiter "remembers" the chat).
 */

function toResultItem(item: MenuItem): ResultItem {
  return {
    id: item.id,
    name: item.name,
    description: item.description,
    price: item.price,
    calories: item.calories,
    protein: item.protein,
    fat: item.fat,
    carbs: item.carbs,
    category: item.category?.name ?? 'Uncategorized',
    tags: item.tags,
    is_available: item.is_available,
    image: item.image ?? '',
  };
}

/** Internal result of the deterministic stage, before the LLM pass. */
interface StagedResult {
  response: Omit<ChatResponse, 'engine'>;
  intent: IntentResult;
  shortlist: MenuItem[];
}

/**
 * Machine block the LLM appends when the guest confirms items for their cart.
 * (Accepts the legacy ORDER tag too, for robustness.)
 */
const CART_MARKER = /\[\[(?:CART|ORDER)\]\]\s*(\{[\s\S]*?\})\s*\[\[\/(?:CART|ORDER)\]\]/;

/** Machine block with contextual quick actions in the guest's language. */
const ACTIONS_MARKER = /\[\[ACTIONS\]\]\s*(\[[\s\S]*?\])\s*\[\[\/ACTIONS\]\]/;

/** Parse and sanitize the LLM's quick actions. Null when unusable. */
function parseActions(json: string): string[] | null {
  try {
    const arr: unknown = JSON.parse(json);
    if (!Array.isArray(arr)) return null;
    const actions = arr
      .filter((a): a is string => typeof a === 'string')
      .map((a) => a.trim())
      .filter((a) => a.length >= 2 && a.length <= 60)
      .slice(0, 4);
    return actions.length ? actions : null;
  } catch {
    return null;
  }
}

export class AiService {
  constructor(
    private readonly menus: MenuService = defaultMenuService,
    private readonly conversations: ConversationService = defaultConversationService,
    /**
     * LLM brain. `null` disables the LLM entirely (used by unit tests so they
     * stay fast and offline). The exported singleton wires the real Groq one.
     */
    private readonly llm: LlmService | null = null,
  ) {}

  /**
   * Run the full waiter pipeline for one message.
   *
   * @throws MenuFetchError when the backend menu cannot be retrieved.
   */
  public async handleChat(
    slug: string,
    message: string,
    sessionId?: string,
  ): Promise<ChatResponse> {
    const menu = await this.menus.getMenu(slug);
    const items = menu.menuItems;
    const menuEmpty = items.length === 0;
    const state = this.conversations.getOrCreate(sessionId);

    // 1. Deterministic stage: follow-up or fresh intent → structured results
    //    + a rule-based reply (which doubles as the fallback).
    const followup = menuEmpty ? null : resolveFollowup(message, state);
    const staged = followup
      ? this.handleFollowup(followup, state, detectLanguage(message))
      : this.handleNewIntent(message, items, menuEmpty, state);

    // Live learning: distil this turn into durable knowledge (trending dishes,
    // requested-but-missing items, unanswered questions, language mix).
    learningService.recordTurn(slug, {
      intent: staged.intent.intent,
      lang: detectLanguage(message),
      askedDish:
        staged.intent.intent === 'explain_food' && staged.shortlist[0]
          ? staged.shortlist[0].name
          : undefined,
      missingQuery:
        staged.intent.intent === 'explain_food' && staged.shortlist.length === 0
          ? (staged.intent.entity ?? message)
          : undefined,
      unansweredMessage:
        staged.intent.intent === 'unknown' ? message : undefined,
    });

    // 2. LLM stage: ask Groq for the natural waiter reply, grounded on the
    //    live menu + conversation history. Falls back to the rule reply.
    let reply = staged.response.reply;
    let engine: ChatResponse['engine'] = 'rules';
    if (this.llm?.isEnabled() && !menuEmpty) {
      const llmReply = await this.llm.generateReply({
        restaurant: menu.restaurant,
        menu: items,
        intent: staged.intent,
        shortlist: staged.shortlist,
        history: state.history,
        userMessage: message,
        trending: learningService.trendingDishes(slug),
        insights: learningService.promptInsights(slug),
      });
      if (llmReply) {
        reply = llmReply;
        engine = 'llm';
      }
    }

    // 2a. Contextual quick actions from the LLM (guest's language, current
    //     moment). Falls back to the static per-intent suggestions.
    let suggestions = staged.response.suggestions;
    const actionsMatch = reply.match(ACTIONS_MARKER);
    if (actionsMatch) {
      reply = reply.replace(ACTIONS_MARKER, '').trim();
      const actions = parseActions(actionsMatch[1]);
      if (actions) suggestions = actions;
    }

    // 2b. Did the waiter confirm items for the cart? Parse the machine block,
    //     validate against the REAL menu, and return structured cart data so
    //     the frontend adds them to the app's cart. The guest completes the
    //     order themselves in the Cart section (table number etc.).
    let cart: ChatResponse['cart'] = null;
    const markerMatch = reply.match(CART_MARKER);
    if (markerMatch) {
      reply = reply.replace(CART_MARKER, '').trim();
      cart = this.buildCartFromMarker(markerMatch[1], items);
      const lang = detectLanguage(message);
      if (cart) {
        reply +=
          lang === 'sw'
            ? '\n\nNimeviweka kwenye cart yako. Ukiwa tayari, fungua sehemu ya Cart ukamilishe order yako — huko utajaza maelezo kama namba ya meza.'
            : "\n\nI've added this to your cart. When you're ready, open the Cart section to complete your order — you'll fill in details like your table number there.";
      } else {
        reply +=
          lang === 'sw'
            ? '\n\nSamahani, sikuweza kuviweka kwenye cart kwa sasa. Tafadhali jaribu tena.'
            : '\n\nSorry, I could not add that to the cart right now. Please try again.';
      }
    }

    // 3. Remember this exchange (conversation memory the LLM learns from).
    this.conversations.addTurn(state, { role: 'user', content: message });
    this.conversations.addTurn(state, { role: 'assistant', content: reply });
    this.conversations.save(state);

    return { ...staged.response, reply, suggestions, engine, cart };
  }

  /**
   * Validate the LLM's cart block against the REAL menu. Items that don't
   * resolve to a real, available menu item are dropped — never cart inventions.
   */
  private buildCartFromMarker(
    json: string,
    menu: MenuItem[],
  ): ChatResponse['cart'] {
    let parsed: { items?: { name?: unknown; quantity?: unknown }[] };
    try {
      parsed = JSON.parse(json);
    } catch {
      return null;
    }
    if (!Array.isArray(parsed.items) || parsed.items.length === 0) return null;

    const byName = new Map(menu.map((m) => [normalize(m.name), m]));
    const lines: NonNullable<ChatResponse['cart']>['items'] = [];

    for (const raw of parsed.items.slice(0, 15)) {
      const name = typeof raw.name === 'string' ? raw.name : '';
      const qty = Math.max(1, Math.min(20, Math.round(Number(raw.quantity)) || 1));
      const item = byName.get(normalize(name)) ?? findItemByName(menu, name, 0.8);
      if (item && item.is_available && !lines.some((l) => l.id === item.id)) {
        lines.push({
          id: item.id,
          name: item.name,
          quantity: qty,
          price: item.price,
          subtotal: item.price !== null ? item.price * qty : null,
        });
      }
    }
    if (lines.length === 0) return null;

    const total = lines.reduce((s, l) => s + (l.subtotal ?? 0), 0);
    return { items: lines, total };
  }

  /** Fresh intent → filter → rule reply, and record the turn for context. */
  private handleNewIntent(
    message: string,
    items: MenuItem[],
    menuEmpty: boolean,
    state: ConversationState,
  ): StagedResult {
    let intent = detectIntent(message);

    // Menu-aware override: a real waiter knows the menu. If the message didn't
    // map to a strong intent but clearly names a real dish, describe that dish
    // instead of saying "I'm not sure" (e.g. "habari, pilau ni chakula gani?").
    if (
      !menuEmpty &&
      intent.intent !== 'explain_food' &&
      (intent.intent === 'unknown' ||
        intent.intent === 'greeting' ||
        intent.confidence < 0.5)
    ) {
      const dish = findItemByName(items, message, 0.66);
      if (dish) {
        intent = {
          intent: 'explain_food',
          confidence: 0.8,
          matchedKeywords: ['(dish name detected)'],
          entity: dish.name,
        };
      }
    }

    const filtered = filterMenu(items, intent, message);
    const built = buildResponse(intent, filtered, menuEmpty, detectLanguage(message));

    // Remember this turn so "more" / "the second one" / "it" work next time.
    if (intent.intent === 'explain_food') {
      // A single-dish description: remember the dish, keep any prior list intact.
      state.lastItem = filtered.items[0] ?? state.lastItem;
    } else if (intent.intent !== 'unknown' && intent.intent !== 'greeting') {
      // A list-style turn becomes the new reference list.
      state.lastIntent = intent.intent;
      state.lastResults = filtered.items;
      state.shownCount = Math.min(filtered.items.length, MAX_LISTED);
      state.lastItem = null;
    }
    // 'unknown'/'greeting' leave the existing context untouched.

    return {
      response: {
        sessionId: state.sessionId,
        intent: intent.intent,
        confidence: intent.confidence,
        results: filtered.items.map(toResultItem),
        reply: built.reply,
        suggestions: built.suggestions,
      },
      intent,
      shortlist: filtered.items,
    };
  }

  /** Resolve a contextual follow-up against the remembered previous turn. */
  private handleFollowup(
    followup: ReturnType<typeof resolveFollowup>,
    state: ConversationState,
    lang: 'en' | 'sw' = 'en',
  ): StagedResult {
    if (followup?.kind === 'more') {
      const start = state.shownCount;
      const batch = state.lastResults.slice(start, start + MAX_LISTED);
      state.shownCount = start + batch.length;
      const remaining = state.lastResults.length - state.shownCount;

      const built = buildMoreReply(batch, start, remaining);
      const intent: IntentResult = {
        intent: state.lastIntent ?? 'menu_overview',
        confidence: 0.9,
        matchedKeywords: ['(follow-up: more)'],
        entity: null,
      };
      return {
        response: {
          sessionId: state.sessionId,
          intent: intent.intent,
          confidence: intent.confidence,
          results: batch.map(toResultItem),
          reply: built.reply,
          suggestions: built.suggestions,
        },
        intent,
        shortlist: batch,
      };
    }

    // kind === 'explain' → describe the referenced item.
    //   index >= 0 → that position in the remembered list (e.g. "the 2nd one")
    //   index === -1 → the most recently referenced item (e.g. "it / hiyo")
    const index = (followup as { index: number }).index;
    const item = index === -1 ? state.lastItem : state.lastResults[index];

    const intent: IntentResult = {
      intent: 'explain_food',
      confidence: 0.95,
      matchedKeywords: ['(follow-up reference)'],
      entity: item?.name ?? null,
    };
    const built = buildResponse(
      intent,
      { items: item ? [item] : [], notFound: !item },
      false,
      lang,
    );

    // Remember the referenced dish, but keep the list intact so a later
    // "show me more" still paginates the original list.
    if (item) state.lastItem = item;

    return {
      response: {
        sessionId: state.sessionId,
        intent: intent.intent,
        confidence: intent.confidence,
        results: item ? [toResultItem(item)] : [],
        reply: built.reply,
        suggestions: built.suggestions,
      },
      intent,
      shortlist: item ? [item] : [],
    };
  }
}

/** Production instance: rule engine + Groq LLM brain (with auto-fallback). */
export const aiService = new AiService(
  defaultMenuService,
  defaultConversationService,
  defaultLlmService,
);
