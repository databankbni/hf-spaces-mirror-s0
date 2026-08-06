import axios, { AxiosInstance } from 'axios';
import { config } from '../config';
import { MenuItem, MenuResponse, MenuResponseSchema } from '../types';

/**
 * Menu Service
 * ------------
 * The ONLY place that talks to the existing Django backend. It fetches the
 * live menu, validates it with Zod, normalizes the payload, and caches it
 * briefly to keep the AI service fast and to shield the backend from bursts.
 *
 * This service builds nothing of its own — every menu item it returns came
 * from the backend. That is what lets the rest of the system promise "never
 * invent menu items".
 */

/** Raised when the backend menu cannot be retrieved. */
export class MenuFetchError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly slug: string,
  ) {
    super(message);
    this.name = 'MenuFetchError';
  }
}

interface CacheEntry {
  data: MenuResponse;
  expiresAt: number;
}

export class MenuService {
  private readonly http: AxiosInstance;
  private readonly cache = new Map<string, CacheEntry>();

  constructor(http?: AxiosInstance) {
    this.http =
      http ??
      axios.create({
        baseURL: config.backendBaseUrl,
        timeout: config.backendTimeoutMs,
        headers: { Accept: 'application/json' },
      });
  }

  /** Build the backend menu endpoint path for a slug (template from config). */
  private menuPath(slug: string): string {
    return config.backendMenuPath.replace('{slug}', encodeURIComponent(slug));
  }

  /** "bravo-coco-beach" → "Bravo Coco Beach" (fallback restaurant name). */
  private humanizeSlug(slug: string): string {
    return slug
      .split(/[-_]+/)
      .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
      .join(' ');
  }

  private getCached(slug: string): MenuResponse | null {
    const entry = this.cache.get(slug);
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) {
      this.cache.delete(slug);
      return null;
    }
    return entry.data;
  }

  private setCached(slug: string, data: MenuResponse): void {
    if (config.menuCacheTtlMs <= 0) return;
    this.cache.set(slug, { data, expiresAt: Date.now() + config.menuCacheTtlMs });
  }

  /** Clear cache (handy for tests / forced refresh). */
  public clearCache(): void {
    this.cache.clear();
  }

  /**
   * Fetch and validate the menu for a restaurant.
   *
   * Accepts both `menuItems` (documented) and `menu_items` (snake_case) keys
   * from the backend for resilience. Throws MenuFetchError on network/HTTP
   * errors so the controller can map them to clean client responses.
   */
  public async getMenu(slug: string): Promise<MenuResponse> {
    const cached = this.getCached(slug);
    if (cached) return cached;

    try {
      const res = await this.http.get(this.menuPath(slug));
      const raw = res.data ?? {};

      // Tolerate snake_case key from some backend versions.
      if (raw.menuItems === undefined && Array.isArray(raw.menu_items)) {
        raw.menuItems = raw.menu_items;
      }

      // ── Adapter for the production backend (mlo.co.tz) shape ─────────────
      // { categories: [{id, name}], items: [{..., isAvailable, imageUrl,
      //   categoryId, protein, fat, carbs}] }  →  our canonical shape.
      if (raw.menuItems === undefined && Array.isArray(raw.items)) {
        const catById = new Map<string, string>(
          (Array.isArray(raw.categories) ? raw.categories : [])
            .filter((c: unknown): c is { id: string; name: string } => !!c)
            .map((c: { id: string; name: string }) => [String(c.id), String(c.name ?? 'Other')]),
        );
        raw.menuItems = raw.items.map((it: Record<string, unknown>) => ({
          ...it,
          category:
            it.category ?? { name: catById.get(String(it.categoryId)) ?? 'Other' },
        }));
      }

      // No restaurant object in the payload → enrich from the restaurants
      // list endpoint (name, opening hours, delivery settings, phone…), with
      // a humanized slug as the final fallback.
      if (!raw.restaurant) {
        const info = await this.getRestaurantInfo(slug);
        raw.restaurant = info ?? { name: this.humanizeSlug(slug), slug };
      }

      // Tolerate different field names for images and availability.
      if (Array.isArray(raw.menuItems)) {
        for (const it of raw.menuItems) {
          if (it && typeof it === 'object') {
            if (it.image === undefined) {
              it.image = it.imageUrl ?? it.image_url ?? it.photo ?? it.picture ?? '';
            }
            if (it.is_available === undefined && it.isAvailable !== undefined) {
              it.is_available = it.isAvailable;
            }
          }
        }
      }

      const parsed = MenuResponseSchema.safeParse(raw);
      if (!parsed.success) {
        throw new MenuFetchError(
          `Backend returned an unexpected menu shape: ${parsed.error.issues
            .map((i) => i.path.join('.') + ' ' + i.message)
            .join('; ')}`,
          502,
          slug,
        );
      }

      this.setCached(slug, parsed.data);
      return parsed.data;
    } catch (err) {
      if (err instanceof MenuFetchError) throw err;

      if (axios.isAxiosError(err)) {
        const status = err.response?.status ?? 0;
        if (status === 404) {
          throw new MenuFetchError(`Restaurant "${slug}" was not found.`, 404, slug);
        }
        if (status >= 500) {
          throw new MenuFetchError('The restaurant backend is unavailable.', 502, slug);
        }
        if (err.code === 'ECONNABORTED') {
          throw new MenuFetchError('The restaurant backend timed out.', 504, slug);
        }
        throw new MenuFetchError(
          `Failed to reach the restaurant backend (${err.message}).`,
          502,
          slug,
        );
      }

      throw new MenuFetchError('Unexpected error fetching the menu.', 500, slug);
    }
  }

  /** Convenience: just the menu items array. */
  public async getMenuItems(slug: string): Promise<MenuItem[]> {
    const menu = await this.getMenu(slug);
    return menu.menuItems;
  }

  /** Restaurant profile (hours, delivery, phone…) from the list endpoint. */
  private infoCache: { data: Record<string, unknown>[]; expiresAt: number } | null = null;

  private async getRestaurantInfo(
    slug: string,
  ): Promise<Record<string, unknown> | null> {
    if (config.demoMode) return null;
    try {
      if (!this.infoCache || Date.now() > this.infoCache.expiresAt) {
        const res = await this.http.get(config.backendRestaurantsPath);
        const list = Array.isArray(res.data) ? res.data : [];
        this.infoCache = {
          data: list,
          expiresAt: Date.now() + Math.max(config.menuCacheTtlMs, 60_000),
        };
      }
      const found = this.infoCache.data.find(
        (r) => r && (r as { slug?: string }).slug === slug,
      );
      return found ?? null;
    } catch {
      // Info is a nice-to-have; the waiter works fine without it.
      return null;
    }
  }
}

/** Default shared instance used by the app. */
export const menuService = new MenuService();
