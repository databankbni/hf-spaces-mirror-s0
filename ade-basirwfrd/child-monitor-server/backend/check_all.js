require('./config/env');
const { supabase } = require('./models/db');

async function checkAll() {
    console.log('--- Database Health Check ---');

    const { data: devices } = await supabase.from('devices').select('*');
    console.log('Devices found:', devices ? devices.length : 0);
    (devices || []).forEach((d) => {
        const minutes = Math.floor((Date.now() - d.last_heartbeat) / 60000);
        console.log(`- ID: ${d.device_id}, Last Seen: ${minutes} min ago, Token: ${d.fcm_token ? 'YES' : 'NO'}`);
    });

    console.log('\n--- Recent Logs (Last 5) ---');
    const { data: logs } = await supabase.from('logs').select('*').order('timestamp', { ascending: false }).limit(5);
    (logs || []).forEach((l) => {
        console.log(`[${new Date(l.timestamp).toLocaleString()}] ${l.device_id}: ${l.app_name} ${l.url}`);
    });
}

checkAll();
