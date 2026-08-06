require('./config/env');
const { supabase } = require('./models/db');
const fcm = require('./services/fcm');

async function wakeUpIrfan() {
    console.log('--- Remote Wake-up Sequence ---');

    const { data: devices, error } = await supabase.from('devices').select('*').ilike('device_id', '%Irfan%');

    if (error) {
        console.error('Database error:', error);
        return;
    }

    if (!devices || devices.length === 0) {
        console.error('Device "Irfan" not found in database.');
        const { data: all } = await supabase.from('devices').select('device_id');
        console.log('Available devices:', all);
        return;
    }

    const device = devices[0];
    console.log(
        `Found device: ${device.device_id}, Status: ${Date.now() - device.last_heartbeat > 24 * 60 * 60 * 1000 ? 'OFFLINE' : 'ONLINE'}`
    );

    if (!device.fcm_token) {
        console.error('Device has no FCM token. Cannot send remote command.');
        return;
    }

    console.log(`Sending RESTART command to ${device.device_id}...`);
    const success = await fcm.sendRestartCommand(device.device_id);

    if (success) {
        console.log('✅ RESTART command sent successfully via FCM.');
        console.log('The device should reconnect within a few minutes if Firebase is alive.');
    } else {
        console.error('❌ Failed to send FCM command.');
    }
}

wakeUpIrfan();
