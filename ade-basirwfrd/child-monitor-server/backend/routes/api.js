const express = require('express');
const router = express.Router();
const {
    upsertDevice, getDeviceById, getAllDevices, deleteDevice,
    updateHeartbeat, insertLog, getLogsByDevice,
    insertErrorLog, getErrorLogsByDevice,
} = require('../models/db');
const { isJudiSite, checkUrlBlock, getBlocklist, addToBlocklist } = require('../utils/judiFilter');
const { sendLogToEmail, sendServiceDisabledAlert } = require('../services/emailNotifier');
const {
    sendFCM, isInitialized, sendQuizStart, sendQuizStop, sendRestartCommand,
    sendPolicyApply, sendLockdownOn, sendLockdownOff, sendStatusPing,
} = require('../services/fcm');
const { clearOnDeviceOnline } = require('../services/staleOfflineCooldown');
const { shouldSendBlockAction } = require('../services/blockActionCooldown');

/** Online jika heartbeat dalam N menit (default 10). */
const ONLINE_WINDOW_MS = (parseInt(process.env.ONLINE_WINDOW_MINUTES, 10) || 10) * 60 * 1000;

// ============================================================
// POST /api/register - Registrasi device baru
// ============================================================
router.post('/register', async (req, res) => {
    try {
        const { deviceId, waNumber, fcmToken } = req.body;

        if (!deviceId || !waNumber) {
            return res.status(400).json({ error: 'deviceId dan waNumber wajib diisi' });
        }

        await upsertDevice({ deviceId, waNumber, fcmToken: fcmToken || null });

        console.log(`[API] Device registered: ${deviceId}, WA: ${waNumber}`);
        res.status(200).json({ message: 'Device registered successfully', deviceId });
    } catch (err) {
        console.error('[API] Register error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// POST /api/log - Terima log aktivitas dari device
// ============================================================
router.post('/log', async (req, res) => {
    try {
        const { deviceId, packageName, appName, url, timestamp } = req.body;

        if (!deviceId) {
            return res.status(400).json({ error: 'deviceId wajib diisi' });
        }

        // Periksa apakah URL judi atau blokir manual
        console.log(`[API] 📥 LOG from ${deviceId}: app=${appName} url=${url || '(none)'}`);
        const { isBlocked: detectedJudi, type: blockType } = url
            ? await checkUrlBlock(url)
            : { isBlocked: false, type: 'none' };

        // WAJIB: Cek eksistensi device SEBELUM insert log untuk Self-Healing
        const device = await getDeviceById(deviceId);
        if (!device) {
            console.warn(`[API] ⚠️ UNKNOWN DEVICE ATTEMPT: ${deviceId}. Log: ${appName} - ${url}. Signaling 401 for self-healing.`);
            return res.status(401).json({
                error: 'DEVICE_NOT_REGISTERED',
                message: 'Please register first',
                hint: 'Triggering Android self-healing...'
            });
        }

        // Simpan log ke database (Hanya jika device valid)
        await insertLog({
            deviceId,
            packageName: packageName || '',
            appName: appName || '',
            url: url || '',
            timestamp: timestamp || Date.now(),
            isJudi: detectedJudi,
        });

        const logData = { appName, packageName, url, timestamp, deviceId };

        if (detectedJudi) {
            console.log(`[API] 🚨 BLOCK TRIGGERED (${blockType}) from ${deviceId}: ${url}`);
            // Cooldown: accessibility sering kirim URL yang sama berkali-kali → spam lock/email
            if (shouldSendBlockAction(deviceId, url)) {
                const emailSuccess = await sendLogToEmail(device.wa_number, logData, blockType);
                if (!emailSuccess) {
                    console.error(`[API] ❌ Email Alert FAILED for ${deviceId} (${blockType}).`);
                }
                await sendFCM(deviceId, 'block', { url });
            } else {
                console.log(`[API] Block action cooldown aktif untuk ${deviceId} / ${url}`);
            }
        } else if (url) {
            console.log(`[API] ℹ️ Web Activity (Allowed) from ${deviceId}: ${url}`);
            await sendLogToEmail(device.wa_number, logData, 'none');
        }

        res.status(200).json({ message: 'Log received', isJudi: detectedJudi });
    } catch (err) {
        console.error('[API] Log error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// GET /api/config — URL kanonik & rekomendasi interval (sinkron dengan app / BuildConfig)
// ============================================================
router.get('/config', (req, res) => {
    const publicBaseUrl = (process.env.PUBLIC_BASE_URL || '').replace(/\/+$/, '');
    res.json({
        publicBaseUrl,
        heartbeatRecommendedSec: 90,
        onlineWindowMinutes: Math.round(ONLINE_WINDOW_MS / 60000),
        version: '1.3.0',
    });
});

// ============================================================
// GET /api/blocklist
// ============================================================
router.get('/blocklist', async (req, res) => {
    try {
        const blocklist = await getBlocklist();
        res.json(blocklist);
    } catch (err) {
        console.error('[API] Blocklist error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// POST /api/blocklist
// ============================================================
router.post('/blocklist', async (req, res) => {
    try {
        let { domain } = req.body;
        if (!domain) {
            return res.status(400).json({ error: 'domain atau url wajib diisi' });
        }

        // Jika user memasukkan full URL, ekstraksi hostnam-nya saja
        if (domain.includes('://')) {
            try {
                const urlObj = new URL(domain.startsWith('http') ? domain : `https://${domain}`);
                domain = urlObj.hostname;
            } catch (e) {
                // Biarkan apa adanya jika gagal parse
            }
        }
        domain = domain.toLowerCase().replace('www.', '');

        await addToBlocklist(domain);
        console.log(`[API] Domain added to blocklist: ${domain}`);
        res.status(200).json({ message: 'Domain added to blocklist', domain });
    } catch (err) {
        console.error('[API] Add blocklist error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// DELETE /api/blocklist/:domain
// ============================================================
router.delete('/blocklist/:domain', async (req, res) => {
    try {
        const { domain } = req.params;
        const { removeFromBlocklist } = require('../utils/judiFilter');
        await removeFromBlocklist(domain);
        console.log(`[API] Domain removed from blocklist: ${domain}`);
        res.status(200).json({ message: 'Domain removed from blocklist', domain });
    } catch (err) {
        console.error('[API] Remove blocklist error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// POST /api/heartbeat
// ============================================================
router.post('/heartbeat', async (req, res) => {
    try {
        const {
            deviceId,
            isDeviceOwner,
            adminActive,
            serviceRunning,
            appVersion,
        } = req.body;

        if (!deviceId) {
            return res.status(400).json({ error: 'deviceId wajib diisi' });
        }

        const device = await getDeviceById(deviceId);
        if (!device) {
            return res.status(401).json({ error: 'DEVICE_NOT_REGISTERED' });
        }

        await updateHeartbeat(deviceId, {
            isDeviceOwner,
            adminActive,
            serviceRunning,
            appVersion,
        });
        clearOnDeviceOnline(deviceId);
        console.log(`[API] Heartbeat from ${deviceId} do=${isDeviceOwner} admin=${adminActive}`);
        res.status(200).json({ message: 'Heartbeat received' });
    } catch (err) {
        console.error('[API] Heartbeat error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// POST /api/alert/service-disabled
// ============================================================
router.post('/alert/service-disabled', async (req, res) => {
    try {
        const { deviceId, serviceName } = req.body;

        if (!deviceId || !serviceName) {
            return res.status(400).json({ error: 'deviceId dan serviceName wajib diisi' });
        }

        const device = await getDeviceById(deviceId);
        if (device) {
            await sendServiceDisabledAlert(device.wa_number, deviceId, serviceName);
            console.log(`[API] ⚠️ Service disabled email alert: ${deviceId} - ${serviceName}`);
        }

        res.status(200).json({ message: 'Alert sent' });
    } catch (err) {
        console.error('[API] Service disabled alert error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// POST /api/alert/vpn-detected
// ============================================================
router.post('/alert/vpn-detected', async (req, res) => {
    try {
        const { deviceId } = req.body;

        const device = await getDeviceById(deviceId);
        if (device) {
            await sendLogToEmail(device.wa_number, {
                appName: '⚠️ VPN AKTIF - Anak menggunakan VPN. Monitoring jaringan mungkin terbatas.',
                packageName: 'system.vpn',
                url: '',
                timestamp: Date.now(),
                deviceId,
            }, 'vpn');
        }

        res.status(200).json({ message: 'VPN alert sent' });
    } catch (err) {
        console.error('[API] VPN alert error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// GET /api/devices
// ============================================================
router.get('/devices', async (req, res) => {
    try {
        const devices = await getAllDevices();
        const now = Date.now();
        const enriched = (devices || []).map((d) => ({
            ...d,
            online: !!(d.last_heartbeat && (now - d.last_heartbeat) < ONLINE_WINDOW_MS),
            online_window_ms: ONLINE_WINDOW_MS,
        }));
        res.json({ devices: enriched, onlineWindowMs: ONLINE_WINDOW_MS });
    } catch (err) {
        const cause = err && err.cause ? String(err.cause.message || err.cause) : undefined;
        console.error('[API] Devices error:', err.message, cause || '');
        res.status(500).json({
            error: err.message,
            cause,
            hint: 'Cek Space Secrets: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY (service_role, bukan anon). Restart Space setelah ubah.',
        });
    }
});

/** Diagnostik DB tanpa membocorkan secret */
router.get('/db-check', async (req, res) => {
    const url = process.env.SUPABASE_URL || '';
    let host = null;
    try { host = url ? new URL(url).host : null; } catch { host = '(invalid SUPABASE_URL)'; }
    const keyLen = (process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY || '').length;
    try {
        const devices = await getAllDevices();
        res.json({
            ok: true,
            supabaseHost: host,
            serviceRoleKeyLength: keyLen,
            deviceCount: (devices || []).length,
        });
    } catch (err) {
        res.status(500).json({
            ok: false,
            supabaseHost: host,
            serviceRoleKeyLength: keyLen,
            error: err.message,
            cause: err.cause ? String(err.cause.message || err.cause) : undefined,
        });
    }
});

// DELETE /api/devices/:deviceId — rapikan duplikat
router.delete('/devices/:deviceId', async (req, res) => {
    try {
        const { deviceId } = req.params;
        if (!deviceId) return res.status(400).json({ error: 'deviceId wajib' });
        await deleteDevice(deviceId);
        res.json({ success: true, message: `Deleted ${deviceId}` });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// POST /api/policy/apply — Device Owner: re-apply uninstall block dll.
router.post('/policy/apply', async (req, res) => {
    try {
        const { deviceId } = req.body;
        if (!deviceId) return res.status(400).json({ error: 'deviceId wajib diisi' });
        const success = await sendPolicyApply(deviceId);
        res.json({ success, message: success ? 'policy_apply sent' : 'Failed to send' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

router.post('/lockdown/on', async (req, res) => {
    try {
        const { deviceId } = req.body;
        if (!deviceId) return res.status(400).json({ error: 'deviceId wajib diisi' });
        const success = await sendLockdownOn(deviceId);
        res.json({ success, message: success ? 'lockdown_on sent' : 'Failed' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

router.post('/lockdown/off', async (req, res) => {
    try {
        const { deviceId } = req.body;
        if (!deviceId) return res.status(400).json({ error: 'deviceId wajib diisi' });
        const success = await sendLockdownOff(deviceId);
        res.json({ success, message: success ? 'lockdown_off sent' : 'Failed' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

router.post('/status-ping', async (req, res) => {
    try {
        const { deviceId } = req.body;
        if (!deviceId) return res.status(400).json({ error: 'deviceId wajib diisi' });
        const success = await sendStatusPing(deviceId);
        res.json({ success, message: success ? 'status sent' : 'Failed' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// POST /api/quiz/start - Mulai mode kuis di device
// ============================================================
router.post('/quiz/start', async (req, res) => {
    try {
        const { deviceId } = req.body;
        if (!deviceId) return res.status(400).json({ error: 'deviceId wajib diisi' });

        const success = await sendQuizStart(deviceId);
        res.json({ success, message: success ? 'Quiz command sent' : 'Failed to send quiz command' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// POST /api/quiz/stop - Hentikan mode kuis di device
// ============================================================
router.post('/quiz/stop', async (req, res) => {
    try {
        const { deviceId } = req.body;
        if (!deviceId) return res.status(400).json({ error: 'deviceId wajib diisi' });

        const success = await sendQuizStop(deviceId);
        res.json({ success, message: success ? 'Stop command sent' : 'Failed to send stop command' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// POST /api/restart - Restart monitoring service on device
// ============================================================
router.post('/restart', async (req, res) => {
    try {
        const { deviceId } = req.body;
        if (!deviceId) return res.status(400).json({ error: 'deviceId wajib diisi' });

        const device = await getDeviceById(deviceId);
        if (!device || !device.fcm_token) {
            return res.status(404).json({ error: 'Device not found or no FCM token' });
        }

        const success = await sendRestartCommand(deviceId);
        console.log(`[API] Restart command sent to ${deviceId}: ${success}`);
        res.json({ success, message: success ? 'Restart command sent' : 'Failed to send restart command' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// GET /api/logs/:deviceId
// ============================================================
router.get('/logs/:deviceId', async (req, res) => {
    try {
        const { deviceId } = req.params;
        const limit = parseInt(req.query.limit) || 50;
        const logs = await getLogsByDevice(deviceId, Math.min(limit, 200));
        res.json({ logs });
    } catch (err) {
        console.error('[API] Get logs error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// GET /api/status - Cek status backend & FCM
// ============================================================
router.get('/status', (req, res) => {
    res.json({
        status: 'online',
        fcm_initialized: isInitialized(),
        email_alerts: 'active',
        timestamp: Date.now()
    });
});

// ============================================================
// POST /api/error-log - Terima error log dari device
// ============================================================
router.post('/error-log', async (req, res) => {
    try {
        const { deviceId, errorType, errorMessage, stackTrace, component } = req.body;

        if (!deviceId) {
            return res.status(400).json({ error: 'deviceId wajib diisi' });
        }

        await insertErrorLog({ deviceId, errorType, errorMessage, stackTrace, component });
        console.log(`[API] ❌ Error from ${deviceId}: [${component}] ${errorType} - ${errorMessage}`);
        res.status(200).json({ message: 'Error log received' });
    } catch (err) {
        console.error('[API] Error log error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// ============================================================
// GET /api/error-logs/:deviceId? - Ambil error logs
// ============================================================
router.get('/error-logs/:deviceId?', async (req, res) => {
    try {
        const deviceId = req.params.deviceId || null;
        const limit = parseInt(req.query.limit) || 50;
        const errors = await getErrorLogsByDevice(deviceId, Math.min(limit, 200));
        res.json({ errors });
    } catch (err) {
        console.error('[API] Get error logs error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

module.exports = router;
