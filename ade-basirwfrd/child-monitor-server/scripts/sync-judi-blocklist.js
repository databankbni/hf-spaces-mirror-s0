#!/usr/bin/env node
/**
 * Sinkronkan backend/judi-domains.json ke Supabase + hapus domain bokep.
 * Usage: node scripts/sync-judi-blocklist.js
 * Membutuhkan SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY di backend/.env
 */
const path = require('path');
require(path.join(__dirname, '..', 'backend', 'config', 'env'));

const domains = require(path.join(__dirname, '..', 'backend', 'judi-domains.json'));
const { insertBlockedDomain, deleteBlockedDomain, getAllBlockedDomains } = require(
  path.join(__dirname, '..', 'backend', 'models', 'db')
);

const PORN = [
  'pornhub.com', 'xvideos.com', 'xnxx.com', 'xhamster.com', 'redtube.com',
  'youporn.com', 'spankbang.com', 'bokep.com', 'bokepindo.com', 'beeg.com',
  'tube8.com', 'pornhd.com',
];

(async () => {
  console.log(`Seeding ${domains.length} judol domains...`);
  for (const d of PORN) {
    try {
      await deleteBlockedDomain(d);
      console.log('  purged', d);
    } catch (e) {
      console.warn('  purge skip', d, e.message);
    }
  }
  for (const d of domains) {
    await insertBlockedDomain(d);
  }
  const all = await getAllBlockedDomains();
  const leftoverPorn = all.filter((x) =>
    /porn|xxx|xvideo|xnxx|bokep|redtube|xhamster|youporn|spankbang|beeg/i.test(x)
  );
  console.log(`Done. blocklist size=${all.length}. leftover adult=${leftoverPorn.length}`);
  if (leftoverPorn.length) console.log(leftoverPorn);
  process.exit(0);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
