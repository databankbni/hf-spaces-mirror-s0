require('dotenv').config();
const dbService = require('../src/services/db');

// List of common Indian scam indicators
const scamSeeds = [
  // ==================================================
  // CATEGORY 1: Utility / Electricity Bills (Disconnection Threat)
  // ==================================================
  {
    pattern: 'Electricity power will be suspended tonight at 9:30 PM',
    type: 'utility_bill_fraud',
    riskLevel: 'HIGH',
    keywords: ['electricity', 'suspended', 'disconnection', 'electricity officer', 'bill update'],
    urls: ['bill-pay-online.in', 'msedcl-bill-pay.com', 'bescom-utility-pay.org'],
    phoneNumbers: ['9887766554', '8887776665', '7776665554', '9123456789', '9555444333']
  },
  {
    pattern: 'Your electricity bill is pending, contact electricity officer immediately',
    type: 'utility_bill_fraud',
    riskLevel: 'HIGH',
    keywords: ['bill officer', 'pending bill', 'power cut', 'electricity office', 'electricity helpline'],
    urls: ['utility-bills-support.net', 'bescom-payment-desk.in'],
    phoneNumbers: ['9444333221', '8111222333', '7000111222']
  },

  // ==================================================
  // CATEGORY 2: Banking / KYC / PAN Card Clones
  // ==================================================
  {
    pattern: 'Your SBI YONO account has been blocked. Update PAN card immediately',
    type: 'banking_fraud',
    riskLevel: 'HIGH',
    keywords: ['sbi', 'yono', 'blocked', 'update pan', 'kyc pending', 'pan card updated'],
    urls: ['sbi-yono-kyc.in', 'yono-sbi-verification.com', 'sbi-pan-update.net', 'yono-verify-account.org', 'sbicard-kyc.com'],
    phoneNumbers: ['9876543210', '8876543210', '7876543210', '9001122334', '8001122334']
  },
  {
    pattern: 'HDFC Netbanking block warning. Update your KYC details to restore access',
    type: 'banking_fraud',
    riskLevel: 'HIGH',
    keywords: ['hdfc', 'netbanking', 'restore access', 'kyc update', 'hdfc card blocked'],
    urls: ['hdfc-netbanking-verify.in', 'hdfc-restore-account.com', 'hdfc-kyc-desk.net', 'hdfcbank-pan.org'],
    phoneNumbers: ['9998887776', '8889997776', '7778889996']
  },
  {
    pattern: 'ICICI Bank customer alert: PAN verification pending. Avoid service charges',
    type: 'banking_fraud',
    riskLevel: 'HIGH',
    keywords: ['icici', 'pan verification', 'service charges', 'icici account security'],
    urls: ['icici-pan-verify.in', 'icici-support-desk.com', 'icicibank-kyc.org'],
    phoneNumbers: ['9555111222', '8555111222', '7555111222']
  },
  {
    pattern: 'Paytm KYC suspended. Complete verification to activate wallet',
    type: 'banking_fraud',
    riskLevel: 'HIGH',
    keywords: ['paytm', 'wallet suspended', 'activate wallet', 'paytm kyc portal'],
    urls: ['paytm-kyc-verify.in', 'paytm-wallet-support.com', 'paytm-active.org'],
    phoneNumbers: ['9666222333', '8666222333', '7666222333']
  },

  // ==================================================
  // CATEGORY 3: KBC / Lottery Win Scams (Lucky Draw)
  // ==================================================
  {
    pattern: 'Congratulations! You have won ₹25 Lakhs in KBC Lucky Draw',
    type: 'lottery_fraud',
    riskLevel: 'HIGH',
    keywords: ['kbc', 'lottery winner', '25 lakhs', 'lucky draw', 'rana pratap singh', 'whatsapp lottery'],
    urls: ['kbc-lottery-winner.in', 'kbc-lucky-draw-desk.com', 'kbc-prize-claim.org'],
    phoneNumbers: ['9999000111', '8888000111', '7777000111', '919999222233', '918888333344']
  },

  // ==================================================
  // CATEGORY 4: Part-Time Job / Task scams (Prepaid Telegram Tasks)
  // ==================================================
  {
    pattern: 'Earn ₹3000-5000 daily by liking YouTube videos. Work from home',
    type: 'job_fraud',
    riskLevel: 'HIGH',
    keywords: ['part-time job', 'youtube like task', 'daily salary', 'work from home', 'telegram manager'],
    urls: ['parttime-job-apply.in', 'youtube-task-earn.com', 'home-tasks-india.org'],
    phoneNumbers: ['9222444666', '8222444666', '7222444666', '9333555777', '8333555777']
  },
  {
    pattern: 'Amazon part-time merchant agent position. Earn commission daily',
    type: 'job_fraud',
    riskLevel: 'HIGH',
    keywords: ['amazon agent', 'merchant commission', 'order rating tasks', 'prepaid task'],
    urls: ['amazon-agent-apply.in', 'merchant-task-verify.com'],
    phoneNumbers: ['9444666888', '8444666888', '7444666888']
  },

  // ==================================================
  // CATEGORY 5: Customs / Police Detained Parcel Fraud (FedEx/DHL)
  // ==================================================
  {
    pattern: 'Your FedEx parcel contains illegal drugs, Customs office has detained it',
    type: 'customs_fraud',
    riskLevel: 'HIGH',
    keywords: ['fedex parcel', 'illegal drugs', 'customs office', 'detained parcel', 'cbi arrest threat', 'delhi police drug case'],
    urls: ['customs-clearance-desk.in', 'fedex-parcel-status.com'],
    phoneNumbers: ['9666777888', '8666777888', '7666777888']
  },
  {
    pattern: 'DHL parcel detained by Narcotics Control Bureau. Call immediately',
    type: 'customs_fraud',
    riskLevel: 'HIGH',
    keywords: ['dhl parcel', 'narcotics bureau', 'ncb warning', 'illegal package'],
    urls: ['dhl-customs-verify.in', 'dhl-clearance-support.org'],
    phoneNumbers: ['9111333555', '8111333555', '7111333555']
  },

  // ==================================================
  // CATEGORY 6: Unofficial Instant Loan Apps Scams
  // ==================================================
  {
    pattern: 'Get instant loan up to ₹50,000 without document checks. Click here',
    type: 'loan_fraud',
    riskLevel: 'HIGH',
    keywords: ['instant loan', 'no document loan', 'quick cash approval', 'loan app link'],
    urls: ['instant-loan-cash.in', 'quick-cash-loan.com', 'rupee-credit-desk.org'],
    phoneNumbers: ['9777555333', '8777555333', '7777555333']
  },

  // ==================================================
  // CATEGORY 7: Urgent Family Distress / UPI Extortion
  // ==================================================
  {
    pattern: 'Dad, my phone is lost, please transfer ₹5000 to this UPI ID urgently',
    type: 'family_distress',
    riskLevel: 'HIGH',
    keywords: ['phone lost', 'lost mobile', 'upi transfer urgent', 'accident hospital cash', 'mummy transfer money'],
    urls: [],
    phoneNumbers: ['9000888999', '8000888999', '7000888999']
  }
];

// Curated list of Indian banking Phishing Domain extensions
const phishingDomainSeeds = [
  'yono-sbi-card.in', 'sbi-card-kyc.net', 'yono-sbi-login.org', 'sbionline-pan.in',
  'hdfcbank-netbanking.net.in', 'hdfcbank-pan-update.com', 'hdfc-kyc-verify.co.in',
  'icicibank-pan-card.com', 'icicibank-yono.in', 'icici-card-active.org',
  'axis-bank-verify.in', 'axisbank-kyc-update.com', 'axiscard-verification.net',
  'kotak-pan-verify.in', 'kotak-yono-update.com', 'kotakcard-kyc.org',
  'airtelbank-kyc.in', 'airtel-payment-verify.com',
  'gpay- कैशबैक-offers.in', 'paytm-cashback-scratch.in', 'scratch-card-win.in',
  'task-earning-youtube.in', 'parttime-telegram-job.co.in', 'earn-daily-tasks.in'
];

async function seed() {
  console.log('🌱 Starting Scam Database Seeder...');
  console.log('==================================================');
  
  const isLocal = process.env.USE_LOCAL_DB === 'true' || !process.env.FIREBASE_DATABASE_URL;
  console.log(`📁 Target Database Mode: ${isLocal ? 'Local JSON File' : 'Firebase Realtime DB'}`);
  console.log('--------------------------------------------------');

  let successCount = 0;
  
  // 1. Upload Curated Scams
  console.log('📤 Uploading Curated Scam Patterns...');
  for (const scam of scamSeeds) {
    try {
      await dbService.addKnownScam(scam);
      successCount++;
    } catch (err) {
      console.error(`❌ Failed to add scam pattern: "${scam.pattern}" (${err.message})`);
    }
  }

  // 2. Upload Phishing Domains
  console.log('📤 Uploading Phishing Domains Blacklist...');
  for (const domain of phishingDomainSeeds) {
    try {
      await dbService.addKnownScam({
        pattern: `Phishing domain blacklist link: ${domain}`,
        type: 'banking_fraud',
        riskLevel: 'HIGH',
        keywords: [domain.split('.')[0]],
        urls: [domain],
        phoneNumbers: []
      });
      successCount++;
    } catch (err) {
      console.error(`❌ Failed to add phishing domain: "${domain}" (${err.message})`);
    }
  }

  console.log('==================================================');
  console.log(`✅ DATABASE SEEDING COMPLETED SUCCESSFULY!`);
  console.log(`🎉 Successfully registered ${successCount} total scam indicators.`);
  console.log('==================================================');
  process.exit(0);
}

seed().catch(err => {
  console.error('Fatal seeder error:', err);
  process.exit(1);
});
