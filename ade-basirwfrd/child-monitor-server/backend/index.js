require('./config/env');

const express = require('express');
const path = require('path');
const cron = require('node-cron');
const { getStaleDevices } = require('./models/db');
const apiRoutes = require('./routes/api');
const { sendEmailAlert } = require('./services/emailNotifier');
const { shouldSendStaleEmail, recordStaleEmailSent } = require('./services/staleOfflineCooldown');

const app = express();
/** HF Spaces = 7860; Fly/Railway set PORT via platform env. */
const PORT = Number(process.env.PORT) || 7860;

// ============================================================
// Middleware
// ============================================================
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// CORS
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    if (req.method === 'OPTIONS') {
        return res.sendStatus(200);
    }
    next();
});

// Request logging
app.use((req, res, next) => {
    const timestamp = new Date().toLocaleString('id-ID');
    console.log(`[${timestamp}] ${req.method} ${req.url}`);
    next();
});

// ============================================================
// Static files (Parent Dashboard)
// ============================================================
const publicDir = path.join(__dirname, 'public');
app.use(express.static(publicDir));

// Alias singkat (mudah diketik di HP) → halaman buka setup ChildMonitor
const openSetupPage = path.join(publicDir, 'open-child-setup.html');
app.get(['/setup-child', '/open-setup-app'], (req, res) => {
    res.sendFile(openSetupPage);
});

// ============================================================
// Routes
// ============================================================
app.use('/api', apiRoutes);

// Lock endpoint for dashboard
const { sendLockCommand } = require('./services/fcm');
app.post('/api/lock', async (req, res) => {
    try {
        const { deviceId } = req.body;
        if (!deviceId) return res.status(400).json({ error: 'deviceId required' });
        const success = await sendLockCommand(deviceId);
        res.json({ success, message: success ? 'Lock command sent' : 'Failed to send lock command' });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Health check
app.get('/api/health', (req, res) => {
    res.json({
        name: 'Child Monitor Backend',
        version: '1.3.0',
        status: 'running',
        email_alerts: 'active',
        hosting_hint: 'Deploy always-on (Fly/Railway) — see backend/DEPLOY_ALWAYS_ON.md',
        uptime: process.uptime(),
        timestamp: new Date().toISOString(),
    });
});

// ============================================================
// Cron — stale heartbeat (default 15 menit; jalankan tiap 5 menit)
// ============================================================
const STALE_OFFLINE_MS = (parseInt(process.env.STALE_OFFLINE_MINUTES, 10) || 15) * 60 * 1000;

cron.schedule('*/5 * * * *', async () => {
    // Jangan spam email di cold start (server baru hidup < 2 menit)
    if (process.uptime() < 120) {
        console.log('[CRON] Skip stale check (startup grace)');
        return;
    }
    console.log('[CRON] Checking device heartbeats...');
    const threshold = Date.now() - STALE_OFFLINE_MS;
    const mins = Math.round(STALE_OFFLINE_MS / 60000);

    try {
        const staleDevices = await getStaleDevices(threshold);
        for (const device of staleDevices) {
            const id = device.device_id;
            if (!shouldSendStaleEmail(id)) {
                console.log(`[CRON] Stale device ${id}: email cooldown aktif, lewati.`);
                continue;
            }
            console.log(`[CRON] Stale device detected: ${id}`);
            const doFlag = device.is_device_owner ? ' (Device Owner)' : '';
            await sendEmailAlert(
                `Perangkat Offline: ${id}`,
                `<h2>Perangkat Offline</h2><p>Perangkat <strong>${id}</strong>${doFlag} tidak mengirim heartbeat selama lebih dari ${mins} menit. Segera periksa HP / jaringan / layanan ChildMonitor.</p>`
            );
            recordStaleEmailSent(id);
        }
    } catch (err) {
        console.error('[CRON] Heartbeat check error:', err.message);
    }
});

// ============================================================
// Start server — bind 0.0.0.0 agar health-check HF Spaces lulus
// ============================================================
app.listen(PORT, '0.0.0.0', () => {
    console.log('='.repeat(50));
    console.log(`  Child Monitor Backend Server`);
    console.log(`  Listening: 0.0.0.0:${PORT}`);
    console.log(`  Dashboard: http://localhost:${PORT}`);
    console.log(`  API:       http://localhost:${PORT}/api`);
    console.log(`  Time: ${new Date().toLocaleString('id-ID')}`);
    console.log('='.repeat(50));
    console.log('');

    console.log('[Server] Email alerts via Brevo are active.');
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\n[Server] Shutting down gracefully...');
    process.exit(0);
});

process.on('SIGTERM', () => {
    console.log('\n[Server] Shutting down...');
    process.exit(0);
});

module.exports = app;
