const crypto = require('crypto');

const ALGORITHM = 'aes-256-cbc';
// Derive a 32-byte key from the environment variable (or a default fallback for local dev)
const SECRET = process.env.ENCRYPTION_KEY || 'default_sec_key_ai_scam_detector_2026';
const KEY = crypto.scryptSync(SECRET, 'scam_salt', 32);

/**
 * Normalize a phone number to digits-only format starting with the country code.
 * Automatically prepends '91' for 10-digit Indian numbers and strips leading zeroes or '00' prefixes.
 */
function normalizePhone(phone) {
  if (!phone) return '';
  let cleaned = phone.replace(/\D/g, '');
  if (cleaned.startsWith('00')) {
    cleaned = cleaned.substring(2);
  }
  if (cleaned.startsWith('0')) {
    cleaned = cleaned.substring(1);
  }
  if (cleaned.length === 10) {
    cleaned = '91' + cleaned;
  }
  return cleaned;
}

/**
 * Hash a phone number using SHA-256 to ensure absolute anonymity.
 * Hashed numbers are used as keys in the database instead of plain text numbers.
 */
function hashPhone(phoneNumber) {
  if (!phoneNumber) return 'anonymous';
  const cleanNumber = normalizePhone(phoneNumber);
  return crypto.createHash('sha256').update(cleanNumber).digest('hex');
}


/**
 * Encrypt a text message using AES-256-CBC
 */
function encryptMessage(text) {
  if (!text) return '';
  try {
    const iv = crypto.randomBytes(16);
    const cipher = crypto.createCipheriv(ALGORITHM, KEY, iv);
    
    let encrypted = cipher.update(text, 'utf8', 'hex');
    encrypted += cipher.final('hex');
    
    // Prefix the initialization vector so it can be used during decryption
    return iv.toString('hex') + ':' + encrypted;
  } catch (error) {
    console.error('Encryption failed:', error.message);
    return text; // Fallback to raw text in case of fatal error
  }
}

/**
 * Decrypt a text message.
 * Supports fallback to raw text if the message was not encrypted.
 */
function decryptMessage(encryptedText) {
  if (!encryptedText) return '';
  if (!encryptedText.includes(':')) {
    // Legacy support: if the stored string doesn't have an IV separator, treat it as unencrypted
    return encryptedText;
  }

  try {
    const parts = encryptedText.split(':');
    const iv = Buffer.from(parts.shift(), 'hex');
    const encrypted = Buffer.from(parts.join(':'), 'hex');
    
    const decipher = crypto.createDecipheriv(ALGORITHM, KEY, iv);
    
    let decrypted = decipher.update(encrypted, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    
    return decrypted;
  } catch (error) {
    // If decryption fails (e.g. key changed), return the ciphertext rather than crashing
    return encryptedText;
  }
}

module.exports = {
  hashPhone,
  encryptMessage,
  decryptMessage,
  normalizePhone
};
