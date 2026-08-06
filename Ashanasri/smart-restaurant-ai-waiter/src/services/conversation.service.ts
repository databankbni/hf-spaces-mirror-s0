import { randomUUID } from 'crypto';
import { config } from '../config';
import { Intent, MenuItem } from '../types';

/**
 * Conversation Service
 * --------------------
 * Lightweight, in-memory multi-turn memory keyed by `sessionId`. It lets the
 * waiter remember the previous turn so a customer can say things like
 * "show me more" or "tell me about the second one".
 *
 * Design notes:
 *  - State is keyed by an opaque sessionId that the CLIENT carries between
 *    messages (returned in every response). The service itself stays close to
 *    stateless: no DB, just a capped, self-expiring Map.
 *  - To scale across many instances, either use sticky sessions at the load
 *    balancer, or swap this class for a Redis-backed implementation — the rest
 *    of the code only depends on this small interface.
 */

export interface ConversationState {
  sessionId: string;
  /** The intent of the previous list-style turn (for "show me more"). */
  lastIntent: Intent | null;
  /** Full ordered list of items from the previous LIST turn (reference list). */
  lastResults: MenuItem[];
  /** How many of `lastResults` have already been shown (pagination cursor). */
  shownCount: number;
  /** The single most-recently referenced item (for "tell me more about it"). */
  lastItem: MenuItem | null;
  /**
   * Rolling chat transcript (user + waiter turns) fed to the LLM as
   * conversation memory. Capped to the last N turns (config.llmMaxHistory).
   */
  history: ChatTurn[];
  updatedAt: number;
}

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

export class ConversationService {
  private readonly store = new Map<string, ConversationState>();
  private readonly ttl = config.sessionTtlMs;
  private readonly max = config.sessionMax;

  /** Remove expired sessions. Cheap; called on each access. */
  private sweep(): void {
    if (this.ttl <= 0) return;
    const now = Date.now();
    for (const [id, s] of this.store) {
      if (now - s.updatedAt > this.ttl) this.store.delete(id);
    }
  }

  /** Keep memory bounded by evicting the oldest sessions past the cap. */
  private capSize(): void {
    if (this.store.size <= this.max) return;
    const sorted = [...this.store.entries()].sort(
      (a, b) => a[1].updatedAt - b[1].updatedAt,
    );
    const toRemove = this.store.size - this.max;
    for (let i = 0; i < toRemove; i++) this.store.delete(sorted[i][0]);
  }

  private fresh(sessionId: string): ConversationState {
    return {
      sessionId,
      lastIntent: null,
      lastResults: [],
      shownCount: 0,
      lastItem: null,
      history: [],
      updatedAt: Date.now(),
    };
  }

  /**
   * Return the existing state for a sessionId, or a fresh state. If the client
   * supplied an id we honor it (so they can choose their own); otherwise we
   * mint a new UUID. The returned object is NOT stored until `save` is called.
   */
  public getOrCreate(sessionId?: string): ConversationState {
    this.sweep();
    if (sessionId) {
      const existing = this.store.get(sessionId);
      if (existing) return existing;
      return this.fresh(sessionId);
    }
    return this.fresh(randomUUID());
  }

  /** Persist (or refresh) a session's state. */
  public save(state: ConversationState): void {
    state.updatedAt = Date.now();
    this.store.set(state.sessionId, state);
    this.capSize();
  }

  /** Append a chat turn, keeping the transcript capped. */
  public addTurn(state: ConversationState, turn: ChatTurn): void {
    state.history.push(turn);
    const cap = Math.max(2, config.llmMaxHistory);
    if (state.history.length > cap) {
      state.history.splice(0, state.history.length - cap);
    }
  }

  /** Testing / ops helper. */
  public clear(): void {
    this.store.clear();
  }

  public size(): number {
    return this.store.size;
  }
}

export const conversationService = new ConversationService();
