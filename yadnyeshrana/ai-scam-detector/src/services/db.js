const fs = require('fs');
const path = require('path');
const { initializeApp, cert } = require('firebase-admin');
const { getDatabase } = require('firebase-admin/database');
const { hashPhone, encryptMessage, decryptMessage } = require('./security');

// Determine database mode
const useLocalDb = process.env.USE_LOCAL_DB === 'true' || !process.env.FIREBASE_DATABASE_URL;
const localDbFile = path.resolve(process.cwd(), process.env.LOCAL_DB_FILE || 'local_db.json');

let firebaseDb = null;
let localDbCache = null;

// Bot paused state cache to eliminate database reads on every check message
let cachedIsBotPaused = null;
let lastBotPausedFetchTime = 0;
const BOT_PAUSED_CACHE_TTL = 30000; // 30 seconds in-memory cache

// Real-time synchronization cache for scams blocklist to optimize Firebase download bandwidth
let cachedScams = [];
let isScamsSynced = false;
let syncTimeout = null;

// Real-time synchronization cache for test users to eliminate database reads on checks
let cachedTestUsers = {};
let isTestUsersSynced = false;

function setupTestUsersRealtimeSync() {
  if (!firebaseDb) return;
  console.log('🔄 Setting up real-time Firebase sync for test users...');
  firebaseDb.ref('testUsers').on('value', (snapshot) => {
    cachedTestUsers = snapshot.val() || {};
    isTestUsersSynced = true;
    console.log(`⚡ Test users whitelist synced in-memory: ${Object.keys(cachedTestUsers).length} items.`);
  }, (error) => {
    console.error('❌ Failed to sync test users in real-time:', error.message);
  });
}

function setupScamsRealtimeSync() {
  if (!firebaseDb) return;
  console.log('🔄 Setting up real-time Firebase sync for scams blacklist...');
  firebaseDb.ref('scams').on('value', (snapshot) => {
    const val = snapshot.val();
    cachedScams = val ? Object.values(val) : [];
    isScamsSynced = true;

    // Debounce console log to avoid output spam during burst updates
    clearTimeout(syncTimeout);
    syncTimeout = setTimeout(() => {
      console.log(`⚡ Scams blacklist synced in-memory: ${cachedScams.length} items.`);
    }, 100);
  }, (error) => {
    console.error('❌ Failed to sync scams in real-time:', error.message);
  });
}

// Initialize Firebase if configured and not explicitly using local DB
if (!useLocalDb) {
  try {
    let serviceAccount = null;
    const jsonEnv = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;

    if (jsonEnv) {
      if (jsonEnv.trim().startsWith('{')) {
        serviceAccount = JSON.parse(jsonEnv);
      } else {
        serviceAccount = require(path.resolve(process.cwd(), jsonEnv));
      }
    }

    if (serviceAccount) {
      initializeApp({
        credential: cert(serviceAccount),
        databaseURL: process.env.FIREBASE_DATABASE_URL
      });
    } else {
      // Attempt initialization with default credentials
      initializeApp({
        databaseURL: process.env.FIREBASE_DATABASE_URL
      });
    }

    firebaseDb = getDatabase();
    console.log('🔥 Connected to Firebase Realtime Database');
    
    // Seed default test user
    firebaseDb.ref('testUsers/919975528455').set(true).catch(e => console.error('Failed to seed default test user:', e.message));

    // Initialize real-time scams and test users sync
    setupScamsRealtimeSync();
    setupTestUsersRealtimeSync();
  } catch (error) {
    console.error('⚠️ Failed to initialize Firebase. Falling back to local JSON database.', error.message);
  }
}

// ==========================================
// LOCAL DATABASE HELPER FUNCTIONS
// ==========================================
function loadLocalDb() {
  if (localDbCache) return localDbCache;

  if (fs.existsSync(localDbFile)) {
    try {
      const data = fs.readFileSync(localDbFile, 'utf8');
      localDbCache = JSON.parse(data);
      return localDbCache;
    } catch (e) {
      console.error('Error reading local DB, initializing new one:', e);
    }
  }

  // Default initial database structure
  localDbCache = {
    users: {},
    checks: {},
    testUsers: { "919975528455": true },
    scams: [
      {
        id: 'scam_1',
        pattern: 'electricity power will be disconnected',
        type: 'utility_bill_fraud',
        riskLevel: 'HIGH',
        examples: 150,
        lastSeen: new Date().toISOString(),
        keywords: ['electricity', 'disconnected', 'power cut', 'electricity officer', 'bill update'],
        urls: [],
        phoneNumbers: []
      },
      {
        id: 'scam_2',
        pattern: 'KBC Lottery Winner ₹25 Lakhs',
        type: 'lottery_fraud',
        riskLevel: 'HIGH',
        examples: 320,
        lastSeen: new Date().toISOString(),
        keywords: ['kbc', 'lottery', '25 lakh', 'rana pratap singh', 'lucky draw'],
        urls: [],
        phoneNumbers: []
      },
      {
        id: 'scam_3',
        pattern: 'part-time job earn ₹3000-5000 daily',
        type: 'job_fraud',
        riskLevel: 'HIGH',
        examples: 450,
        lastSeen: new Date().toISOString(),
        keywords: ['part-time', 'telegram task', 'work from home', 'daily salary', 'like youtube video'],
        urls: [],
        phoneNumbers: []
      },
      {
        id: 'scam_4',
        pattern: 'SBI account blocked due to KYC',
        type: 'banking_fraud',
        riskLevel: 'HIGH',
        examples: 290,
        lastSeen: new Date().toISOString(),
        keywords: ['sbi', 'blocked', 'kyc', 'netbanking', 'yono', 'update pan'],
        urls: [],
        phoneNumbers: []
      }
    ]
  };
  saveLocalDb();
  return localDbCache;
}

function saveLocalDb() {
  if (!localDbCache) return;
  try {
    fs.writeFileSync(localDbFile, JSON.stringify(localDbCache, null, 2), 'utf8');
  } catch (e) {
    console.error('Error writing to local DB:', e);
  }
}

// Get Date String in India Standard Time (IST) YYYY-MM-DD
function getISTDateString() {
  return new Date().toLocaleDateString('en-US', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).split('/').reverse().join('-'); // Format YYYY-MM-DD
}

// ==========================================
// EXPOSED SERVICE API
// ==========================================

/**
 * Get user profile, or create default if not found
 */
async function getUser(phoneNumber) {
  const cleanNumber = hashPhone(phoneNumber);

  if (firebaseDb) {
    const snapshot = await firebaseDb.ref(`users/${cleanNumber}`).once('value');
    let user = snapshot.val();
    if (!user) {
      user = {
        premium: false,
        premiumExpiry: null,
        checksThisMonth: 0,
        createdAt: new Date().toISOString(),
        lastChecked: null,
        checksToday: 0,
        lastCheckDate: getISTDateString()
      };
      await firebaseDb.ref(`users/${cleanNumber}`).set(user);
    }
    // Check and handle premium expiration
    if (user.premium && user.premiumExpiry && new Date(user.premiumExpiry) < new Date()) {
      user.premium = false;
      user.premiumExpiry = null;
      await firebaseDb.ref(`users/${cleanNumber}`).update({ premium: false, premiumExpiry: null });
    }
    return user;
  } else {
    const db = loadLocalDb();
    let user = db.users[cleanNumber];
    if (!user) {
      user = {
        premium: false,
        premiumExpiry: null,
        checksThisMonth: 0,
        createdAt: new Date().toISOString(),
        lastChecked: null,
        checksToday: 0,
        lastCheckDate: getISTDateString()
      };
      db.users[cleanNumber] = user;
      saveLocalDb();
    }
    // Check and handle premium expiration
    if (user.premium && user.premiumExpiry && new Date(user.premiumExpiry) < new Date()) {
      user.premium = false;
      user.premiumExpiry = null;
      saveLocalDb();
    }
    return user;
  }
}

/**
 * Check if a phone number is a whitelisted Test User
 */
async function isTestUser(phoneNumber) {
  if (!phoneNumber) return false;
  const cleanPhone = phoneNumber.replace(/\D/g, '');
  if (firebaseDb) {
    if (isTestUsersSynced) {
      return !!cachedTestUsers[cleanPhone];
    }
    const snapshot = await firebaseDb.ref(`testUsers/${cleanPhone}`).once('value');
    return !!snapshot.val();
  } else {
    const db = loadLocalDb();
    if (!db.testUsers) db.testUsers = {};
    return !!db.testUsers[cleanPhone];
  }
}

/**
 * Add a Test User
 */
async function addTestUser(phoneNumber) {
  if (!phoneNumber) return false;
  const cleanPhone = phoneNumber.replace(/\D/g, '');
  if (firebaseDb) {
    await firebaseDb.ref(`testUsers/${cleanPhone}`).set(true);
  } else {
    const db = loadLocalDb();
    if (!db.testUsers) db.testUsers = {};
    db.testUsers[cleanPhone] = true;
    saveLocalDb();
  }
  return true;
}

/**
 * Remove a Test User
 */
async function removeTestUser(phoneNumber) {
  if (!phoneNumber) return false;
  const cleanPhone = phoneNumber.replace(/\D/g, '');
  if (firebaseDb) {
    await firebaseDb.ref(`testUsers/${cleanPhone}`).remove();
  } else {
    const db = loadLocalDb();
    if (db.testUsers && db.testUsers[cleanPhone]) {
      delete db.testUsers[cleanPhone];
      saveLocalDb();
    }
  }
  return true;
}

/**
 * List all Test Users
 */
async function getTestUsers() {
  if (firebaseDb) {
    const snapshot = await firebaseDb.ref('testUsers').once('value');
    const val = snapshot.val();
    return val ? Object.keys(val) : [];
  } else {
    const db = loadLocalDb();
    return db.testUsers ? Object.keys(db.testUsers) : [];
  }
}

/**
 * Check if the user is allowed to perform a scam check today.
 * If yes, increments their counter. If no, returns allowed=false.
 */
async function incrementUserCheck(phoneNumber, cachedUser = null) {
  const user = cachedUser || await getUser(phoneNumber);
  const cleanNumber = hashPhone(phoneNumber);
  const today = getISTDateString();

  // If this is a whitelisted test user, bypass limit and allow unlimited checks!
  const isTest = await isTestUser(phoneNumber);

  if (user.premium || isTest) {
    // Premium / Test users have unlimited checks
    const updates = {
      checksThisMonth: (user.checksThisMonth || 0) + 1,
      lastChecked: new Date().toISOString()
    };
    if (firebaseDb) {
      await firebaseDb.ref(`users/${cleanNumber}`).update(updates);
    } else {
      const db = loadLocalDb();
      Object.assign(db.users[cleanNumber], updates);
      saveLocalDb();
    }
    return { allowed: true, isPremium: user.premium || isTest };
  }

  // Free Tier usage logic
  let checksToday = user.checksToday || 0;
  if (user.lastCheckDate !== today) {
    checksToday = 0;
  }

  if (checksToday >= 5) {
    return {
      allowed: false,
      checksRemaining: 0,
      message: '🚨 Daily limit of 5 free checks reached! Upgrade to Premium (₹199/month) for unlimited, priority detection.'
    };
  }

  // Increment counter
  const newChecksToday = checksToday + 1;
  const updates = {
    checksToday: newChecksToday,
    lastCheckDate: today,
    checksThisMonth: (user.checksThisMonth || 0) + 1,
    lastChecked: new Date().toISOString()
  };

  if (firebaseDb) {
    await firebaseDb.ref(`users/${cleanNumber}`).update(updates);
  } else {
    const db = loadLocalDb();
    Object.assign(db.users[cleanNumber], updates);
    saveLocalDb();
  }

  return {
    allowed: true,
    isPremium: false,
    checksRemaining: 5 - newChecksToday
  };
}

/**
 * Log a check details (message & AI analysis output)
 */
async function logCheck(phoneNumber, message, result) {
  const cleanNumber = hashPhone(phoneNumber);
  const checkId = 'check_' + Math.random().toString(36).substring(2, 15);
  const checkData = {
    message: encryptMessage(message),
    result,
    timestamp: new Date().toISOString()
  };

  if (firebaseDb) {
    await firebaseDb.ref(`checks/${cleanNumber}/${checkId}`).set(checkData);
    // Increment daily check stats
    const today = getISTDateString();
    const statsRef = firebaseDb.ref(`analytics/daily/${today}`);
    await statsRef.transaction((current) => {
      const stats = current || { totalChecks: 0, highRiskDetected: 0 };
      stats.totalChecks = (stats.totalChecks || 0) + 1;
      if (result.riskLevel === 'HIGH') {
        stats.highRiskDetected = (stats.highRiskDetected || 0) + 1;
      }
      return stats;
    });
  } else {
    const db = loadLocalDb();
    if (!db.checks[cleanNumber]) {
      db.checks[cleanNumber] = {};
    }
    db.checks[cleanNumber][checkId] = checkData;

    // Increment daily check stats locally
    const today = getISTDateString();
    db.analytics = db.analytics || { daily: {} };
    db.analytics.daily = db.analytics.daily || {};
    const stats = db.analytics.daily[today] || { totalChecks: 0, highRiskDetected: 0 };
    stats.totalChecks = (stats.totalChecks || 0) + 1;
    if (result.riskLevel === 'HIGH') {
      stats.highRiskDetected = (stats.highRiskDetected || 0) + 1;
    }
    db.analytics.daily[today] = stats;

    saveLocalDb();
  }

  return checkId;
}

/**
 * Get list of known scam patterns
 */
async function getKnownScams() {
  if (firebaseDb) {
    if (isScamsSynced) {
      return cachedScams;
    }
    const snapshot = await firebaseDb.ref('scams').once('value');
    const scams = snapshot.val();
    cachedScams = scams ? Object.values(scams) : [];
    isScamsSynced = true;
    return cachedScams;
  } else {
    const db = loadLocalDb();
    return db.scams || [];
  }
}

/**
 * Add a new detected scam pattern to database (or increment counts if exists)
 */
async function addKnownScam(scamData, incrementExamples = true) {
  const scams = await getKnownScams();
  
  // Try to find if a similar pattern exists
  const existingScam = scams.find(s => 
    s.pattern.toLowerCase().includes(scamData.pattern.toLowerCase()) ||
    scamData.pattern.toLowerCase().includes(s.pattern.toLowerCase())
  );

  if (existingScam) {
    const updates = {
      examples: incrementExamples ? (existingScam.examples || 1) + 1 : (existingScam.examples || 1),
      lastSeen: new Date().toISOString()
    };
    if (firebaseDb) {
      // Find the key in Firebase
      const snapshot = await firebaseDb.ref('scams').once('value');
      const allScams = snapshot.val() || {};
      const key = Object.keys(allScams).find(k => allScams[k].id === existingScam.id);
      if (key) {
        await firebaseDb.ref(`scams/${key}`).update(updates);
      }
    } else {
      const db = loadLocalDb();
      const local = db.scams.find(s => s.id === existingScam.id);
      if (local) {
        Object.assign(local, updates);
        saveLocalDb();
      }
    }
    return Object.assign({}, existingScam, updates);
  } else {
    const newScam = {
      id: 'scam_' + Math.random().toString(36).substring(2, 15),
      pattern: scamData.pattern,
      type: scamData.type || 'unknown_fraud',
      riskLevel: scamData.riskLevel || 'HIGH',
      examples: 1,
      lastSeen: new Date().toISOString(),
      keywords: scamData.keywords || [],
      urls: scamData.urls || [],
      phoneNumbers: scamData.phoneNumbers || []
    };

    if (firebaseDb) {
      await firebaseDb.ref('scams').push(newScam);
    } else {
      const db = loadLocalDb();
      db.scams.push(newScam);
      saveLocalDb();
    }
    return newScam;
  }
}

/**
 * Add a batch of new detected scam patterns to database in a single transaction
 */
async function addKnownScamsBatch(scamDataArray) {
  if (!scamDataArray || scamDataArray.length === 0) return [];
  const scams = await getKnownScams();
  const newScamsList = [];

  for (const scamData of scamDataArray) {
    const existingScam = scams.find(s => 
      s.pattern.toLowerCase().includes(scamData.pattern.toLowerCase()) ||
      scamData.pattern.toLowerCase().includes(s.pattern.toLowerCase())
    );

    if (!existingScam) {
      const newScam = {
        id: 'scam_' + Math.random().toString(36).substring(2, 15),
        pattern: scamData.pattern,
        type: scamData.type || 'unknown_fraud',
        riskLevel: scamData.riskLevel || 'HIGH',
        examples: 1,
        lastSeen: new Date().toISOString(),
        keywords: scamData.keywords || [],
        urls: scamData.urls || [],
        phoneNumbers: scamData.phoneNumbers || []
      };
      newScamsList.push(newScam);
    }
  }

  if (newScamsList.length > 0) {
    if (firebaseDb) {
      const batchUpdate = {};
      for (const item of newScamsList) {
        const newKey = firebaseDb.ref('scams').push().key;
        batchUpdate[`scams/${newKey}`] = item;
      }
      await firebaseDb.ref().update(batchUpdate);
    } else {
      const db = loadLocalDb();
      db.scams.push(...newScamsList);
      saveLocalDb();
    }
  }

  return newScamsList;
}

/**
 * Upgrade user to Premium tier
 */
async function setPremium(phoneNumber, months = 1) {
  const cleanNumber = hashPhone(phoneNumber);
  
  // Fetch existing user to check current premium status
  const user = await getUser(phoneNumber);
  
  let expiry = new Date();
  if (user && user.premium && user.premiumExpiry) {
    const currentExpiry = new Date(user.premiumExpiry);
    if (currentExpiry > new Date()) {
      // User has active premium, stack the new months on top of their existing expiry date!
      expiry = currentExpiry;
    }
  }
  expiry.setMonth(expiry.getMonth() + months);

  const updates = {
    premium: true,
    premiumExpiry: expiry.toISOString()
  };

  if (firebaseDb) {
    await firebaseDb.ref(`users/${cleanNumber}`).update(updates);
  } else {
    const db = loadLocalDb();
    const localUser = db.users[cleanNumber] || { createdAt: new Date().toISOString() };
    db.users[cleanNumber] = Object.assign(localUser, updates);
    saveLocalDb();
  }

  return updates;
}

/**
 * Get global statistics
 */
async function getStats() {
  if (firebaseDb) {
    const usersSnap = await firebaseDb.ref('users').once('value');
    const scamsSnap = await firebaseDb.ref('scams').once('value');
    
    const users = usersSnap.val() || {};
    const scams = scamsSnap.val() || {};
    
    const totalUsers = Object.keys(users).length;
    const totalPremium = Object.values(users).filter(u => u.premium).length;
    const totalScamsDetected = Object.values(scams).reduce((acc, curr) => acc + (curr.examples || 0), 0);

    return {
      totalUsers,
      totalPremium,
      totalScamsDetected,
      dbMode: 'Firebase'
    };
  } else {
    const db = loadLocalDb();
    const totalUsers = Object.keys(db.users).length;
    const totalPremium = Object.values(db.users).filter(u => u.premium).length;
    const totalScamsDetected = db.scams.reduce((acc, curr) => acc + (curr.examples || 0), 0);

    return {
      totalUsers,
      totalPremium,
      totalScamsDetected,
      dbMode: 'Local JSON'
    };
  }
}

/**
 * Get all users and their metrics details
 */
async function getAllUsersDetail() {
  if (firebaseDb) {
    const snapshot = await firebaseDb.ref('users').once('value');
    const data = snapshot.val() || {};
    return Object.keys(data).map(hash => ({
      hash,
      ...data[hash]
    }));
  } else {
    const db = loadLocalDb();
    if (!db.users) db.users = {};
    return Object.keys(db.users).map(hash => ({
      hash,
      ...db.users[hash]
    }));
  }
}

/**
 * Set premium status directly by user hash ID
 */
async function setPremiumByHash(userHash, isPremium = true, durationDays = 30) {
  const updates = {
    premium: isPremium,
    premiumExpiry: isPremium 
      ? new Date(Date.now() + durationDays * 24 * 60 * 60 * 1000).toISOString()
      : null
  };

  if (firebaseDb) {
    await firebaseDb.ref(`users/${userHash}`).update(updates);
  } else {
    const db = loadLocalDb();
    if (!db.users) db.users = {};
    if (db.users[userHash]) {
      Object.assign(db.users[userHash], updates);
      saveLocalDb();
    }
  }
  return updates;
}

/**
 * Get check history for a user
 */
async function getUserHistory(phoneNumber) {
  const cleanNumber = hashPhone(phoneNumber);
  return getUserHistoryByHash(cleanNumber);
}

/**
 * Get check history directly by user hash
 */
async function getUserHistoryByHash(userHash) {
  if (firebaseDb) {
    const snapshot = await firebaseDb.ref(`checks/${userHash}`).once('value');
    const data = snapshot.val();
    if (!data) return [];
    const list = Object.values(data);
    return list.map(check => ({
      ...check,
      message: decryptMessage(check.message)
    })).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  } else {
    const db = loadLocalDb();
    const data = db.checks[userHash] || {};
    const list = Object.values(data);
    return list.map(check => ({
      ...check,
      message: decryptMessage(check.message)
    })).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }
}

/**
 * Check if the bot is currently paused
 */
async function isBotPaused() {
  if (cachedIsBotPaused !== null && (Date.now() - lastBotPausedFetchTime < BOT_PAUSED_CACHE_TTL)) {
    return cachedIsBotPaused;
  }

  if (firebaseDb) {
    try {
      const snapshot = await firebaseDb.ref('appSettings/isBotPaused').once('value');
      cachedIsBotPaused = !!snapshot.val();
      lastBotPausedFetchTime = Date.now();
      return cachedIsBotPaused;
    } catch (err) {
      console.error('Error fetching app settings:', err.message);
      return cachedIsBotPaused || false;
    }
  } else {
    const db = loadLocalDb();
    db.appSettings = db.appSettings || { isBotPaused: false };
    cachedIsBotPaused = !!db.appSettings.isBotPaused;
    lastBotPausedFetchTime = Date.now();
    return cachedIsBotPaused;
  }
}

/**
 * Toggle the pause state of the bot
 */
async function setBotPaused(paused) {
  const isPaused = !!paused;
  cachedIsBotPaused = isPaused;
  lastBotPausedFetchTime = Date.now();

  if (firebaseDb) {
    await firebaseDb.ref('appSettings/isBotPaused').set(isPaused);
  } else {
    const db = loadLocalDb();
    db.appSettings = db.appSettings || { isBotPaused: false };
    db.appSettings.isBotPaused = isPaused;
    saveLocalDb();
  }
  return isPaused;
}

/**
 * Delete a registered scam pattern by ID
 */
async function deleteKnownScam(id) {
  if (firebaseDb) {
    const snapshot = await firebaseDb.ref('scams').once('value');
    const allScams = snapshot.val() || {};
    const key = Object.keys(allScams).find(k => allScams[k].id === id);
    if (key) {
      await firebaseDb.ref(`scams/${key}`).remove();
      return true;
    }
    return false;
  } else {
    const db = loadLocalDb();
    const index = db.scams.findIndex(s => s.id === id);
    if (index !== -1) {
      db.scams.splice(index, 1);
      saveLocalDb();
      return true;
    }
    return false;
  }
}

/**
 * Save temporary OTP code for a phone number
 */
async function saveOTP(phoneNumber, otp, expiryMs = 300000) { // Default 5 minutes
  const cleanNumber = hashPhone(phoneNumber);
  const expiry = new Date(Date.now() + expiryMs).toISOString();
  const otpData = { otp, expiry };

  if (firebaseDb) {
    await firebaseDb.ref(`otps/${cleanNumber}`).set(otpData);
  } else {
    const db = loadLocalDb();
    db.otps = db.otps || {};
    db.otps[cleanNumber] = otpData;
    saveLocalDb();
  }
  return true;
}

/**
 * Verify if the OTP matches and is not expired.
 * Deletes the OTP after verification check.
 */
async function verifyOTP(phoneNumber, otp) {
  const cleanNumber = hashPhone(phoneNumber);
  let otpData = null;

  if (firebaseDb) {
    const snapshot = await firebaseDb.ref(`otps/${cleanNumber}`).once('value');
    otpData = snapshot.val();
    if (otpData) {
      await firebaseDb.ref(`otps/${cleanNumber}`).remove(); // Delete immediately
    }
  } else {
    const db = loadLocalDb();
    db.otps = db.otps || {};
    otpData = db.otps[cleanNumber];
    if (otpData) {
      delete db.otps[cleanNumber];
      saveLocalDb();
    }
  }

  if (!otpData) return false;

  const isMatch = otpData.otp === otp;
  const isNotExpired = new Date(otpData.expiry) > new Date();

  return isMatch && isNotExpired;
}

/**
 * Save active session token for a user
 */
async function saveSessionToken(phoneNumber, token) {
  const cleanNumber = hashPhone(phoneNumber);
  const expiry = new Date();
  expiry.setDate(expiry.getDate() + 7); // Valid for 7 days

  const tokenData = {
    token,
    expiry: expiry.toISOString()
  };

  if (firebaseDb) {
    await firebaseDb.ref(`users/${cleanNumber}/session`).set(tokenData);
  } else {
    const db = loadLocalDb();
    const user = db.users[cleanNumber];
    if (user) {
      user.session = tokenData;
      saveLocalDb();
    }
  }
  return true;
}

/**
 * Verify if the session token is valid for a user
 */
async function verifySessionToken(phoneNumber, token) {
  const cleanNumber = hashPhone(phoneNumber);
  let tokenData = null;

  if (firebaseDb) {
    const snapshot = await firebaseDb.ref(`users/${cleanNumber}/session`).once('value');
    tokenData = snapshot.val();
  } else {
    const db = loadLocalDb();
    const user = db.users[cleanNumber];
    if (user) {
      tokenData = user.session;
    }
  }

  if (!tokenData) return false;

  const isMatch = tokenData.token === token;
  const isNotExpired = new Date(tokenData.expiry) > new Date();

  return isMatch && isNotExpired;
}


/**
 * Retrieve OTP for testing purposes (does not delete)
 */
async function getOTPForTesting(phoneNumber) {
  const cleanNumber = hashPhone(phoneNumber);
  if (firebaseDb) {
    const snapshot = await firebaseDb.ref(`otps/${cleanNumber}`).once('value');
    const val = snapshot.val();
    return val ? val.otp : null;
  } else {
    const db = loadLocalDb();
    db.otps = db.otps || {};
    const val = db.otps[cleanNumber];
    return val ? val.otp : null;
  }
}

/**
 * Get daily scan stats for charts
 */
async function getAnalyticsStats() {
  if (firebaseDb) {
    const snapshot = await firebaseDb.ref('analytics/daily').once('value');
    return snapshot.val() || {};
  } else {
    const db = loadLocalDb();
    db.analytics = db.analytics || { daily: {} };
    return db.analytics.daily || {};
  }
}

/**
 * Get all recent checks across all users (for admin audit log)
 */
async function getAllRecentChecks(limit = 20) {
  if (firebaseDb) {
    const snapshot = await firebaseDb.ref('checks').once('value');
    const val = snapshot.val() || {};
    let allChecks = [];
    
    // Flat map all checks
    for (const userHash in val) {
      const userChecks = val[userHash];
      for (const checkId in userChecks) {
        const check = userChecks[checkId];
        try {
          allChecks.push({
            ...check,
            message: decryptMessage(check.message),
            userHash: userHash
          });
        } catch (e) {
          // ignore decrypt errors
        }
      }
    }
    
    // Sort by timestamp descending and take the limit
    return allChecks
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, limit);
  } else {
    const db = loadLocalDb();
    const val = db.checks || {};
    let allChecks = [];
    
    for (const userHash in val) {
      const userChecks = val[userHash];
      for (const checkId in userChecks) {
        const check = userChecks[checkId];
        try {
          allChecks.push({
            ...check,
            message: decryptMessage(check.message),
            userHash: userHash
          });
        } catch (e) {
          // ignore
        }
      }
    }
    
    return allChecks
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, limit);
  }
}

/**
 * Log a transaction to the database
 */
async function logTransaction(phoneNumber, amount, orderId, paymentId, status = 'success') {
  const cleanNumber = hashPhone(phoneNumber);
  const txnId = `txn_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`;
  const txnData = {
    id: txnId,
    userHash: cleanNumber,
    amount: amount || 199,
    orderId: orderId || 'mock',
    paymentId: paymentId || 'mock',
    status,
    timestamp: new Date().toISOString()
  };

  if (firebaseDb) {
    await firebaseDb.ref(`transactions/${txnId}`).set(txnData);
  } else {
    const db = loadLocalDb();
    db.transactions = db.transactions || {};
    db.transactions[txnId] = txnData;
    saveLocalDb();
  }
  return txnData;
}

/**
 * Get recent transactions
 */
async function getTransactions(limit = 20) {
  if (firebaseDb) {
    const snapshot = await firebaseDb.ref('transactions').once('value');
    const val = snapshot.val() || {};
    return Object.values(val)
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, limit);
  } else {
    const db = loadLocalDb();
    const val = db.transactions || {};
    return Object.values(val)
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, limit);
  }
}

/**
 * Set user reporting state
 */
async function setUserReportingState(phoneNumber, isActive) {
  const cleanNumber = hashPhone(phoneNumber);
  const updates = {
    reportingState: isActive
  };

  if (firebaseDb) {
    await firebaseDb.ref(`users/${cleanNumber}`).update(updates);
  } else {
    const db = loadLocalDb();
    const user = db.users[cleanNumber] || { createdAt: new Date().toISOString() };
    db.users[cleanNumber] = Object.assign(user, updates);
    saveLocalDb();
  }
}

/**
 * Retrieve recent high-risk checks and sanitize them for a public search database (SEO-friendly)
 */
async function getPublicScamTemplates(limit = 15) {
  const recent = await getAllRecentChecks(50);
  
  const publicScams = recent
    .filter(c => c.result && c.result.riskLevel === 'HIGH')
    .map(c => {
      // Basic sanitization of message content
      let text = c.message || '';
      
      // Redact Indian phone numbers (10 digits, optionally with +91 or 91)
      text = text.replace(/(\+?91)?\s*\d{10}/g, '[REDACTED PHONE]');
      
      // Redact email addresses
      text = text.replace(/[\w\.-]+@[\w\.-]+\.\w+/g, '[REDACTED EMAIL]');

      // Redact generic OTP/PIN numbers (4 to 6 digit codes)
      text = text.replace(/\b\d{4,6}\b/g, '[REDACTED CODE]');

      return {
        id: c.timestamp + '_' + Math.random().toString(36).substring(2, 7), // randomized public ID
        message: text,
        type: c.result.type,
        explanation: c.result.explanation,
        timestamp: c.timestamp
      };
    });

  return publicScams.slice(0, limit);
}

/**
 * Get user reporting state
 */
async function getUserReportingState(phoneNumber) {
  const cleanNumber = hashPhone(phoneNumber);
  if (firebaseDb) {
    const snapshot = await firebaseDb.ref(`users/${cleanNumber}/reportingState`).once('value');
    return !!snapshot.val();
  } else {
    const db = loadLocalDb();
    const user = db.users[cleanNumber] || {};
    return !!user.reportingState;
  }
}

module.exports = {
  getPublicScamTemplates,
  getUser,
  incrementUserCheck,
  logCheck,
  getKnownScams,
  addKnownScam,
  addKnownScamsBatch,
  setPremium,
  getStats,
  getUserHistory,
  isBotPaused,
  setBotPaused,
  deleteKnownScam,
  saveOTP,
  verifyOTP,
  saveSessionToken,
  verifySessionToken,
  getOTPForTesting,
  getAnalyticsStats,
  getAllRecentChecks,
  logTransaction,
  getTransactions,
  setUserReportingState,
  getUserReportingState,
  addTestUser,
  removeTestUser,
  getTestUsers,
  isTestUser,
  getAllUsersDetail,
  setPremiumByHash,
  getUserHistoryByHash
};

