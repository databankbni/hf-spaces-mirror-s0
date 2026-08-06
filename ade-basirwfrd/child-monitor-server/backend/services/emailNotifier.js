/**
 * Email lewat Brevo API. Membutuhkan fetch global (Node.js 18+).
 * Set BREVO_API_KEY dan EMAIL_ALERT_TO di environment atau backend/.env
 */

function getBrevoSettings() {
    const apiKey = process.env.BREVO_API_KEY;
    const alertTo = process.env.EMAIL_ALERT_TO || process.env.ALERT_TARGET_EMAIL || '';
    const senderEmail =
        process.env.BREVO_SENDER_EMAIL || process.env.EMAIL_ALERT_TO || process.env.ALERT_TARGET_EMAIL || '';
    const senderName = process.env.BREVO_SENDER_NAME || 'Child Monitor Alert';
    return { apiKey, alertTo, senderEmail, senderName };
}

/**
 * Normalisasi tipe aktivitas untuk template email.
 * Hanya string yang dikenal; boolean/angka tidak boleh jatuh ke cabang "blokir".
 * @param {string|boolean|undefined|null} blockType
 * @returns {'none'|'judi'|'manual'|'vpn'}
 */
function normalizeActivityType(blockType) {
    if (blockType === false || blockType === true || blockType == null) {
        return 'none';
    }
    if (typeof blockType !== 'string') {
        return 'none';
    }
    const t = blockType.trim().toLowerCase();
    if (t === 'none' || t === 'judi' || t === 'manual' || t === 'vpn') {
        return t;
    }
    return 'none';
}

async function sendEmailAlert(subject, htmlContent) {
    const { apiKey, alertTo, senderEmail, senderName } = getBrevoSettings();
    if (!apiKey) {
        console.error('[Email] BREVO_API_KEY tidak di-set; email tidak dikirim.');
        return false;
    }
    if (!alertTo) {
        console.error('[Email] EMAIL_ALERT_TO (atau ALERT_TARGET_EMAIL) tidak di-set; email tidak dikirim.');
        return false;
    }
    if (!senderEmail) {
        console.error('[Email] Set BREVO_SENDER_EMAIL atau EMAIL_ALERT_TO untuk alamat pengirim Brevo.');
        return false;
    }

    try {
        const response = await fetch('https://api.brevo.com/v3/smtp/email', {
            method: 'POST',
            headers: {
                'api-key': apiKey,
                'Content-Type': 'application/json',
                accept: 'application/json',
            },
            body: JSON.stringify({
                sender: { name: senderName, email: senderEmail },
                to: [{ email: alertTo }],
                subject: subject,
                htmlContent: htmlContent,
            }),
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Brevo API error: ${response.status} ${errorText}`);
        }

        console.log(`[Email] Alert sent to ${alertTo}: ${subject}`);
        return true;
    } catch (error) {
        console.error('[Email] Failed to send email:', error.message);
        return false;
    }
}

/**
 * @param {string} _emailAddress - Dipertahankan untuk kompatibilitas API; penerima dari EMAIL_ALERT_TO.
 * @param {object} logData
 * @param {string|boolean} blockType - 'none' | 'judi' | 'manual' | 'vpn' (bukan boolean)
 */
async function sendLogToEmail(_emailAddress, logData, blockType = 'none') {
    const activity = normalizeActivityType(blockType);
    const dateStr = new Date(logData.timestamp).toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' });
    let subject = '';
    let htmlContent = '';

    if (activity === 'judi' || activity === 'manual') {
        subject = `🚨 PERINGATAN BLOKIR: Aktivitas Dilarang (${activity})`;
        htmlContent = `
            <h2>⚠️ Peringatan Blokir: ${activity}</h2>
            <p>Sistem mendeteksi aktivitas yang dilarang pada perangkat anak Anda.</p>
            <ul>
                <li><strong>Waktu:</strong> ${dateStr}</li>
                <li><strong>Aplikasi:</strong> ${logData.appName} (${logData.packageName})</li>
                <li><strong>URL/Domain:</strong> ${logData.url || 'N/A'}</li>
                <li><strong>Alasan Blokir:</strong> ${activity}</li>
            </ul>
            <p style="color:red;">Layar anak telah dikunci sementara.</p>
        `;
    } else if (activity === 'vpn') {
        subject = `⚠️ VPN aktif di perangkat anak`;
        htmlContent = `
            <h2>⚠️ VPN terdeteksi</h2>
            <p>Anak menggunakan VPN. Pemantauan atau pemblokiran jaringan mungkin terbatas.</p>
            <ul>
                <li><strong>Waktu:</strong> ${dateStr}</li>
                <li><strong>Keterangan:</strong> ${logData.appName || ''}</li>
                <li><strong>Perangkat:</strong> ${logData.deviceId || 'N/A'}</li>
            </ul>
        `;
    } else {
        subject = `ℹ️ Info Aktivitas Web`;
        htmlContent = `
            <h2>ℹ️ Informasi Aktivitas Web</h2>
            <p>Aktivitas web baru terdeteksi pada perangkat anak Anda.</p>
            <ul>
                <li><strong>Waktu:</strong> ${dateStr}</li>
                <li><strong>Aplikasi:</strong> ${logData.appName} (${logData.packageName})</li>
                <li><strong>URL/Domain:</strong> ${logData.url || 'N/A'}</li>
            </ul>
        `;
    }

    return await sendEmailAlert(subject, htmlContent);
}

async function sendServiceDisabledAlert(_emailAddress, deviceId, serviceName) {
    const subject = `⚠️ PERINGATAN KRITIS: Layanan Dimatikan`;
    const htmlContent = `
        <div style="border-left: 5px solid red; padding-left: 10px;">
            <h2 style="color:red;">⚠️ Peringatan Kritis</h2>
            <p>Anak Anda telah <strong>mematikan</strong> layanan penting di perangkatnya.</p>
            <ul>
                <li><strong>Layanan:</strong> ${serviceName}</li>
                <li><strong>Waktu:</strong> ${new Date().toLocaleString('id-ID', { timeZone: 'Asia/Jakarta' })}</li>
            </ul>
            <p>Pemantauan mungkin terhenti. Segera periksa perangkat anak Anda.</p>
        </div>
    `;
    return await sendEmailAlert(subject, htmlContent);
}

module.exports = {
    sendLogToEmail,
    sendServiceDisabledAlert,
    sendEmailAlert,
    normalizeActivityType,
};

Object.defineProperty(module.exports, 'TARGET_EMAIL', {
    enumerable: true,
    configurable: true,
    get() {
        return process.env.EMAIL_ALERT_TO || process.env.ALERT_TARGET_EMAIL || '';
    },
});
