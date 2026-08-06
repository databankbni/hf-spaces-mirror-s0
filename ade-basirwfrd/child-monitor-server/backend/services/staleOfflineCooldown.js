/**
 * Mencegah spam email "perangkat offline" untuk device yang sama (cron per jam).
 * State disimpan di file agar tetap konsisten setelah restart proses (single-instance server).
 */
const fs = require('fs');
const path = require('path');

/** Jangan spam email offline untuk device yang sama (default 2 jam). */
const COOLDOWN_MS = (parseInt(process.env.STALE_EMAIL_COOLDOWN_MINUTES, 10) || 120) * 60 * 1000;
const DATA_PATH = path.join(__dirname, '..', 'data', 'stale-offline-alerts.json');

function load() {
    try {
        if (!fs.existsSync(DATA_PATH)) return {};
        const raw = fs.readFileSync(DATA_PATH, 'utf8');
        const parsed = JSON.parse(raw);
        return typeof parsed === 'object' && parsed !== null ? parsed : {};
    } catch {
        return {};
    }
}

function save(map) {
    const dir = path.dirname(DATA_PATH);
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(DATA_PATH, JSON.stringify(map), 'utf8');
}

/**
 * @returns {boolean} true jika boleh kirim email offline untuk device ini
 */
function shouldSendStaleEmail(deviceId) {
    if (!deviceId) return false;
    const map = load();
    const last = map[deviceId];
    if (last == null) return true;
    return Date.now() - Number(last) >= COOLDOWN_MS;
}

function recordStaleEmailSent(deviceId) {
    if (!deviceId) return;
    const map = load();
    map[deviceId] = Date.now();
    save(map);
}

/** Panggil saat heartbeat OK — reset cooldown agar episode offline berikutnya dapat alert baru */
function clearOnDeviceOnline(deviceId) {
    if (!deviceId) return;
    const map = load();
    if (map[deviceId] == null) return;
    delete map[deviceId];
    save(map);
}

module.exports = {
    shouldSendStaleEmail,
    recordStaleEmailSent,
    clearOnDeviceOnline,
    COOLDOWN_MS,
};
