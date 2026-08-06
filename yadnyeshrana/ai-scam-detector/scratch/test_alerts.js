require('dotenv').config();
const alertService = require('../src/services/alert');

async function main() {
  console.log('🔔 Testing Telegram Alert Configuration...');
  console.log('--------------------------------------------------');
  
  const token = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  
  console.log(`TELEGRAM_BOT_TOKEN: ${token ? 'Configured (starts with ' + token.substring(0, 5) + '...)' : 'MISSING'}`);
  console.log(`TELEGRAM_CHAT_ID: ${chatId ? 'Configured (' + chatId + ')' : 'MISSING'}`);
  console.log('--------------------------------------------------');

  if (!token || !chatId || token.includes('your_telegram') || chatId.includes('your_telegram')) {
    console.log('❌ Error: Telegram Bot Token or Chat ID is not configured in your .env file.');
    console.log('\n📖 HOW TO SET UP YOUR TELEGRAM ALERTS:');
    console.log('1. Open Telegram and search for "@BotFather".');
    console.log('2. Send "/newbot" to BotFather and follow instructions to create a new bot.');
    console.log('3. Copy the HTTP API token BotFather gives you. This is your TELEGRAM_BOT_TOKEN.');
    console.log('4. Search for "@userinfobot" on Telegram and message it. It will reply with your Chat ID. This is your TELEGRAM_CHAT_ID.');
    console.log('5. IMPORTANT: Click the start link for your new bot or search for its username and click "Start" / send "/start". Bots cannot message you first!');
    console.log('6. Add these keys to your local .env file.');
    process.exit(1);
  }

  console.log('📤 Sending test alert message to Telegram...');
  const success = await alertService.sendAlert(
    `🔔 <b>Test Alert System</b>\n\n` +
    `Hello! This is a test alert from your <b>AI Scam Detector Bot</b>.\n` +
    `Your Telegram notification channel is successfully configured and active! 🎉`
  );

  if (success) {
    console.log('\n✅ TEST ALERT SENT SUCCESSFULY! Check your Telegram chat.');
  } else {
    console.log('\n❌ FAILED TO SEND TEST ALERT. Please check the credentials and verify you have clicked "/start" in your bot chat.');
  }
}

main().catch(err => {
  console.error('Unhandled script error:', err);
});
