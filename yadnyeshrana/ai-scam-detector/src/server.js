require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');
const whatsappService = require('./services/whatsapp');
const scraperService = require('./services/scraper');

// Prevent Puppeteer navigation errors from crashing the server
process.on('uncaughtException', (err) => {
  console.error('🔥 Global Uncaught Exception:', err);
  if (err.message && (err.message.includes('Execution context was destroyed') || err.message.includes('navigation'))) {
    console.log('ℹ️ Safe to ignore: Puppeteer navigation exception. Keeping server alive.');
  } else {
    process.exit(1);
  }
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('🔥 Global Unhandled Rejection:', reason);
  if (reason && reason.message && (reason.message.includes('Execution context was destroyed') || reason.message.includes('navigation'))) {
    console.log('ℹ️ Safe to ignore: Puppeteer navigation rejection. Keeping server alive.');
  }
});

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// Handle JSON parsing syntax errors (prevent crashing on malformed payloads)
app.use((err, req, res, next) => {
  if (err instanceof SyntaxError && err.status === 400 && 'body' in err) {
    console.error('⚠️ JSON Parsing Error caught:', err.message);
    return res.status(400).json({
      success: false,
      error: 'BAD_REQUEST',
      message: 'Invalid JSON payload format.'
    });
  }
  next(err);
});

app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, '../public')));

// Health Check
app.get('/health', (req, res) => {
  const isReady = whatsappService.isReady();
  const hasQr = !!whatsappService.getLatestQr();

  res.json({
    status: 'UP',
    timestamp: new Date().toISOString(),
    whatsappStatus: isReady ? 'CONNECTED' : (hasQr ? 'PAIRING_REQUIRED' : 'INITIALIZING'),
    env: {
      dbMode: process.env.USE_LOCAL_DB === 'true' ? 'Local JSON' : 'Firebase Realtime DB',
      geminiConfigured: !!process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== 'your_gemini_api_key_here'
    }
  });
});



// Routes
const webhookRoutes = require('./routes/webhook');
const apiRoutes = require('./routes/api');
const paymentRoutes = require('./routes/payments');
const adminRoutes = require('./routes/admin');
const historyRoutes = require('./routes/history');

app.use('/webhook', webhookRoutes);
app.use('/api', apiRoutes);
app.use('/payments', paymentRoutes);
app.use('/admin', adminRoutes);
app.use('/history', historyRoutes);

// WhatsApp QR Code visual scanner page
app.get('/qr', (req, res) => {
  const isReady = whatsappService.isReady();
  const qr = whatsappService.getLatestQr();

  if (isReady) {
    return res.send(`
      <html>
        <head>
          <title>WhatsApp Bot Online</title>
          <style>
            body { background: #0f172a; color: #f8fafc; font-family: system-ui; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; border: 1px solid #334155; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); max-width: 400px; }
            h2 { color: #10b981; margin-top: 0; }
            p { color: #94a3b8; font-size: 0.95rem; line-height: 1.5; }
            .checkmark { font-size: 3rem; color: #10b981; margin: 1rem 0; }
          </style>
        </head>
        <body>
          <div class="card">
            <h2>Bot is Active!</h2>
            <div class="checkmark">✅</div>
            <p><strong>WhatsApp Scam Detector is online and running.</strong></p>
            <p>The login session is saved securely in the cloud. You can safely close this browser window.</p>
          </div>
        </body>
      </html>
    `);
  }

  if (!qr) {
    return res.send(`
      <html>
        <head>
          <title>WhatsApp Bot Status</title>
          <meta http-equiv="refresh" content="5">
          <style>
            body { background: #0f172a; color: #f8fafc; font-family: system-ui; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; border: 1px solid #334155; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); max-width: 400px; }
            h2 { color: #38bdf8; margin-top: 0; }
            p { color: #94a3b8; font-size: 0.95rem; line-height: 1.5; }
            .spinner { border: 4px solid rgba(56, 189, 248, 0.1); border-left-color: #38bdf8; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 1.5rem auto; }
            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
          </style>
        </head>
        <body>
          <div class="card">
            <h2>WhatsApp Bot Setup</h2>
            <div class="spinner"></div>
            <p><strong>Waiting for QR code generation...</strong></p>
            <p>If you have already scanned the QR code, the bot is running! You can close this window.</p>
            <p>Refreshing automatically...</p>
          </div>
        </body>
      </html>
    `);
  }

  const qrImageUrl = `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(qr)}`;
  res.send(`
    <html>
      <head>
        <title>Scan WhatsApp QR Code</title>
        <meta http-equiv="refresh" content="15">
        <style>
          body { background: #0f172a; color: #f8fafc; font-family: system-ui; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
          .card { background: #1e293b; padding: 2.5rem; border-radius: 1rem; border: 1px solid #334155; text-align: center; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); max-width: 450px; }
          h2 { color: #38bdf8; margin-top: 0; margin-bottom: 0.5rem; }
          p { color: #94a3b8; font-size: 0.95rem; line-height: 1.5; margin-bottom: 1.5rem; }
          .qr-container { background: white; padding: 1.5rem; border-radius: 0.5rem; display: inline-block; margin-bottom: 1.5rem; box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.06); }
          .footer { font-size: 0.8rem; color: #64748b; }
        </style>
      </head>
      <body>
        <div class="card">
          <h2>Link Your WhatsApp</h2>
          <p>Open WhatsApp on your phone, go to <b>Linked Devices</b>, tap <b>Link a Device</b>, and scan the QR code below:</p>
          <div class="qr-container">
            <img src="${qrImageUrl}" alt="WhatsApp QR Code" width="300" height="300" style="display: block;" />
          </div>
          <p class="footer">This page will automatically refresh every 15 seconds with a new code if needed.</p>
        </div>
      </body>
    </html>
  `);
});

// Error Handling Middleware
app.use((err, req, res, next) => {
  console.error('Unhandled Error:', err);
  res.status(500).json({
    success: false,
    error: 'Internal Server Error',
    message: err.message
  });
});

// Start Server
if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`==================================================`);
    console.log(`🚀 AI Scam Detector Server running on port ${PORT}`);
    console.log(`📁 Database Mode: ${process.env.USE_LOCAL_DB === 'true' ? 'Local JSON' : 'Firebase Realtime DB'}`);
    console.log(`🤖 Gemini Configured: ${!!process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== 'your_gemini_api_key_here' ? 'Yes' : 'No (using local mock)'}`);
    console.log(`==================================================`);

    // Start free self-hosted WhatsApp Web client
    try {
      const whatsappService = require('./services/whatsapp');
      whatsappService.initialize();
    } catch (err) {
      console.error('❌ Failed to initialize WhatsApp Web client:', err.message);
    }

    // Start automated background threat feeds sync scheduler (every 12 hours)
    const TWELVE_HOURS_MS = 12 * 60 * 60 * 1000;
    setInterval(async () => {
      console.log('⏰ Running scheduled background threat feeds sync...');
      try {
        const syncResult = await scraperService.syncPhishingFeeds();
        console.log(`✅ Scheduled threat feeds sync completed. Synced ${syncResult.syncedCount} records.`);
      } catch (err) {
        console.error('❌ Scheduled threat feeds sync failed:', err.message);
      }
    }, TWELVE_HOURS_MS);

    // Run an initial sync on server start (in the background, non-blocking)
    setTimeout(async () => {
      console.log('🚀 Running initial startup threat feeds sync in background...');
      try {
        const syncResult = await scraperService.syncPhishingFeeds();
        console.log(`✅ Startup threat feeds sync completed. Synced ${syncResult.syncedCount} records.`);
      } catch (err) {
        console.error('❌ Startup threat feeds sync failed:', err.message);
      }
    }, 10000); // start 10 seconds after server boot to allow full connection initialization
  });
}

module.exports = app;
