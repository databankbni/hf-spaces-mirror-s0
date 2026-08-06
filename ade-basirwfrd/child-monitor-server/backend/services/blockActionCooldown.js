/**
 * Cooldown aksi blokir (FCM lock + email) per device+url agar tidak spam kunci layar.
 */
const fs = require('fs');
const path = require('path');

const COOLDOWN_MS = (parseInt(process.env.BLOCK_ACTION_COOLDOWN_SEC, 10) || 180) * 1000;
const DATA_PATH = path.join(__dirname, '..', 'data', 'block-action-cooldown.json');

function load() {
    try {
        if (!fs.existsSync(DATA_PATH)) return {};
        const parsed = JSON.parse(fs.readFileSync(DATA_PATH, 'utf8'));
        return typeof parsed === 'object' && parsed !== null ? parsed : {};
    } catch {
        return {};
    }
}

function save(map) {
    const dir = path.dirname(DATA_PATH);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(DATA_PATH, JSON.stringify(map), 'utf8');
}

function normalizeKey(deviceId, url) {
    const u = String(url || '').toLowerCase().replace(/^https?:\/\//, '').replace(/^www\./, '').split(/[/?#]/)[0];
    return `${deviceId}::${u}`;
}

/** @returns {boolean} true jika boleh kirim FCM/email block sekarang */
function shouldSendBlockAction(deviceId, url) {
    if (!deviceId) return false;
    const key = normalizeKey(deviceId, url);
    const map = load();
    const last = map[key];
    if (last != null && Date.now() - Number(last) < COOLDOWN_MS) {
        return false;
    }
    map[key] = Date.now();
    save(map);
    return true;
}

module.exports = { shouldSendBlockAction, COOLDOWN_MS };
