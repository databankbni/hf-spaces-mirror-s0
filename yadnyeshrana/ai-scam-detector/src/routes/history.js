const express = require('express');
const router = express.Router();
const crypto = require('crypto');
const path = require('path');
const dbService = require('../services/db');
const whatsappService = require('../services/whatsapp');
const { normalizePhone } = require('../services/security');

const otpPhoneLimit = {}; // phone -> lastRequestTime
const otpIpLimit = {}; // ip -> Array of timestamps

function checkOtpRateLimit(phoneNumber, ip) {
  const now = Date.now();
  const THREE_MINUTES = 3 * 60 * 1000;
  const ONE_HOUR = 60 * 60 * 1000;

  // 1. Phone check (1 request per 3 minutes)
  if (otpPhoneLimit[phoneNumber]) {
    const lastRequest = otpPhoneLimit[phoneNumber];
    if (now - lastRequest < THREE_MINUTES) {
      const remainingSeconds = Math.ceil((THREE_MINUTES - (now - lastRequest)) / 1000);
      return {
        allowed: false,
        message: `Please wait ${remainingSeconds} seconds before requesting another code.`
      };
    }
  }

  // 2. IP check (3 requests per hour)
  if (!otpIpLimit[ip]) {
    otpIpLimit[ip] = [];
  }
  
  // Filter out timestamps older than 1 hour
  otpIpLimit[ip] = otpIpLimit[ip].filter(timestamp => now - timestamp < ONE_HOUR);

  if (otpIpLimit[ip].length >= 3) {
    return {
      allowed: false,
      message: "Too many requests from this IP address. Please try again in an hour."
    };
  }

  // Record request
  otpPhoneLimit[phoneNumber] = now;
  otpIpLimit[ip].push(now);

  return { allowed: true };
}

// Background cleanup daemon running hourly to prevent memory leaks
setInterval(() => {
  const now = Date.now();
  const THREE_MINUTES = 3 * 60 * 1000;
  const ONE_HOUR = 60 * 60 * 1000;

  for (const phone in otpPhoneLimit) {
    if (now - otpPhoneLimit[phone] >= THREE_MINUTES) {
      delete otpPhoneLimit[phone];
    }
  }
  for (const ip in otpIpLimit) {
    otpIpLimit[ip] = otpIpLimit[ip].filter(timestamp => now - timestamp < ONE_HOUR);
    if (otpIpLimit[ip].length === 0) {
      delete otpIpLimit[ip];
    }
  }
}, 60 * 60 * 1000);

/**
 * Middleware to authenticate user session token
 */
async function userAuth(req, res, next) {
  const authHeader = req.headers['authorization'];
  const phone = req.query.phone;

  if (!authHeader || !authHeader.startsWith('Bearer ') || !phone) {
    return res.status(401).json({ success: false, error: 'UNAUTHORIZED', message: 'Session token or phone number missing.' });
  }

  const token = authHeader.split(' ')[1];

  try {
    const isValid = await dbService.verifySessionToken(phone, token);
    if (isValid) {
      next();
    } else {
      res.status(401).json({ success: false, error: 'UNAUTHORIZED', message: 'Session expired or invalid. Please log in again.' });
    }
  } catch (error) {
    next(error);
  }
}

/**
 * GET /history
 * Serve the history dashboard HTML page
 */
router.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '../../public/history.html'));
});

/**
 * POST /api/request-otp
 * Request passwordless WhatsApp OTP code
 */
router.post('/api/request-otp', async (req, res, next) => {
  let { phoneNumber } = req.body;

  if (!phoneNumber) {
    return res.status(400).json({ success: false, error: 'MISSING_PARAM', message: 'Phone number is required.' });
  }

  // Normalize phone number (enforce country code formats)
  phoneNumber = normalizePhone(phoneNumber);
  if (!phoneNumber) {
    return res.status(400).json({ success: false, error: 'INVALID_PHONE', message: 'Invalid phone number format.' });
  }

  const rawIp = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
  const ip = rawIp ? rawIp.split(',')[0].trim() : 'unknown';

  // Apply OTP rate limits (protects WhatsApp outbound credits)
  const rateLimit = checkOtpRateLimit(phoneNumber, ip);
  if (!rateLimit.allowed) {
    return res.status(429).json({
      success: false,
      error: 'RATE_LIMIT_EXCEEDED',
      message: rateLimit.message
    });
  }

  try {
    // 1. Fetch user status, check if premium
    const user = await dbService.getUser(phoneNumber);
    
    if (!user.premium) {
      return res.status(403).json({
        success: false,
        error: 'PREMIUM_REQUIRED',
        message: 'Scan history is a Premium feature. Reply UPGRADE on WhatsApp to unlock unlimited checks and logs!'
      });
    }

    // 2. Generate 4-digit code
    const otp = Math.floor(1000 + Math.random() * 9000).toString();

    // 3. Save OTP in DB (valid for 5 minutes)
    await dbService.saveOTP(phoneNumber, otp, 5 * 60 * 1000);

    // 4. Send code via WhatsApp
    const messageText = `🔑 *AI Scam Detector Dashboard*\n\nYour login verification code is: *${otp}*\n\nThis code will expire in 5 minutes. Do not share it with anyone.`;
    
    const sent = await whatsappService.sendMessage(phoneNumber, messageText);
    if (!sent) {
      // If client is not ready (sandbox), we can log the OTP for local test output
      console.log(`🤖 [OTP Sandbox Fallback] Sent OTP *${otp}* to +${phoneNumber}`);
    }

    res.json({
      success: true,
      message: 'Verification code sent to your WhatsApp.'
    });

  } catch (error) {
    next(error);
  }
});

/**
 * POST /api/verify-otp
 * Validate OTP and create session token
 */
router.post('/api/verify-otp', async (req, res, next) => {
  let { phoneNumber, otp } = req.body;

  if (!phoneNumber || !otp) {
    return res.status(400).json({ success: false, error: 'MISSING_PARAM', message: 'Phone number and OTP code are required.' });
  }

  phoneNumber = normalizePhone(phoneNumber);
  if (!phoneNumber) {
    return res.status(400).json({ success: false, error: 'INVALID_PHONE', message: 'Invalid phone number format.' });
  }
  // Strip any non-digits from OTP (handles whitespace, brackets, or copy-paste text)
  otp = otp.replace(/\D/g, '');

  try {
    // 1. Verify OTP
    const isValid = await dbService.verifyOTP(phoneNumber, otp);
    
    if (!isValid) {
      return res.status(401).json({
        success: false,
        error: 'INVALID_OTP',
        message: 'Invalid or expired verification code.'
      });
    }

    // 2. Generate Session Token
    const sessionToken = crypto.randomBytes(16).toString('hex');
    
    // 3. Save session in database
    await dbService.saveSessionToken(phoneNumber, sessionToken);

    res.json({
      success: true,
      sessionToken,
      message: 'OTP verified successfully. Login authorized.'
    });

  } catch (error) {
    next(error);
  }
});

/**
 * GET /api/data
 * Secure endpoint retrieving decrypted logs
 */
router.get('/api/data', userAuth, async (req, res, next) => {
  const { phone } = req.query;
  const cleanPhone = phone.replace(/\D/g, '');

  try {
    const history = await dbService.getUserHistory(cleanPhone);
    const user = await dbService.getUser(cleanPhone);

    res.json({
      success: true,
      stats: {
        totalChecks: user.checksThisMonth || 0,
        expiry: user.premiumExpiry
      },
      history
    });

  } catch (error) {
    next(error);
  }
});

module.exports = router;
