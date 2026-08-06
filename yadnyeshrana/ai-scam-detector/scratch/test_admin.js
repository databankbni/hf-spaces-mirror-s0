require('dotenv').config();
const http = require('http');
const app = require('../src/server');

const TEST_PORT = 3001;
let server;

// Default test password is "admin123" (since it falls back to admin123 if unset)
const adminPassword = process.env.ADMIN_PASSWORD || 'admin123';

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

async function runTests() {
  console.log('\n==================================================');
  console.log('🧪 RUNNING ADMIN DASHBOARD API INTEGRATION TESTS');
  console.log('==================================================\n');

  // Test 1: Health check endpoint (Public)
  console.log('📋 Test 1: Public Health Check...');
  const healthRes = await makeRequest('GET', '/health');
  console.log(`Status: ${healthRes.statusCode}, Bot Status: ${healthRes.body.whatsappStatus}`);
  if (healthRes.statusCode === 200) {
    console.log('✅ Test 1 Passed.');
  } else {
    throw new Error('Test 1 Failed: Health check failed.');
  }
  console.log('--------------------------------------------------');

  // Test 2: Admin stats WITHOUT credentials
  console.log('📋 Test 2: Admin Stats without password header...');
  const statsUnauthRes = await makeRequest('GET', '/admin/api/stats');
  console.log(`Status: ${statsUnauthRes.statusCode}, Error: ${statsUnauthRes.body.error}`);
  if (statsUnauthRes.statusCode === 401 && statsUnauthRes.body.error === 'UNAUTHORIZED') {
    console.log('✅ Test 2 Passed: Rejected unauthenticated request.');
  } else {
    throw new Error('Test 2 Failed: Unauthenticated request was not blocked.');
  }
  console.log('--------------------------------------------------');

  // Test 3: Admin stats WITH invalid credentials
  console.log('📋 Test 3: Admin Stats with invalid password header...');
  const statsInvalidRes = await makeRequest('GET', '/admin/api/stats', { 'x-admin-password': 'wrong_password_123' });
  console.log(`Status: ${statsInvalidRes.statusCode}, Error: ${statsInvalidRes.body.error}`);
  if (statsInvalidRes.statusCode === 401 && statsInvalidRes.body.error === 'UNAUTHORIZED') {
    console.log('✅ Test 3 Passed: Rejected invalid credentials.');
  } else {
    throw new Error('Test 3 Failed: Invalid credentials request was not blocked.');
  }
  console.log('--------------------------------------------------');

  // Test 4: Admin stats WITH valid credentials
  console.log('📋 Test 4: Admin Stats with valid credentials...');
  const statsValidRes = await makeRequest('GET', '/admin/api/stats', { 'x-admin-password': adminPassword });
  console.log(`Status: ${statsValidRes.statusCode}, DB Mode: ${statsValidRes.body.stats.dbMode}, Bot Paused: ${statsValidRes.body.isBotPaused}`);
  if (statsValidRes.statusCode === 200 && statsValidRes.body.success === true) {
    console.log('✅ Test 4 Passed: Authenticated successfully.');
  } else {
    throw new Error('Test 4 Failed: Valid authentication failed.');
  }
  console.log('--------------------------------------------------');

  // Test 5: Toggle Bot Pause to TRUE
  console.log('📋 Test 5: Pausing the WhatsApp Bot...');
  const pauseRes = await makeRequest('POST', '/admin/api/toggle-pause', { 'x-admin-password': adminPassword }, { paused: true });
  console.log(`Status: ${pauseRes.statusCode}, Is Bot Paused: ${pauseRes.body.isBotPaused}, Msg: ${pauseRes.body.message}`);
  if (pauseRes.statusCode === 200 && pauseRes.body.isBotPaused === true) {
    console.log('✅ Test 5 Passed: Bot paused successfully.');
  } else {
    throw new Error('Test 5 Failed: Failed to pause bot.');
  }
  console.log('--------------------------------------------------');

  // Test 6: Verify pause state persisted in stats
  console.log('📋 Test 6: Verifying pause state persistence...');
  const statsPauseCheckRes = await makeRequest('GET', '/admin/api/stats', { 'x-admin-password': adminPassword });
  console.log(`Status: ${statsPauseCheckRes.statusCode}, Persisted Bot Paused: ${statsPauseCheckRes.body.isBotPaused}`);
  if (statsPauseCheckRes.statusCode === 200 && statsPauseCheckRes.body.isBotPaused === true) {
    console.log('✅ Test 6 Passed: Pause state correctly persisted.');
  } else {
    throw new Error('Test 6 Failed: Pause state did not persist.');
  }
  console.log('--------------------------------------------------');

  // Test 7: Add a custom scam pattern heuristics
  console.log('📋 Test 7: Adding custom scam pattern blacklist...');
  const newScamData = {
    pattern: 'Win custom prize check text pattern test 123',
    type: 'lottery_fraud',
    riskLevel: 'HIGH',
    urls: ['test-blacklist-url.com'],
    phoneNumbers: ['919999888877']
  };
  const addScamRes = await makeRequest('POST', '/admin/api/scams', { 'x-admin-password': adminPassword }, newScamData);
  console.log(`Status: ${addScamRes.statusCode}, Pattern ID: ${addScamRes.body.scam.id}, Msg: ${addScamRes.body.message}`);
  const scamId = addScamRes.body.scam.id;
  if (addScamRes.statusCode === 200 && addScamRes.body.success === true && scamId) {
    console.log('✅ Test 7 Passed: Scam pattern registered.');
  } else {
    throw new Error('Test 7 Failed: Failed to register scam pattern.');
  }
  console.log('--------------------------------------------------');

  // Test 8: Get scams and verify the new one is listed
  console.log('📋 Test 8: Fetching scams checklist...');
  const scamsListRes = await makeRequest('GET', '/admin/api/scams', { 'x-admin-password': adminPassword });
  const foundScam = scamsListRes.body.scams.find(s => s.id === scamId);
  console.log(`Status: ${scamsListRes.statusCode}, Scam Records Count: ${scamsListRes.body.scams.length}, Found Newly Added: ${!!foundScam}`);
  if (scamsListRes.statusCode === 200 && foundScam) {
    console.log('✅ Test 8 Passed: Scam verified in list.');
  } else {
    throw new Error('Test 8 Failed: Scam pattern not found in blacklist.');
  }
  console.log('--------------------------------------------------');

  // Test 9: Delete the scam pattern
  console.log('📋 Test 9: Deleting the scam pattern...');
  const deleteRes = await makeRequest('DELETE', `/admin/api/scams/${scamId}`, { 'x-admin-password': adminPassword });
  console.log(`Status: ${deleteRes.statusCode}, Msg: ${deleteRes.body.message}`);
  if (deleteRes.statusCode === 200 && deleteRes.body.success === true) {
    console.log('✅ Test 9 Passed: Scam pattern deleted.');
  } else {
    throw new Error('Test 9 Failed: Failed to delete scam pattern.');
  }
  console.log('--------------------------------------------------');

  // Test 10: Toggle Bot Pause back to FALSE (Resume)
  console.log('📋 Test 10: Resuming the WhatsApp Bot...');
  const resumeRes = await makeRequest('POST', '/admin/api/toggle-pause', { 'x-admin-password': adminPassword }, { paused: false });
  console.log(`Status: ${resumeRes.statusCode}, Is Bot Paused: ${resumeRes.body.isBotPaused}, Msg: ${resumeRes.body.message}`);
  if (resumeRes.statusCode === 200 && resumeRes.body.isBotPaused === false) {
    console.log('✅ Test 10 Passed: Bot resumed successfully.');
  } else {
    throw new Error('Test 10 Failed: Failed to resume bot.');
  }
  console.log('==================================================');
  console.log('✅ ALL ADMIN API TESTS PASSED SUCCESSFULLY!');
  console.log('==================================================');
}

// Start Server and Run Tests
server = app.listen(TEST_PORT, async () => {
  console.log(`📡 Test server started on port ${TEST_PORT}`);
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
