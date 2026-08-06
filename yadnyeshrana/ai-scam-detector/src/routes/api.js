const express = require('express');
const router = express.Router();
const dbService = require('../services/db');
const detectorService = require('../services/detector');

const ipCache = {};

// Background daemon to sweep and clean up expired IP cache logs once per hour (prevents memory leaks)
setInterval(() => {
  const now = Date.now();
  const ONE_DAY = 24 * 60 * 60 * 1000;
  for (const ip in ipCache) {
    if (now - ipCache[ip] >= ONE_DAY) {
      delete ipCache[ip];
    }
  }
}, 60 * 60 * 1000);

/**
 * IP-based rate limiter for anonymous landing page scans (Max 1 per 24 hours per IP)
 */
function anonymousIpRateLimiter(req, res, next) {
  const { phoneNumber } = req.body;
  
  // Skip IP limiting for logged-in / real phone sessions
  if (phoneNumber && phoneNumber !== '919999999999' && phoneNumber !== 'anonymous') {
    return next();
  }

  const rawIp = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
  const ip = rawIp ? rawIp.split(',')[0].trim() : 'unknown';
  
  const now = Date.now();
  const ONE_DAY = 24 * 60 * 60 * 1000;

  if (ipCache[ip]) {
    const lastScan = ipCache[ip];
    if (now - lastScan < ONE_DAY) {
      return res.status(429).json({
        success: false,
        error: 'WEB_LIMIT_EXCEEDED',
        message: 'Web scan limit reached! To continue scanning, upload screenshots, and get real-time protection, chat with our WhatsApp bot!'
      });
    }
  }

  ipCache[ip] = now;
  next();
}

/**
 * POST /api/check-scam
 * Directly check a message for scams (JSON API)
 */
router.post('/check-scam', anonymousIpRateLimiter, async (req, res) => {
  let { message, phoneNumber } = req.body;

  if (!message) {
    return res.status(400).json({
      success: false,
      error: 'MISSING_MESSAGE',
      message: 'Parameter "message" is required.'
    });
  }

  // Default to fallback anonymous phone if not provided
  if (!phoneNumber) {
    phoneNumber = '919999999999';
  }

  try {
    // 1. Enforce usage limits (Freemium Gate)
    const limitCheck = await dbService.incrementUserCheck(phoneNumber);

    if (!limitCheck.allowed) {
      return res.status(403).json({
        success: false,
        error: 'LIMIT_EXCEEDED',
        message: limitCheck.message
      });
    }

    // 2. Perform Scam Detection
    const analysisResult = await detectorService.detectScam(message, phoneNumber);

    // 3. Log results to database
    const checkId = await dbService.logCheck(phoneNumber, message, analysisResult);

    res.json({
      success: true,
      checkId,
      result: analysisResult,
      isPremium: limitCheck.isPremium,
      checksRemaining: limitCheck.isPremium ? null : limitCheck.checksRemaining
    });

  } catch (error) {
    console.error('Error on /api/check-scam:', error);
    res.status(500).json({
      success: false,
      error: 'DETECTION_FAILED',
      message: 'Failed to process message analysis: ' + error.message
    });
  }
});

/**
 * GET /api/stats
 * Public analytics stats
 */
router.get('/stats', async (req, res) => {
  try {
    const stats = await dbService.getStats();
    res.json({
      success: true,
      data: stats
    });
  } catch (error) {
    console.error('Error on /api/stats:', error);
    res.status(500).json({
      success: false,
      error: 'STATS_FAILED',
      message: 'Failed to retrieve stats: ' + error.message
    });
  }
});

/**
 * GET /api/user-history/:phoneNumber
 * Retrieve scam checks history for premium users
 */
router.get('/user-history/:phoneNumber', async (req, res) => {
  const { phoneNumber } = req.params;

  try {
    const user = await dbService.getUser(phoneNumber);

    if (!user.premium) {
      return res.status(403).json({
        success: false,
        error: 'PREMIUM_REQUIRED',
        message: 'View history is a premium-only feature. Upgrade to unlock.'
      });
    }

    const history = await dbService.getUserHistory(phoneNumber);
    res.json({
      success: true,
      history
    });

  } catch (error) {
    console.error('Error on /api/user-history:', error);
    res.status(500).json({
      success: false,
      error: 'HISTORY_FAILED',
      message: 'Failed to retrieve history: ' + error.message
    });
  }
});

/**
 * GET /api/public-scams
 * Fetch last 15-20 public HIGH RISK checks to display as a searchable scam database
 */
router.get('/public-scams', async (req, res) => {
  try {
    const scams = await dbService.getPublicScamTemplates(20);
    res.json({
      success: true,
      scams
    });
  } catch (error) {
    console.error('Error on /api/public-scams:', error);
    res.status(500).json({
      success: false,
      error: 'FETCH_FAILED',
      message: 'Failed to retrieve scam listings: ' + error.message
    });
  }
});

module.exports = router;
