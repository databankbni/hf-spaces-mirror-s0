const dbService = require('./db');

/**
 * Fetch active phishing URLs from OpenPhish community feed
 * and sync them into the database blacklist.
 * @returns {Promise<{success: boolean, syncedCount: number, error: string|null}>}
 */
async function syncPhishingFeeds() {
  console.log('📡 Starting threat intelligence feed synchronization...');
  
  try {
    // OpenPhish community feed is updated every 12 hours and contains raw URLs of active scams
    const feedUrl = 'https://openphish.com/feed.txt';
    const response = await fetch(feedUrl, { signal: AbortSignal.timeout(10000) }); // 10 second timeout

    if (!response.ok) {
      throw new Error(`Failed to fetch threat feed: ${response.status} ${response.statusText}`);
    }

    const rawText = await response.text();
    const urls = rawText.split('\n')
      .map(line => line.trim())
      .filter(line => line && line.startsWith('http'));

    console.log(`📡 Loaded ${urls.length} active phishing links from OpenPhish.`);
    
    // Slice to the top 40 most recent URLs to avoid exceeding write capacities
    const recentUrls = urls.slice(0, 40);
    const scamDataArray = [];

    for (const url of recentUrls) {
      try {
        let domain = '';
        try {
          domain = new URL(url).hostname;
        } catch (e) {
          // Fallback simple parsing if URL parsing fails
          domain = url.split('/')[2] || url;
        }

        if (!domain) continue;

        scamDataArray.push({
          pattern: `Live threat intelligence block list: ${domain}`,
          type: 'banking_fraud',
          riskLevel: 'HIGH',
          keywords: [domain.split('.')[0]],
          urls: [domain, url],
          phoneNumbers: []
        });
      } catch (err) {
        console.error(`⚠️ Failed to parse synced URL: ${url} (${err.message})`);
      }
    }

    // Perform a single batch database transaction write
    const syncedRecords = await dbService.addKnownScamsBatch(scamDataArray);
    const newSyncCount = syncedRecords.length;

    console.log(`✅ Threat synchronization complete. Synced ${newSyncCount} records.`);
    return {
      success: true,
      syncedCount: newSyncCount,
      error: null
    };

  } catch (error) {
    console.error('❌ Threat intelligence sync failed:', error.message);
    return {
      success: false,
      syncedCount: 0,
      error: error.message
    };
  }
}

module.exports = {
  syncPhishingFeeds
};
