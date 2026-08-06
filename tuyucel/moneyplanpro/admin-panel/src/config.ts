// Runtime configuration fetched from backend
let runtimeConfig: {
    supabase_url: string;
    supabase_anon_key: string;
    app_name: string;
    app_version: string;
} | null = null;

// API Base URL - in production, this will be same domain
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || globalThis.location.origin;

/**
 * Fetch runtime configuration from backend
 * This is called once on app startup
 */
export async function fetchRuntimeConfig() {
    if (runtimeConfig) {
        return runtimeConfig; // Already fetched
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/config/client`);
        if (!response.ok) {
            throw new Error(`Failed to fetch config: ${response.statusText}`);
        }
        runtimeConfig = await response.json();
        console.log('✅ Runtime config loaded successfully');
        return runtimeConfig;
    } catch (error) {
        console.error('❌ Failed to load runtime config:', error);
        throw error;
    }
}

/**
 * Get Supabase URL (runtime config)
 */
export function getSupabaseUrl(): string {
    if (!runtimeConfig) {
        throw new Error('Config not loaded. Call fetchRuntimeConfig() first.');
    }
    return runtimeConfig.supabase_url;
}

/**
 * Get Supabase Anon Key (runtime config)
 */
export function getSupabaseAnonKey(): string {
    if (!runtimeConfig) {
        throw new Error('Config not loaded. Call fetchRuntimeConfig() first.');
    }
    return runtimeConfig.supabase_anon_key;
}

/**
 * Get app info
 */
export function getAppInfo() {
    return {
        name: runtimeConfig?.app_name || 'MoneyPlan Pro Admin Panel',
        version: runtimeConfig?.app_version || '1.0.0',
    };
}
