const express = require('express');
const router = express.Router();
const path = require('path');
const dbService = require('../services/db');
const whatsappService = require('../services/whatsapp');
const scraperService = require('../services/scraper');

// Simple admin password authentication from environment settings
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin123';

/**
 * Admin authorization middleware
 */
function adminAuth(req, res, next) {
  const password = req.headers['x-admin-password'];
  if (password === ADMIN_PASSWORD) {
    next();
  } else {
    res.status(401).json({ 
      success: false, 
      error: 'UNAUTHORIZED', 
      message: 'Invalid admin password. Please try again.' 
    });
  }
}

/**
 * GET /admin
 * Serve the dashboard HTML file
 */
router.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '../../public/admin.html'));
});

/**
 * POST /admin/api/login
 * Verify password and return success status
 */
router.post('/api/login', (req, res) => {
  const { password } = req.body;
  if (password === ADMIN_PASSWORD) {
    res.json({ success: true, message: 'Authenticated successfully.' });
  } else {
    res.status(401).json({ success: false, error: 'INVALID_PASSWORD', message: 'Invalid admin password.' });
  }
});

/**
 * GET /admin/api/stats
 * Fetch live system status, connection states, and check counts
 */
router.get('/api/stats', adminAuth, async (req, res, next) => {
  try {
    const stats = await dbService.getStats();
    const isReady = whatsappService.isReady();
    const hasQr = !!whatsappService.getLatestQr();
    const isPaused = await dbService.isBotPaused();

    res.json({
      success: true,
      stats,
      whatsappStatus: isReady ? 'CONNECTED' : (hasQr ? 'PAIRING_REQUIRED' : 'INITIALIZING'),
      isBotPaused: isPaused
    });
  } catch (error) {
    next(error);
  }
});

/**
 * POST /admin/api/toggle-pause
 * Enable/Disable the WhatsApp bot message processing
 */
router.post('/api/toggle-pause', adminAuth, async (req, res, next) => {
  const { paused } = req.body;
  
  if (paused === undefined) {
    return res.status(400).json({ success: false, error: 'MISSING_PARAM', message: 'Parameter "paused" is required.' });
  }

  try {
    const isPaused = await dbService.setBotPaused(paused);
    res.json({
      success: true,
      isBotPaused: isPaused,
      message: isPaused ? 'WhatsApp Bot has been paused.' : 'WhatsApp Bot has been resumed.'
    });
  } catch (error) {
    next(error);
  }
});

/**
 * GET /admin/api/scams
 * Get list of all registered scam patterns
 */
router.get('/api/scams', adminAuth, async (req, res, next) => {
  try {
    const scams = await dbService.getKnownScams();
    res.json({
      success: true,
      scams: scams.sort((a, b) => new Date(b.lastSeen) - new Date(a.lastSeen))
    });
  } catch (error) {
    next(error);
  }
});

/**
 * POST /admin/api/scams
 * Add a new manual blacklist scam pattern
 */
router.post('/api/scams', adminAuth, async (req, res, next) => {
  const { pattern, type, riskLevel, keywords, urls, phoneNumbers } = req.body;

  if (!pattern) {
    return res.status(400).json({ success: false, error: 'MISSING_PARAM', message: 'Parameter "pattern" is required.' });
  }

  try {
    const newScam = await dbService.addKnownScam({
      pattern,
      type: type || 'other_fraud',
      riskLevel: riskLevel || 'HIGH',
      keywords: keywords || [],
      urls: urls || [],
      phoneNumbers: phoneNumbers || []
    });

    res.json({
      success: true,
      scam: newScam,
      message: 'Scam pattern registered successfully.'
    });
  } catch (error) {
    next(error);
  }
});

/**
 * DELETE /admin/api/scams/:id
 * Remove a registered scam pattern from heuristics blacklist
 */
router.delete('/api/scams/:id', adminAuth, async (req, res, next) => {
  const { id } = req.params;

  try {
    const deleted = await dbService.deleteKnownScam(id);
    if (deleted) {
      res.json({ success: true, message: 'Scam pattern deleted successfully.' });
    } else {
      res.status(404).json({ success: false, error: 'NOT_FOUND', message: 'Scam pattern ID not found.' });
    }
  } catch (error) {
    next(error);
  }
});

/**
 * POST /admin/api/sync-feeds
 * Sync live threat intelligence phishing feeds
 */
router.post('/api/sync-feeds', adminAuth, async (req, res, next) => {
  try {
    const result = await scraperService.syncPhishingFeeds();
    if (result.success) {
      res.json({
        success: true,
        syncedCount: result.syncedCount,
        message: `Threat intelligence feeds synced successfully. Registered ${result.syncedCount} new scam indicators.`
      });
    } else {
      res.status(502).json({
        success: false,
        error: 'FEED_SYNC_FAILED',
        message: result.error
      });
    }
  } catch (error) {
    next(error);
  }
});

/**
 * GET /admin/api/analytics
 * Fetch analytics data for charts (daily trends, scam types, users)
 */
router.get('/api/analytics', adminAuth, async (req, res, next) => {
  try {
    const stats = await dbService.getStats();
    const scams = await dbService.getKnownScams();
    const daily = await dbService.getAnalyticsStats();

    // Aggregate scam types distribution
    const scamTypes = {};
    scams.forEach(s => {
      const type = s.type || 'other_fraud';
      scamTypes[type] = (scamTypes[type] || 0) + (s.examples || 1);
    });

    res.json({
      success: true,
      stats,
      daily,
      scamTypes
    });
  } catch (error) {
    next(error);
  }
});

/**
 * GET /admin/api/recent-checks
 * Fetch recent scans audit log
 */
router.get('/api/recent-checks', adminAuth, async (req, res, next) => {
  try {
    const checks = await dbService.getAllRecentChecks(20);
    res.json({
      success: true,
      checks
    });
  } catch (error) {
    next(error);
  }
});

/**
 * GET /admin/api/transactions
 * Fetch recent payment transactions & compile total earnings
 */
router.get('/api/transactions', adminAuth, async (req, res, next) => {
  try {
    const transactions = await dbService.getTransactions(30);
    const totalEarnings = transactions
      .filter(t => t.status === 'success')
      .reduce((acc, t) => acc + (t.amount || 199), 0);

    res.json({
      success: true,
      transactions,
      totalEarnings
    });
  } catch (error) {
    next(error);
  }
});

/**
 * GET /admin/api/test-users
 * List all test users
 */
router.get('/api/test-users', adminAuth, async (req, res, next) => {
  try {
    const users = await dbService.getTestUsers();
    res.json({
      success: true,
      users
    });
  } catch (error) {
    next(error);
  }
});

/**
 * POST /admin/api/test-users
 * Add a test user
 */
router.post('/api/test-users', adminAuth, async (req, res, next) => {
  try {
    const { phoneNumber } = req.body;
    if (!phoneNumber) {
      return res.status(400).json({ success: false, error: 'MISSING_PARAM', message: 'Phone number is required.' });
    }
    await dbService.addTestUser(phoneNumber);
    res.json({
      success: true,
      message: `Test user +${phoneNumber} added successfully.`
    });
  } catch (error) {
    next(error);
  }
});

/**
 * DELETE /admin/api/test-users
 * Remove a test user
 */
router.delete('/api/test-users', adminAuth, async (req, res, next) => {
  try {
    const { phoneNumber } = req.body;
    if (!phoneNumber) {
      return res.status(400).json({ success: false, error: 'MISSING_PARAM', message: 'Phone number is required.' });
    }
    await dbService.removeTestUser(phoneNumber);
    res.json({
      success: true,
      message: `Test user +${phoneNumber} removed successfully.`
    });
  } catch (error) {
    next(error);
  }
});

/**
 * GET /admin/api/users
 * Fetch list of all registered users and metrics
 */
router.get('/api/users', adminAuth, async (req, res, next) => {
  try {
    const users = await dbService.getAllUsersDetail();
    res.json({
      success: true,
      users
    });
  } catch (error) {
    next(error);
  }
});

/**
 * GET /admin/api/users/:hash/checks
 * Fetch recent scan history of a specific user hash
 */
router.get('/api/users/:hash/checks', adminAuth, async (req, res, next) => {
  const { hash } = req.params;
  try {
    const checks = await dbService.getUserHistoryByHash(hash);
    res.json({
      success: true,
      checks
    });
  } catch (error) {
    next(error);
  }
});

/**
 * POST /admin/api/users/:hash/toggle-premium
 * Grant or revoke Pro status manually for a user hash
 */
router.post('/api/users/:hash/toggle-premium', adminAuth, async (req, res, next) => {
  const { hash } = req.params;
  const { premium } = req.body;
  
  if (premium === undefined) {
    return res.status(400).json({ success: false, error: 'MISSING_PARAM', message: 'Parameter "premium" is required.' });
  }

  try {
    const updates = await dbService.setPremiumByHash(hash, premium, 30);
    res.json({
      success: true,
      premium: updates.premium,
      premiumExpiry: updates.premiumExpiry,
      message: updates.premium 
        ? 'User has been upgraded to Premium (Pro status).'
        : 'User Premium status has been revoked.'
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
