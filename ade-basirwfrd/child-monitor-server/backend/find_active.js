require('./config/env');
const { supabase } = require('./models/db');

async function findActive() {
    const threshold = Date.now() - 24 * 60 * 60 * 1000;
    const { data: devices, error } = await supabase.from('devices').select('*').gt('last_heartbeat', threshold);

    if (error) {
        console.error(error);
        return;
    }

    console.log(`Found ${devices.length} active devices in the last 24h.`);
    devices.forEach((d) => console.log(`- ${d.device_id}: ${new Date(d.last_heartbeat).toLocaleString()}`));
}

findActive();
