const axios = require('axios');
const { normalizePhone } = require('./security');

const META_ACCESS_TOKEN = process.env.META_ACCESS_TOKEN;
const PHONE_NUMBER_ID = process.env.PHONE_NUMBER_ID;

const crypto = require('crypto');
const https = require('https');
const agent = new https.Agent({
  keepAlive: true,
  rejectUnauthorized: false,
  secureOptions: crypto.constants.SSL_OP_LEGACY_SERVER_CONNECT,
  ciphers: 'DEFAULT:@SECLEVEL=0'
});

const META_API_BASE_URL = process.env.META_API_BASE_URL;

/**
 * Initialize WhatsApp service (no-op since we use webhooks now)
 */
async function initialize() {
  console.log('⚡ Meta WhatsApp Cloud API Service Initialized.');
  return true;
}

/**
 * Send WhatsApp message using Meta Cloud API (supports Cloudflare Proxy)
 */
async function sendMessage(phoneNumber, text, replyToMessageId = null) {
  if (!META_ACCESS_TOKEN || !PHONE_NUMBER_ID) {
    console.log(`\n==================================================`);
    console.log(`📣 [MOCK WHATSAPP OUTBOUND (Meta)]`);
    console.log(`Recipient: ${phoneNumber}`);
    if (replyToMessageId) {
      console.log(`Reply to Message ID: ${replyToMessageId}`);
    }
    console.log(`Message:\n${text}`);
    console.log(`==================================================\n`);
    return true;
  }

  try {
    const cleanPhone = normalizePhone(phoneNumber);
    const targetUrl = `https://graph.facebook.com/v18.0/${PHONE_NUMBER_ID}/messages`;
    
    // Route through Google Script/Proxy using query parameters
    let requestUrl = targetUrl;
    const headers = {
      'Content-Type': 'application/json'
    };
    if (META_API_BASE_URL) {
      requestUrl = `${META_API_BASE_URL}?targetUrl=${encodeURIComponent(targetUrl)}&authToken=${encodeURIComponent(META_ACCESS_TOKEN)}`;
    } else {
      headers['Authorization'] = `Bearer ${META_ACCESS_TOKEN}`;
    }

    const payload = {
      messaging_product: 'whatsapp',
      recipient_type: 'individual',
      to: cleanPhone,
      type: 'text',
      text: { body: text }
    };

    if (replyToMessageId) {
      payload.context = {
        message_id: replyToMessageId
      };
    }

    const response = await axios.post(
      requestUrl,
      payload,
      {
        headers: headers,
        httpsAgent: agent
      }
    );

    // Parse for Meta API errors inside 200 OK responses (e.g. from the Google Apps Script proxy)
    if (response.data && response.data.error) {
      const fbError = response.data.error;
      console.error(`❌ Meta API returned error payload:`, JSON.stringify(fbError));
      if (fbError.code === 190 || fbError.type === 'OAuthException') {
        triggerTokenExpiryAlert(fbError.message || 'OAuthException');
      }
      return false;
    }

    console.log(`📤 Successfully sent WhatsApp message to +${cleanPhone}`);
    console.log(`Response payload: ${JSON.stringify(response.data)}`);
    return true;
  } catch (error) {
    const errData = error.response ? error.response.data : null;
    const errMsg = error.message;
    console.error(`❌ Failed to send WhatsApp message to +${phoneNumber}:`, JSON.stringify(errData || errMsg));
    
    // Parse for Meta API errors inside axios exceptions
    if (errData && errData.error) {
      const fbError = errData.error;
      if (fbError.code === 190 || fbError.type === 'OAuthException') {
        triggerTokenExpiryAlert(fbError.message || 'OAuthException');
      }
    } else if (errMsg && (errMsg.includes('190') || errMsg.includes('OAuthException'))) {
      triggerTokenExpiryAlert(errMsg);
    }
    return false;
  }
}

// Rate-limited tracker to avoid spamming the admin with alerts
let lastTokenAlertTime = 0;

function triggerTokenExpiryAlert(errorMessage) {
  const now = Date.now();
  const TEN_MINUTES = 10 * 60 * 1000;
  if (now - lastTokenAlertTime < TEN_MINUTES) {
    return; // Rate limit alerts to once every 10 minutes
  }
  lastTokenAlertTime = now;

  console.error('🚨 WhatsApp Meta Access Token has expired or is invalid! Dispatching Telegram Admin Alert.');
  const alertService = require('./alert');
  alertService.sendAlert(
    `🚨 <b>CRITICAL: WhatsApp Token Expired</b>\n\n` +
    `Outbound Meta WhatsApp Cloud API calls are failing with an Authentication Error.\n\n` +
    `• <b>Error Message:</b> <code>${errorMessage}</code>\n` +
    `• <b>Meta Error Code:</b> <code>190 (OAuthException)</code>\n\n` +
    `👉 <b>Action Required:</b> Please login to the Meta Developer Dashboard, generate a permanent System User Token, and update the <code>META_ACCESS_TOKEN</code> secret in your Hugging Face Space settings!`
  ).catch(err => console.error('Failed to send token expiry alert:', err.message));
}

/**
 * Send a Meta WhatsApp template message
 */
async function sendTemplateMessage(phoneNumber, templateName, languageCode = 'en', parameters = []) {
  const cleanPhone = normalizePhone(phoneNumber);
  if (!cleanPhone) return false;

  const targetUrl = `${META_API_BASE_URL || 'https://graph.facebook.com/v19.0'}/${PHONE_NUMBER_ID}/messages`;
  let requestUrl = targetUrl;
  const headers = { 'Content-Type': 'application/json' };

  if (META_API_BASE_URL) {
    requestUrl = `${META_API_BASE_URL}?targetUrl=${encodeURIComponent(targetUrl)}&authToken=${encodeURIComponent(META_ACCESS_TOKEN)}`;
  } else {
    headers['Authorization'] = `Bearer ${META_ACCESS_TOKEN}`;
  }

  const payload = {
    messaging_product: 'whatsapp',
    recipient_type: 'individual',
    to: cleanPhone,
    type: 'template',
    template: {
      name: templateName,
      language: {
        code: languageCode
      }
    }
  };

  if (parameters && parameters.length > 0) {
    payload.template.components = [
      {
        "type": "body",
        "parameters": parameters.map(p => ({
          "type": "text",
          "text": p
        }))
      }
    ];
  }

  try {
    const response = await axios.post(requestUrl, payload, { headers, httpsAgent: agent });
    
    // Parse for Meta API errors inside 200 OK responses
    if (response.data && response.data.error) {
      console.error(`❌ Meta Template API returned error payload:`, JSON.stringify(response.data.error));
      return false;
    }

    console.log(`📤 Successfully sent WhatsApp template [${templateName}] to +${cleanPhone}`);
    return true;
  } catch (error) {
    const errData = error.response ? error.response.data : error.message;
    console.error(`❌ Failed to send WhatsApp template [${templateName}] to +${phoneNumber}:`, JSON.stringify(errData));
    return false;
  }
}

module.exports = {
  initialize,
  getLatestQr: () => null,
  isReady: () => true,
  sendMessage,
  sendTemplateMessage
};
