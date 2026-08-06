require('dotenv').config();
const scraperService = require('../src/services/scraper');

async function test() {
  console.log('🧪 TESTING THREAT INTELLIGENCE SCRAPER LIVE');
  console.log('==================================================');
  
  const result = await scraperService.syncPhishingFeeds();
  
  console.log('--------------------------------------------------');
  console.log('Scraper Sync Success:', result.success);
  console.log('Synced Count:', result.syncedCount);
  console.log('Error (if any):', result.error);
  
  if (result.success && result.syncedCount > 0) {
    console.log('✅ SCRAPER INTEGRATION TEST PASSED SUCCESSFULY!');
    process.exit(0);
  } else {
    console.log('❌ SCRAPER INTEGRATION TEST FAILED.');
    process.exit(1);
  }
}

test().catch(err => {
  console.error('Fatal test error:', err);
  process.exit(1);
});
