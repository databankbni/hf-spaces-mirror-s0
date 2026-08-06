const path = require('path');
const { getDeviceById } = require('../models/db');

let admin = null;
let initialized = false;

/**
 * Inisialisasi Firebase Admin SDK
 */
function initFirebase() {
    if (initialized) return;

    try {
        admin = require('firebase-admin');
        let serviceAccount = null;

        // Try environment variable first (for cloud deployment)
        if (process.env.FIREBASE_SERVICE_ACCOUNT) {
            try {
                serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
                console.log('[FCM] Using credentials from FIREBASE_SERVICE_ACCOUNT env var');
            } catch (e) {
                // Try base64
                serviceAccount = JSON.parse(Buffer.from(process.env.FIREBASE_SERVICE_ACCOUNT, 'base64').toString());
                console.log('[FCM] Using base64 credentials from FIREBASE_SERVICE_ACCOUNT env var');
            }
        } else {
            // Fallback to local file
            const serviceAccountPath = path.join(__dirname, '..', 'serviceAccountKey.json');
            try {
                serviceAccount = require(serviceAccountPath);
            } catch (e) {
                console.warn('[FCM] serviceAccountKey.json not found, skipping local init');
            }
        }

        if (serviceAccount) {
            admin.initializeApp({
                credential: admin.credential.cert(serviceAccount),
            });
            initialized = true;
            console.log('[FCM] Firebase Admin SDK initialized successfully');
        }
    } catch (err) {
        console.warn('[FCM] Firebase Admin SDK not initialized:', err.message);
    }
}

/** FCM registration tokens are long (~140+ chars). device_id dari setup biasanya pendek — jangan kirim token sebagai argumen pertama. */
const LIKELY_FCM_TOKEN_MIN_LEN = 120;

/**
 * Kirim perintah FCM ke device.
 * @param {string} deviceId - Primary key di tabel devices (bukan fcm_token).
 * @param {string} command - Perintah untuk payload data.command
 */
async function sendFCM(deviceId, command, extraData = {}) {
    if (!initialized || !admin) {
        console.warn('[FCM] Cannot send FCM - not initialized');
        return false;
    }

    if (typeof deviceId !== 'string' || !deviceId.trim()) {
        console.error('[FCM] sendFCM: deviceId must be a non-empty string');
        return false;
    }
    if (deviceId.length >= LIKELY_FCM_TOKEN_MIN_LEN) {
        console.error(
            '[FCM] sendFCM: argumen pertama terlihat seperti FCM token, bukan device_id. ' +
                'Gunakan device_id dari database; token di-resolve di dalam fungsi ini.'
        );
        return false;
    }

    try {
        const device = await getDeviceById(deviceId);
        if (!device || !device.fcm_token) {
            console.warn(`[FCM] Device ${deviceId} not found or no FCM token`);
            return false;
        }

        const message = {
            data: {
                command: command,
                ...Object.fromEntries(
                    Object.entries(extraData).map(([k, v]) => [k, String(v)])
                ),
            },
            token: device.fcm_token,
        };

        const response = await admin.messaging().send(message);
        console.log(`[FCM] Message sent to ${deviceId}: ${response}`);
        return true;
    } catch (error) {
        console.error(`[FCM] Error sending to ${deviceId}:`, error.message);

        if (
            error.code === 'messaging/invalid-registration-token' ||
            error.code === 'messaging/registration-token-not-registered'
        ) {
            console.warn(`[FCM] Invalid token for device ${deviceId}`);
        }

        return false;
    }
}

async function sendLockCommand(deviceId) {
    return sendFCM(deviceId, 'lock');
}

async function sendUpdateBlocklist(deviceId) {
    return sendFCM(deviceId, 'update_blocklist');
}

async function sendQuizStart(deviceId) {
    return sendFCM(deviceId, 'start_quiz');
}

async function sendQuizStop(deviceId) {
    return sendFCM(deviceId, 'stop_quiz');
}

async function sendRestartCommand(deviceId) {
    return sendFCM(deviceId, 'restart');
}

async function sendPolicyApply(deviceId) {
    return sendFCM(deviceId, 'policy_apply');
}

async function sendLockdownOn(deviceId) {
    return sendFCM(deviceId, 'lockdown_on');
}

async function sendLockdownOff(deviceId) {
    return sendFCM(deviceId, 'lockdown_off');
}

async function sendStatusPing(deviceId) {
    return sendFCM(deviceId, 'status');
}

initFirebase();

module.exports = {
    sendFCM,
    sendLockCommand,
    sendUpdateBlocklist,
    sendQuizStart,
    sendQuizStop,
    sendRestartCommand,
    sendPolicyApply,
    sendLockdownOn,
    sendLockdownOff,
    sendStatusPing,
    initFirebase,
    isInitialized: () => initialized,
};
