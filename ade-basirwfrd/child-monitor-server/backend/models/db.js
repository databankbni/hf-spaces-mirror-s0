const { createClient } = require('@supabase/supabase-js');

const SUPABASE_URL = process.env.SUPABASE_URL;
/** Service role key (bukan anon). Alias: SUPABASE_SERVICE_KEY */
const SUPABASE_SERVICE_ROLE_KEY =
    process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_SERVICE_KEY;

if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error(
        '[DB] Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_KEY) in environment or backend/.env'
    );
}

const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

try {
    const host = new URL(SUPABASE_URL).host;
    console.log(`[DB] Supabase host=${host} (service role key length=${SUPABASE_SERVICE_ROLE_KEY.length})`);
} catch {
    console.log('[DB] Connected to Supabase (persistent cloud database)');
}

// ============================================================
// Helper functions (all async with Promises)
// ============================================================

// -- Devices --
async function upsertDevice({ deviceId, waNumber, fcmToken }) {
  const now = Date.now();
  const { data, error } = await supabase
    .from('devices')
    .upsert({
      device_id: deviceId,
      wa_number: waNumber,
      fcm_token: fcmToken || null,
      last_heartbeat: now,
      created_at: now
    }, { onConflict: 'device_id' })
    .select();

  if (error) throw error;
  return data;
}

async function getDeviceById(deviceId) {
  const { data, error } = await supabase
    .from('devices')
    .select('*')
    .eq('device_id', deviceId)
    .single();

  if (error && error.code !== 'PGRST116') throw error; // PGRST116 = not found
  return data || null;
}

async function getAllDevices() {
  const { data, error } = await supabase
    .from('devices')
    .select('*');

  if (error) throw error;
  return data || [];
}

async function updateHeartbeat(deviceId, health = {}) {
  const now = Date.now();
  const patch = { last_heartbeat: now };

  if (typeof health.isDeviceOwner === 'boolean') {
    patch.is_device_owner = health.isDeviceOwner;
  }
  if (typeof health.adminActive === 'boolean') {
    patch.admin_active = health.adminActive;
  }
  if (typeof health.serviceRunning === 'boolean') {
    patch.service_running = health.serviceRunning;
  }
  if (health.appVersion != null && String(health.appVersion).trim() !== '') {
    patch.app_version = String(health.appVersion).trim();
  }
  if (
    health.isDeviceOwner !== undefined ||
    health.adminActive !== undefined ||
    health.serviceRunning !== undefined ||
    health.appVersion
  ) {
    patch.last_health_at = now;
  }

  let { data, error } = await supabase
    .from('devices')
    .update(patch)
    .eq('device_id', deviceId);

  // Kolom health belum ada di Supabase → fallback heartbeat saja
  if (error && /column|schema|PGRST204/i.test(String(error.message || error.code || ''))) {
    console.warn('[DB] Health columns missing — heartbeat only. Run sql/devices_health_columns.sql');
    ({ data, error } = await supabase
      .from('devices')
      .update({ last_heartbeat: now })
      .eq('device_id', deviceId));
  }

  if (error) throw error;
  return data;
}

/** Hapus baris device (rapikan duplikat). */
async function deleteDevice(deviceId) {
  const { data, error } = await supabase
    .from('devices')
    .delete()
    .eq('device_id', deviceId);
  if (error) throw error;
  return data;
}

async function getStaleDevices(threshold) {
  const { data, error } = await supabase
    .from('devices')
    .select('*')
    .lt('last_heartbeat', threshold);

  if (error) throw error;
  return data || [];
}

// -- Logs --
async function insertLog({ deviceId, packageName, appName, url, timestamp, isJudi }) {
  const { data, error } = await supabase
    .from('logs')
    .insert({
      device_id: deviceId,
      package_name: packageName || '',
      app_name: appName || '',
      url: url || '',
      timestamp: timestamp || Date.now(),
      is_judi: isJudi ? 1 : 0
    });

  if (error) throw error;
  return data;
}

async function getLogsByDevice(deviceId, limit = 50) {
  const { data, error } = await supabase
    .from('logs')
    .select('*')
    .eq('device_id', deviceId)
    .order('timestamp', { ascending: false })
    .limit(limit);

  if (error) throw error;
  return data || [];
}

async function markLogSentWA(logId) {
  const { data, error } = await supabase
    .from('logs')
    .update({ sent_wa: 1 })
    .eq('id', logId);

  if (error) throw error;
  return data;
}

// -- Blocklist --
async function insertBlockedDomain(domain) {
  const { data, error } = await supabase
    .from('blocklist')
    .upsert({
      domain: domain,
      added_at: Date.now()
    }, { onConflict: 'domain', ignoreDuplicates: true });

  if (error && error.code !== '23505') throw error; // ignore unique violation
  return data;
}

async function getAllBlockedDomains() {
  const { data, error } = await supabase
    .from('blocklist')
    .select('domain');

  if (error) throw error;
  return (data || []).map(r => r.domain);
}

async function deleteBlockedDomain(domain) {
  const { data, error } = await supabase
    .from('blocklist')
    .delete()
    .eq('domain', domain.toLowerCase());

  if (error) throw error;
  return data;
}

/** Domain dewasa yang tidak boleh ada di blocklist anti-judol. */
const PORN_DOMAINS_PURGE = [
  'pornhub.com', 'www.pornhub.com', 'xvideos.com', 'www.xvideos.com',
  'xnxx.com', 'xhamster.com', 'redtube.com', 'youporn.com', 'spankbang.com',
  'bokep.com', 'bokepindo.com', 'pornhd.com', 'tube8.com', 'beeg.com',
];

// Seed initial blocklist (judol only) + buang entri bokep lama
async function seedBlocklist() {
  try {
    for (const bad of PORN_DOMAINS_PURGE) {
      try {
        await deleteBlockedDomain(bad.replace(/^www\./, ''));
        await deleteBlockedDomain(bad);
      } catch (_) { /* ignore */ }
    }
    const domains = require('../judi-domains.json');
    for (const domain of domains) {
      await insertBlockedDomain(domain);
    }
    console.log(`[DB] Seeded ${domains.length} judol domains; purged adult domains from blocklist`);
  } catch (err) {
    console.warn('[DB] Could not seed blocklist:', err.message);
  }
}

seedBlocklist();

// -- Error Logs --
async function insertErrorLog({ deviceId, errorType, errorMessage, stackTrace, component }) {
  const { data, error } = await supabase
    .from('error_logs')
    .insert({
      device_id: deviceId,
      error_type: errorType || 'UNKNOWN',
      error_message: errorMessage || '',
      stack_trace: stackTrace || '',
      component: component || '',
      timestamp: Date.now()
    });

  if (error) throw error;
  return data;
}

async function getErrorLogsByDevice(deviceId, limit = 50) {
  let query = supabase.from('error_logs').select('*');
  if (deviceId) {
    query = query.eq('device_id', deviceId);
  }
  const { data, error } = await query
    .order('timestamp', { ascending: false })
    .limit(limit);
  if (error) throw error;
  return data || [];
}

module.exports = {
  supabase,
  upsertDevice,
  getDeviceById,
  getAllDevices,
  updateHeartbeat,
  deleteDevice,
  getStaleDevices,
  insertLog,
  getLogsByDevice,
  markLogSentWA,
  insertBlockedDomain,
  getAllBlockedDomains,
  deleteBlockedDomain,
  insertErrorLog,
  getErrorLogsByDevice,
};
