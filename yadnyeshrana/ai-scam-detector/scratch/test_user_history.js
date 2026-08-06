require('dotenv').config();
const http = require('http');
const fs = require('fs');
const path = require('path');
const { getApps } = require('firebase-admin/app');
const { getDatabase } = require('firebase-admin/database');
const app = require('../src/server');
const dbService = require('../src/services/db');
const { hashPhone } = require('../src/services/security');

const TEST_PORT = 3002;
let server;

/**
 * Make an HTTP request helper
 */
function makeRequest(method, path, headers = {}, body = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'localhost',
      port: TEST_PORT,
      path: path,
      method: method,
      headers: {
        'Content-Type': 'application/json',
        ...headers
      }
    };

    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => {
        data += chunk;
      });
      res.on('end', () => {
        try {
          resolve({
            statusCode: res.statusCode,
            body: data.startsWith('{') ? JSON.parse(data) : data
          });
        } catch (e) {
          resolve({ statusCode: res.statusCode, body: data });
        }
      });
    });

    req.on('error', (err) => {
      reject(err);
    });

    if (body) {
      req.write(JSON.stringify(body));
    }
    req.end();
  });
}

/**
 * Reset test user data from database (handles live Firebase and local JSON)
 */
async function resetTestUser(phone) {
  const cleanNumber = hashPhone(phone);
  if (getApps().length > 0) {
    const firebaseDb = getDatabase();
    await firebaseDb.ref(`users/${cleanNumber}`).remove();
    await firebaseDb.ref(`checks/${cleanNumber}`).remove();
    await firebaseDb.ref(`otps/${cleanNumber}`).remove();
    console.log(`🧹 Cleaned up live Firebase DB nodes for hash: ${cleanNumber}`);
  } else {
    const localDbFile = path.resolve(process.cwd(), process.env.LOCAL_DB_FILE || 'local_db.json');
    if (fs.existsSync(localDbFile)) {
      try {
        const db = JSON.parse(fs.readFileSync(localDbFile, 'utf8'));
        if (db.users) delete db.users[cleanNumber];
        if (db.checks) delete db.checks[cleanNumber];
        if (db.otps) delete db.otps[cleanNumber];
        fs.writeFileSync(localDbFile, JSON.stringify(db, null, 2), 'utf8');
        console.log(`🧹 Cleaned up local JSON DB nodes for hash: ${cleanNumber}`);
      } catch (err) {
        console.error('⚠️ Failed to clean up local DB file:', err.message);
      }
    }
  }
}

async function runTests() {
  console.log('\n==================================================');
  console.log('🧪 RUNNING PREMIUM USER HISTORY API INTEGRATION TESTS');
  console.log('==================================================\n');

  const testPhone = '919999999999';

  // Make sure we start clean
  await resetTestUser(testPhone);

  // Test 1: Non-premium user request OTP block
  console.log('📋 Test 1: Requesting OTP for a non-premium user...');
  const reqOtpUnauth = await makeRequest('POST', '/history/api/request-otp', {}, { phoneNumber: testPhone });
  console.log(`Status: ${reqOtpUnauth.statusCode}, Error: ${reqOtpUnauth.body.error}, Msg: ${reqOtpUnauth.body.message}`);
  if (reqOtpUnauth.statusCode === 403 && reqOtpUnauth.body.error === 'PREMIUM_REQUIRED') {
    console.log('✅ Test 1 Passed: Successfully blocked non-premium user.');
  } else {
    throw new Error('Test 1 Failed: Non-premium user was not blocked.');
  }
  console.log('--------------------------------------------------');

  // Test 2: Upgrade user to Premium and request OTP
  console.log('📋 Test 2: Upgrading user to Premium and requesting OTP...');
  await dbService.setPremium(testPhone, 1);
  const reqOtpPremium = await makeRequest('POST', '/history/api/request-otp', {}, { phoneNumber: testPhone });
  console.log(`Status: ${reqOtpPremium.statusCode}, Success: ${reqOtpPremium.body.success}, Msg: ${reqOtpPremium.body.message}`);
  if (reqOtpPremium.statusCode === 200 && reqOtpPremium.body.success === true) {
    console.log('✅ Test 2 Passed: Successfully sent OTP for Premium user.');
  } else {
    throw new Error('Test 2 Failed: Failed to request OTP for Premium user.');
  }
  console.log('--------------------------------------------------');

  // Test 3: Fetch OTP from DB and verify mismatch
  console.log('📋 Test 3: Verifying OTP with an incorrect code...');
  const firstOtp = await dbService.getOTPForTesting(testPhone);
  console.log(`Stored OTP fetched for testing: ${firstOtp}`);
  if (!firstOtp) {
    throw new Error('Test 3 Failed: OTP was not generated in the database.');
  }

  const verifyInvalid = await makeRequest('POST', '/history/api/verify-otp', {}, { phoneNumber: testPhone, otp: '0000' });
  console.log(`Status: ${verifyInvalid.statusCode}, Error: ${verifyInvalid.body.error}, Msg: ${verifyInvalid.body.message}`);
  if (verifyInvalid.statusCode === 401 && verifyInvalid.body.error === 'INVALID_OTP') {
    console.log('✅ Test 3 Passed: Successfully rejected invalid OTP.');
  } else {
    throw new Error('Test 3 Failed: Failed to reject invalid OTP.');
  }
  console.log('--------------------------------------------------');

  // Test 3.5: Verify that the first OTP is now deleted / single-use
  console.log('📋 Test 3.5: Verifying single-use security (retrying with the old correct code)...');
  const verifyOldCorrect = await makeRequest('POST', '/history/api/verify-otp', {}, { phoneNumber: testPhone, otp: firstOtp });
  console.log(`Status: ${verifyOldCorrect.statusCode}, Error: ${verifyOldCorrect.body.error}, Msg: ${verifyOldCorrect.body.message}`);
  if (verifyOldCorrect.statusCode === 401 && verifyOldCorrect.body.error === 'INVALID_OTP') {
    console.log('✅ Test 3.5 Passed: Single-use security confirmed. Old code was deleted.');
  } else {
    throw new Error('Test 3.5 Failed: Old code was not deleted after first verification attempt.');
  }
  console.log('--------------------------------------------------');

  // Test 4: Request a new OTP and verify with correct code
  console.log('📋 Test 4: Requesting new OTP and verifying with correct code...');
  const reqNewOtp = await makeRequest('POST', '/history/api/request-otp', {}, { phoneNumber: testPhone });
  if (reqNewOtp.statusCode !== 200) {
    throw new Error('Test 4 Failed: Failed to request new OTP.');
  }
  
  const newOtp = await dbService.getOTPForTesting(testPhone);
  console.log(`New Stored OTP fetched for testing: ${newOtp}`);
  
  const verifyValid = await makeRequest('POST', '/history/api/verify-otp', {}, { phoneNumber: testPhone, otp: newOtp });
  console.log(`Status: ${verifyValid.statusCode}, Success: ${verifyValid.body.success}, Token: ${verifyValid.body.sessionToken}`);
  const sessionToken = verifyValid.body.sessionToken;
  if (verifyValid.statusCode === 200 && verifyValid.body.success === true && sessionToken) {
    console.log('✅ Test 4 Passed: Successfully authorized login & received session token.');
  } else {
    throw new Error('Test 4 Failed: Failed to verify correct OTP.');
  }
  console.log('--------------------------------------------------');

  // Test 5: Fetch history data with invalid session token
  console.log('📋 Test 5: Fetching user stats and history with invalid token...');
  const dataUnauth = await makeRequest('GET', `/history/api/data?phone=${testPhone}`, {
    'Authorization': 'Bearer invalid_token_123'
  });
  console.log(`Status: ${dataUnauth.statusCode}, Error: ${dataUnauth.body.error}`);
  if (dataUnauth.statusCode === 401 && dataUnauth.body.error === 'UNAUTHORIZED') {
    console.log('✅ Test 5 Passed: Successfully blocked access with invalid session token.');
  } else {
    throw new Error('Test 5 Failed: Allowed access to data with invalid token.');
  }
  console.log('--------------------------------------------------');

  // Test 6: Fetch history data with correct session token
  console.log('📋 Test 6: Fetching user stats and history with correct token (decryption verification)...');
  
  // Log some test checks for the user
  const msg1 = "Urgent: Your electricity bill is pending. Click to pay now http://fakebill-pay.in";
  const result1 = { riskLevel: "HIGH", confidence: 95, explanation: "Utility payment link scam", actions: ["Do not click link", "Verify with electricity provider"] };
  const msg2 = "Hi, how are you? Let us catch up this weekend.";
  const result2 = { riskLevel: "SAFE", confidence: 5, explanation: "Normal personal conversation message", actions: [] };

  await dbService.logCheck(testPhone, msg1, result1);
  await dbService.logCheck(testPhone, msg2, result2);

  const dataAuth = await makeRequest('GET', `/history/api/data?phone=${testPhone}`, {
    'Authorization': `Bearer ${sessionToken}`
  });
  console.log(`Status: ${dataAuth.statusCode}, Success: ${dataAuth.body.success}, Total Checks: ${dataAuth.body.stats.totalChecks}, Logs Found: ${dataAuth.body.history ? dataAuth.body.history.length : 0}`);
  
  if (dataAuth.statusCode === 200 && dataAuth.body.success === true) {
    const history = dataAuth.body.history;
    if (history.length !== 2) {
      throw new Error(`Test 6 Failed: Expected 2 scan items, got ${history.length}`);
    }
    
    // Verify decryption of the messages
    console.log(`Decrypted message 1: "${history[0].message}"`);
    console.log(`Decrypted message 2: "${history[1].message}"`);

    // Sorted by timestamp (newest first).
    const messages = history.map(h => h.message);
    if (messages.includes(msg1) && messages.includes(msg2)) {
      console.log('✅ Decryption verified! Encrypted DB logs decrypted correctly on-the-fly.');
      console.log('✅ Test 6 Passed.');
    } else {
      throw new Error('Test 6 Failed: Message contents were not decrypted correctly.');
    }
  } else {
    throw new Error('Test 6 Failed: Failed to fetch user stats and history data.');
  }
  console.log('--------------------------------------------------');

  // Test 7: Phone number normalization check
  console.log('📋 Test 7: Requesting OTP for formatted, short, and leading-zero numbers...');
  
  // Force clean user state to premium
  await dbService.setPremium(testPhone, 1);
  
  // A. 10-digit number without country code: "9999999999" (should match testPhone '919999999999')
  const reqShort = await makeRequest('POST', '/history/api/request-otp', {}, { phoneNumber: '9999999999' });
  console.log(`   Short Number (10 digits) Status: ${reqShort.statusCode}, Msg: ${reqShort.body.message}`);
  
  // B. Formatted number: "+91 99999-99999"
  const reqFormatted = await makeRequest('POST', '/history/api/request-otp', {}, { phoneNumber: '+91 99999-99999' });
  console.log(`   Formatted Number Status: ${reqFormatted.statusCode}, Msg: ${reqFormatted.body.message}`);
  
  // C. Leading-zero domestic number: "09999999999"
  const reqZero = await makeRequest('POST', '/history/api/request-otp', {}, { phoneNumber: '09999999999' });
  console.log(`   Leading Zero Number Status: ${reqZero.statusCode}, Msg: ${reqZero.body.message}`);
  
  if (reqShort.statusCode === 200 && reqFormatted.statusCode === 200 && reqZero.statusCode === 200) {
    console.log('✅ Test 7 Passed: Phone number normalization successfully validated on lookups.');
  } else {
    throw new Error('Test 7 Failed: Normalization logic did not match the premium user.');
  }
  console.log('--------------------------------------------------');

  // Cleanup test user
  await resetTestUser(testPhone);

  console.log('==================================================');
  console.log('✅ ALL PREMIUM USER HISTORY TESTS PASSED SUCCESSFULLY!');
  console.log('==================================================');
}

// Start Server and Run Tests
server = app.listen(TEST_PORT, async () => {
  console.log(`📡 User History Test server started on port ${TEST_PORT}`);
  try {
    await runTests();
    server.close(() => {
      console.log('🔌 Test server stopped.');
      process.exit(0);
    });
  } catch (err) {
    console.error('❌ Integration Tests Failed:', err.message);
    server.close(() => {
      console.log('🔌 Test server stopped.');
      process.exit(1);
    });
  }
});
