/**
 * Muat variabel dari backend/.env (lokal) sebelum modul lain membaca process.env.
 * Di Hugging Face / hosting, set variabel di panel; file .env tidak wajib ada.
 */
const path = require('path');

const envPath = path.join(__dirname, '..', '.env');
require('dotenv').config({ path: envPath });
// Fallback: jika cwd adalah backend/ (mis. script dari folder lain)
require('dotenv').config();

module.exports = {};
