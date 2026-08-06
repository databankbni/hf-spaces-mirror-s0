require('dotenv').config();
const { initializeApp, cert } = require('firebase-admin');
const { getDatabase } = require('firebase-admin/database');
const fs = require('fs');
const path = require('path');

// Determine database mode
const useLocalDb = process.env.USE_LOCAL_DB === 'true' || !process.env.FIREBASE_DATABASE_URL;
const localDbFile = path.resolve(process.cwd(), process.env.LOCAL_DB_FILE || 'local_db.json');

async function main() {
  console.log('🧹 CLEANING INFLATED THREAT SYNC STATISTICS...');
  console.log('==================================================');

  if (useLocalDb) {
    console.log('📁 Mode: Local JSON File');
    if (!fs.existsSync(localDbFile)) {
      console.log('❌ Local DB file not found. Nothing to reset.');
      process.exit(1);
    }

    const data = fs.readFileSync(localDbFile, 'utf8');
    const db = JSON.parse(data);
    
    let resetCount = 0;
    if (db.scams && Array.isArray(db.scams)) {
      db.scams.forEach(scam => {
        if (scam.pattern.startsWith('Live threat intelligence') || scam.pattern.startsWith('Phishing domain')) {
          if (scam.examples !== 1) {
            scam.examples = 1;
            resetCount++;
          }
        }
      });
    }

    fs.writeFileSync(localDbFile, JSON.stringify(db, null, 2), 'utf8');
    console.log(`✅ Reset completed! Cleaned up stats for ${resetCount} scams in local DB.`);
    process.exit(0);

  } else {
    console.log('🔥 Mode: Firebase Realtime Database');
    try {
      let serviceAccount = null;
      const jsonEnv = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;

      if (jsonEnv) {
        if (jsonEnv.trim().startsWith('{')) {
          serviceAccount = JSON.parse(jsonEnv);
        } else {
          serviceAccount = require(path.resolve(process.cwd(), jsonEnv));
        }
      }

      const appConfig = {
        databaseURL: process.env.FIREBASE_DATABASE_URL
      };

      if (serviceAccount) {
        appConfig.credential = cert(serviceAccount);
      }

      initializeApp(appConfig);
      const db = getDatabase();

      console.log('📥 Fetching registered scams from Firebase...');
      const snapshot = await db.ref('scams').once('value');
      const allScams = snapshot.val();

      if (!allScams) {
        console.log('ℹ️ No scams found in database.');
        process.exit(0);
      }

      let resetCount = 0;
      const keys = Object.keys(allScams);
      
      console.log(`🔄 Scanning ${keys.length} records...`);
      for (const key of keys) {
        const scam = allScams[key];
        const isThreatSync = scam.pattern.startsWith('Live threat intelligence') || scam.pattern.startsWith('Phishing domain');
        
        if (isThreatSync && scam.examples !== 1) {
          await db.ref(`scams/${key}`).update({ examples: 1 });
          resetCount++;
        }
      }

      console.log(`✅ Reset completed! Cleaned up stats for ${resetCount} records in Firebase.`);
      process.exit(0);

    } catch (error) {
      console.error('❌ Failed to connect or reset Firebase stats:', error.message);
      process.exit(1);
    }
  }
}

main().catch(err => {
  console.error('Fatal execution error:', err);
  process.exit(1);
});
