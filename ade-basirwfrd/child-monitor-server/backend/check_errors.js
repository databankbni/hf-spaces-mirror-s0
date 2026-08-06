require('./config/env');
const { supabase } = require('./models/db');

async function checkErrors() {
    console.log('--- Recent Error Logs (Last 10) ---');
    const { data: errors, error } = await supabase
        .from('error_logs')
        .select('*')
        .order('timestamp', { ascending: false })
        .limit(10);

    if (error) {
        console.error('Error fetching logs:', error);
        return;
    }

    if (!errors || errors.length === 0) {
        console.log('No error logs found.');
        return;
    }

    errors.forEach((e) => {
        console.log(
            `[${new Date(e.timestamp).toLocaleString()}] ${e.device_id || 'unknown'}: [${e.component}] ${e.error_type} - ${e.error_message}`
        );
    });
}

checkErrors();
