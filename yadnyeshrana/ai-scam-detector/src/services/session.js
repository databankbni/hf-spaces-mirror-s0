const fs = require('fs');
const path = require('path');
const os = require('os');
const AdmZip = require('adm-zip');
const { getDatabase } = require('firebase-admin/database');

const sessionDir = path.resolve(process.cwd(), '.wwebjs_auth');
const tempBackupDir = path.join(os.tmpdir(), 'wwebjs_auth_backup');

/**
 * Safely copy a directory recursively, skipping lock files and ignoring missing files.
 */
function copyDirRecursive(src, dest) {
  if (!fs.existsSync(src)) return;
  
  fs.mkdirSync(dest, { recursive: true });
  
  const entries = fs.readdirSync(src, { withFileTypes: true });
  
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    
    // Skip lock, socket, and temporary Singleton files
    const isLockFile = entry.name.includes('LOCK') || 
                       entry.name.includes('Singleton') ||
                       entry.name.includes('lock') ||
                       entry.name.includes('Socket');
                       
    if (isLockFile) continue;
    
    if (entry.isDirectory()) {
      copyDirRecursive(srcPath, destPath);
    } else {
      try {
        fs.copyFileSync(srcPath, destPath);
      } catch (err) {
        // Ignore missing or locked files during copy (e.g. if deleted by Chrome mid-copy)
        console.log(`ℹ️ Skipping ephemeral file during copy: ${entry.name} (${err.message})`);
      }
    }
  }
}

/**
 * Safely delete a directory and all its contents recursively
 */
function deleteFolderRecursive(dirPath) {
  if (fs.existsSync(dirPath)) {
    fs.readdirSync(dirPath).forEach((file) => {
      const curPath = path.join(dirPath, file);
      if (fs.lstatSync(curPath).isDirectory()) {
        deleteFolderRecursive(curPath);
      } else {
        fs.unlinkSync(curPath);
      }
    });
    fs.rmdirSync(dirPath);
  }
}

/**
 * Clean up unnecessary temporary Chrome directories in the session folder
 * to keep the zip file size as small as possible.
 */
function cleanSessionCache() {
  const cachePaths = [
    path.join(sessionDir, 'session', 'Default', 'Cache'),
    path.join(sessionDir, 'session', 'Default', 'Code Cache'),
    path.join(sessionDir, 'session', 'Default', 'GPUCache'),
    path.join(sessionDir, 'session', 'Default', 'Service Worker'),
    path.join(sessionDir, 'session', 'Default', 'IndexedDB', 'https_web.whatsapp.com_0.indexeddb.blob'),
    path.join(sessionDir, 'session', 'Default', 'Blob_Storage'),
    path.join(sessionDir, 'session', 'Default', 'File System'),
  ];

  cachePaths.forEach(p => {
    try {
      if (fs.existsSync(p)) {
        deleteFolderRecursive(p);
        console.log(`🧹 Cleaned temporary folder: ${p}`);
      }
    } catch (err) {
      // Ignore cleanup errors for locked files
    }
  });
}

/**
 * Back up the local WhatsApp session folder to Firebase Realtime Database
 */
async function backupSession(retryCount = 0) {
  const useLocalDb = process.env.USE_LOCAL_DB === 'true' || !process.env.FIREBASE_DATABASE_URL;
  if (useLocalDb) {
    console.log('ℹ️ Running in Local DB mode. Skipping Firebase session backup.');
    return false;
  }

  if (!fs.existsSync(sessionDir)) {
    console.log('⚠️ Session folder .wwebjs_auth does not exist. Skipping backup.');
    return false;
  }

  if (retryCount === 0) {
    console.log('📦 Backing up WhatsApp session to Firebase...');
  }
  
  try {
    // 1. Clean cache folders to minimize size
    cleanSessionCache();

    // 2. Safely copy to a temp static directory to avoid race conditions with active Chrome process
    if (fs.existsSync(tempBackupDir)) {
      deleteFolderRecursive(tempBackupDir);
    }
    copyDirRecursive(sessionDir, tempBackupDir);

    // 3. Zip the temp static directory
    const zip = new AdmZip();
    zip.addLocalFolder(tempBackupDir, '');
    
    const buffer = zip.toBuffer();
    const base64 = buffer.toString('base64');
    
    // Clean up temp directory
    deleteFolderRecursive(tempBackupDir);
    
    const sizeKb = Math.round(buffer.length / 1024);
    console.log(`📦 Compressed session size: ${sizeKb} KB`);

    // 4. Split Base64 string into chunks of 5MB characters (approx 3.75MB of binary data)
    // to strictly stay under Firebase's 10MB node size limit.
    const CHUNK_SIZE = 5 * 1024 * 1024;
    const chunks = [];
    for (let i = 0; i < base64.length; i += CHUNK_SIZE) {
      chunks.push(base64.substring(i, i + CHUNK_SIZE));
    }

    console.log(`📦 Session split into ${chunks.length} chunks for Firebase upload.`);

    // 5. Upload to Firebase Database
    const db = getDatabase();
    
    // Clear previous chunks to prevent leftover stale chunks
    await db.ref('whatsapp_session/chunks').remove();
    
    // Write metadata
    await db.ref('whatsapp_session/meta').set({
      chunkCount: chunks.length,
      timestamp: new Date().toISOString()
    });
    
    // Upload chunks individually to bypass the 10MB single-write operation limit
    console.log(`📤 Uploading ${chunks.length} session chunks to Firebase...`);
    for (let i = 0; i < chunks.length; i++) {
      await db.ref(`whatsapp_session/chunks/${i}`).set(chunks[i]);
    }
    
    console.log('✅ WhatsApp session successfully backed up to Firebase!');
    return true;
  } catch (error) {
    if ((error.code === 'EBUSY' || error.message.includes('busy') || error.message.includes('locked')) && retryCount < 3) {
      console.log(`⚠️ Files locked by active Chrome session. Retrying backup in 5 seconds (Attempt ${retryCount + 1}/3)...`);
      await new Promise(resolve => setTimeout(resolve, 5000));
      return backupSession(retryCount + 1);
    }
    console.error('❌ Failed to backup WhatsApp session:', error.message);
    return false;
  }
}

/**
 * Restore the WhatsApp session folder from Firebase Realtime Database
 */
async function restoreSession() {
  const useLocalDb = process.env.USE_LOCAL_DB === 'true' || !process.env.FIREBASE_DATABASE_URL;
  if (useLocalDb) {
    console.log('ℹ️ Running in Local DB mode. Skipping Firebase session restore.');
    return false;
  }

  console.log('🚀 Checking Firebase for saved WhatsApp session...');

  try {
    const db = getDatabase();
    const snapshot = await db.ref('whatsapp_session').once('value');
    const sessionData = snapshot.val();

    if (!sessionData) {
      console.log('ℹ️ No saved WhatsApp session found in Firebase. A new QR code login will be required.');
      return false;
    }

    let base64 = '';
    
    if (typeof sessionData === 'string') {
      // Legacy support: if stored as a single string
      base64 = sessionData;
    } else if (sessionData.meta && sessionData.chunks) {
      // New chunked format with meta info
      console.log(`📥 Found chunked session data (${sessionData.meta.chunkCount} chunks). Restoring...`);
      const chunks = Array.isArray(sessionData.chunks) ? sessionData.chunks : Object.values(sessionData.chunks);
      base64 = chunks.join('');
    } else if (sessionData.chunks && Array.isArray(sessionData.chunks)) {
      // Intermediate chunked format
      console.log(`📥 Found chunked session data (${sessionData.chunks.length} chunks). Restoring...`);
      base64 = sessionData.chunks.join('');
    } else {
      console.log('⚠️ Saved WhatsApp session data format is invalid. Re-auth required.');
      return false;
    }

    console.log('📥 Restoring session files...');
    const buffer = Buffer.from(base64, 'base64');

    // Make sure clean slate
    if (fs.existsSync(sessionDir)) {
      deleteFolderRecursive(sessionDir);
    }

    // Extract
    fs.mkdirSync(sessionDir, { recursive: true });
    const zip = new AdmZip(buffer);
    zip.extractAllTo(sessionDir, true);

    console.log('✅ WhatsApp session successfully restored from Firebase!');
    return true;
  } catch (error) {
    console.error('❌ Failed to restore WhatsApp session:', error.message);
    return false;
  }
}

module.exports = {
  backupSession,
  restoreSession
};
