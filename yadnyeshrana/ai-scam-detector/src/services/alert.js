const token = process.env.TELEGRAM_BOT_TOKEN;
const chatId = process.env.TELEGRAM_CHAT_ID;

/**
 * Send an alert message to the configured Telegram chat.
 * @param {string} message The plain text or HTML message to send
 * @returns {Promise<boolean>} Resolves to true if successful, false otherwise
 */
async function sendAlert(message) {
  if (!token || !chatId || token === 'your_telegram_bot_token_here' || chatId === 'your_telegram_chat_id_here') {
    console.log('🔔 [Alert Skipped] Telegram Bot credentials not fully configured in env.');
    return false;
  }

  try {
    let url = `https://api.telegram.org/bot${token}/sendMessage`;
    const headers = {
      'Content-Type': 'application/json'
    };

    if (process.env.META_API_BASE_URL) {
      // Route through the Google Script proxy to bypass Hugging Face egress firewall blocking Telegram
      url = `${process.env.META_API_BASE_URL}?targetUrl=${encodeURIComponent(url)}&authToken=telegram`;
    }

    const response = await fetch(url, {
      method: 'POST',
      headers: headers,
      body: JSON.stringify({
        chat_id: chatId,
        text: message,
        parse_mode: 'HTML',
        disable_web_page_preview: true
      })
    });

    const data = await response.json();
    if (response.ok && data.ok) {
      console.log('🔔 Telegram alert sent successfully.');
      return true;
    } else {
      console.error('❌ Failed to send Telegram alert:', data.description || response.statusText);
      return false;
    }
  } catch (error) {
    console.error('❌ Error sending Telegram alert:', error.message);
    return false;
  }
}

module.exports = {
  sendAlert
};
