const { getAllBlockedDomains, insertBlockedDomain, deleteBlockedDomain } = require('../models/db');

// Keywords yang mengindikasikan situs judi
const JUDI_KEYWORDS = [
    'judi', 'slot', 'poker', 'togel', 'casino', 'bet', 'bola',
    'gambling', 'taruhan', 'bandar', 'jackpot', 'scatter', 'gacor',
    'maxwin', 'rtp', 'pragmatic', 'pgsoft', 'livecasino', 'sportsbook',
    'roulette', 'blackjack', 'baccarat', 'sicbo', 'dragontiger',
    'slotgacor', 'judol', 'cuan',
    // Brand mirror / SEO clone (hostname mengandung nama brand)
    'sbobet', 'mansion88', 'm88', 'w88', 'fun88', 'we88', 'md88',
    'bk8', 'dafabet', 'cmd368', 'ibcbet', 'maxbet', '188bet',
    'longfu88', 'kawanslot', 'naga303', 'dewapoker', 'idnpoker',
    'joker123', 'mpo88', 'parimatch', 'paripesa', '1xbet', '1win',
    'mostbet', 'melbet', 'roobet', 'bcgame',
];

// Cache blocklist in memory, refresh periodically
let cachedDomains = [];
let lastRefresh = 0;
const CACHE_TTL = 60000; // 1 minute

async function refreshCache() {
    if (Date.now() - lastRefresh > CACHE_TTL) {
        try {
            cachedDomains = await getAllBlockedDomains();
            lastRefresh = Date.now();
        } catch (err) {
            console.warn('[JudiFilter] Failed to refresh cache:', err.message);
        }
    }
}

/**
 * Periksa apakah sebuah URL mengarah ke situs judi atau daftar blokir manual
 * @param {string} url - URL yang akan diperiksa
 * @returns {Promise<{ isBlocked: boolean, type: 'none' | 'judi' | 'manual' }>}
 */
async function checkUrlBlock(url) {
    if (!url) return { isBlocked: false, type: 'none' };

    await refreshCache();

    try {
        // Normalize URL
        let normalizedUrl = url;
        if (!normalizedUrl.startsWith('http://') && !normalizedUrl.startsWith('https://')) {
            normalizedUrl = 'https://' + normalizedUrl;
        }

        const parsedUrl = new URL(normalizedUrl);
        // Strip Bidi/zero-width marks + leading www.
        const host = parsedUrl.hostname
            .toLowerCase()
            .replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069\u200b]/g, '')
            .replace(/^www\./, '');

        // 1. Cek exact match dengan blocklist database (Blokir Manual)
        if (cachedDomains.includes(host)) return { isBlocked: true, type: 'manual' };

        // 2. Cek subdomain match (Blokir Manual)
        const parts = host.split('.');
        if (parts.length >= 2) {
            const baseDomain = parts.slice(-2).join('.');
            if (cachedDomains.includes(baseDomain)) return { isBlocked: true, type: 'manual' };

            if (parts.length >= 3) {
                const baseDomain3 = parts.slice(-3).join('.');
                if (cachedDomains.includes(baseDomain3)) return { isBlocked: true, type: 'manual' };
            }
        }

        // 3. Cek keyword di hostname (Deteksi Otomatis Judi)
        for (const keyword of JUDI_KEYWORDS) {
            if (host.includes(keyword)) return { isBlocked: true, type: 'judi' };
        }

        // 4. Cek keyword di path (Deteksi Otomatis Judi)
        const specificPathKeywords = ['slot', 'togel', 'casino', 'poker', 'sportsbook', 'livecasino'];
        const pathLower = parsedUrl.pathname.toLowerCase();
        for (const keyword of specificPathKeywords) {
            if (pathLower.includes(keyword)) return { isBlocked: true, type: 'judi' };
        }

        return { isBlocked: false, type: 'none' };
    } catch (e) {
        // Jika URL tidak valid, cek keyword di string mentah
        const urlLower = url.toLowerCase();
        const isJudi = JUDI_KEYWORDS.some(k => urlLower.includes(k));
        return { isBlocked: isJudi, type: isJudi ? 'judi' : 'none' };
    }
}

// Keep backward compatibility
async function isJudiSite(url) {
    const result = await checkUrlBlock(url);
    return result.isBlocked;
}

/**
 * Dapatkan daftar blocklist saat ini
 * @returns {Promise<{ domains: string[], keywords: string[], version: number }>}
 */
async function getBlocklist() {
    const domains = await getAllBlockedDomains();
    return {
        domains,
        keywords: JUDI_KEYWORDS,
        version: 1,
    };
}

/**
 * Tambah domain baru ke blocklist
 * @param {string} domain
 */
async function addToBlocklist(domain) {
    await insertBlockedDomain(domain.toLowerCase());
    lastRefresh = 0; // Force cache refresh
}

/**
 * Hapus domain dari blocklist
 * @param {string} domain
 */
async function removeFromBlocklist(domain) {
    await deleteBlockedDomain(domain.toLowerCase());
    lastRefresh = 0;
}

module.exports = {
    isJudiSite,
    checkUrlBlock,
    getBlocklist,
    addToBlocklist,
    removeFromBlocklist,
    JUDI_KEYWORDS,
};
