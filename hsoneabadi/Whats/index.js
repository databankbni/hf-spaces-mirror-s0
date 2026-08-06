process.on('unhandledRejection', (err) => {
  if (err === 'auth timeout' || (err && err.message === 'auth timeout')) return;
  if (err && err.message && err.message.includes('Execution context was destroyed')) return;
  console.error('Unhandled Rejection:', err);
});

const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const qrcodeTerminal = require('qrcode-terminal');
const MTProto = require('@mtproto/core');
const fs = require('fs');
const express = require('express');
const path = require('path');
const { generateInvoiceImage } = require('./invoice');

let DATA_DIR = '/data';
try {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
} catch { DATA_DIR = '.'; }
const API_ID = parseInt(process.env.API_ID, 10);
const API_HASH = process.env.API_HASH;
const BOT_TOKEN = process.env.BOT_TOKEN;
const MISTRAL_API_KEYS = [process.env.MISTRAL_API_KEY, process.env.MISTRAL_API_KEY_2].filter(Boolean);
let mistralKeyIndex = 0;

if (!API_ID || !API_HASH || !BOT_TOKEN || MISTRAL_API_KEYS.length === 0) {
  console.error('❌ متغيرات البيئة المطلوبة: API_ID, API_HASH, BOT_TOKEN, MISTRAL_API_KEY');
  process.exit(1);
}

const app = express();
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST');
  res.setHeader('Access-Control-Allow-Headers', '*');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
});
app.use(express.static('.'));
app.use(express.urlencoded({ extended: true }));
app.get('/ping', (req, res) => res.sendStatus(200));
app.get('/', (req, res) => {
  const qrPath = path.join(__dirname, 'whatsapp-qr.png');
  const qrHtml = fs.existsSync(qrPath)
    ? `<div class="qr"><img src="/whatsapp-qr.png" alt="QR Code"/></div><p class="status waiting">امسح رمز QR باستخدام واتساب</p>`
    : `<p class="status waiting loading">في انتظار رمز QR...</p>`;
  const chatId = telegramChatId || 'غير معروف';
  res.send(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>WhatsApp Bot</title><style>
body{font-family:sans-serif;text-align:center;padding:20px;background:#f5f5f5;max-width:500px;margin:auto}
h1{color:#075e54}.qr{background:#fff;padding:20px;border-radius:12px;display:inline-block;box-shadow:0 2px 8px rgba(0,0,0,0.1)}
img{max-width:300px;height:auto}.status{color:#666;margin-top:20px}.check{color:#4caf50}.waiting{color:#ff9800}
.loading{animation:pulse 1.5s infinite}@keyframes pulse{50%{opacity:0.5}}
.card{background:#fff;border-radius:12px;padding:15px;margin:15px 0;box-shadow:0 2px 8px rgba(0,0,0,0.1);text-align:left}
input,button{width:100%;padding:10px;margin:5px 0;border:1px solid #ddd;border-radius:8px;box-sizing:border-box;font-size:16px}
button{background:#075e54;color:#fff;border:none;cursor:pointer}
button:hover{background:#0a7a6e}
</style></head><body>
<h1>WhatsApp Bot</h1>
${qrHtml}
<p class="check">✅ البوت يعمل</p>
<div class="card"><b>Telegram Chat ID:</b> <span id="cid">${chatId}</span></div>
<form method="POST" action="/setchat">
<div class="card"><b>🔧 تعيين Chat ID يدوي:</b><br>
<input type="text" name="chatId" placeholder="أدخل معرف المحادثة" value="${telegramChatId || ''}"/>
<input type="text" name="accessHash" placeholder="access_hash (اختياري)" value="${telegramAccessHash || ''}"/>
<button type="submit">حفظ</button></div>
</form></body></html>`);
});
app.post('/setchat', (req, res) => {
  const cid = parseInt(req.body?.chatId, 10);
  if (cid) { telegramChatId = cid; telegramAccessHash = req.body?.accessHash || null; saveState(); }
  res.redirect('/');
});
app.listen(7860, () => console.log('Health check server on port 7860'));

const STATE_FILE = `${DATA_DIR}/state.json`;
const ORDERS_FILE = `${DATA_DIR}/orders.json`;
let state = { telegramChatId: null, botEnabled: true, telegramAccessHash: null, excludedNumbers: [] };
try { state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); } catch {}
let telegramChatId = state.telegramChatId || (process.env.DEFAULT_CHAT_ID ? parseInt(process.env.DEFAULT_CHAT_ID, 10) : null);
let telegramAccessHash = state.telegramAccessHash;
let botEnabled = state.botEnabled;
let forceOpen = state.forceOpen || false;
let excludedNumbers = state.excludedNumbers || [];
let whatsappConnected = false;
const START_TIME = Date.now();
const processedMsgIds = new Set();
let orderCounter = 0;
const pendingOrders = new Map();
const pendingConfirmations = new Map();
const pendingAdditions = new Map();
let awaitingAdminAdd = null;
let awaitingExcludeAdd = null;
function getProducts(info) {
  if (!info) return [];
  return info.products && info.products.length > 0 ? info.products :
    info.product ? [{ product: info.product, quantity: info.quantity || 0 }] : [];
}
function formatProductsList(products) {
  return products.map(p => `• ${p.product} x${p.quantity}`).join('\n');
}
let admins = [];
let orders = [];
try { const s = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); admins = s.admins || []; } catch {}
try { orders = JSON.parse(fs.readFileSync(ORDERS_FILE, 'utf8')); } catch {}
function saveState() {
  try { fs.writeFileSync(STATE_FILE, JSON.stringify({ telegramChatId, botEnabled, forceOpen, telegramAccessHash, excludedNumbers, admins })); } catch {}
}
function isAdmin(userId) {
  return String(userId) === String(telegramChatId) || admins.includes(String(userId));
}
function sendReport(userId) {
  if (orders.length === 0) { tgSend(userId, '📭 لا توجد طلبات بعد'); return; }
  const now = new Date();
  const d = now.toLocaleString('en-US', { hour12: true, hour: '2-digit', minute: '2-digit', second: '2-digit', day: 'numeric', month: 'numeric', year: 'numeric' });
  let report = `📊 تقرير الطلبات\n📅 ${d}\n📈 الإجمالي: ${orders.length}\n\n`;
  const names = [...new Set(orders.map(o => o.name))];
  report += `👥 الزبائن (${names.length}):\n`;
  for (const n of names) report += `  • ${n}: ${orders.filter(o => o.name === n).length} طلب\n`;
  report += '\n📋 جميع الطلبات:\n';
  for (const o of orders) {
    const prods = o.products ? o.products.map(p => `  • ${p.product} x${p.quantity}`).join('\n') : `  • ${o.product} x${o.quantity}`;
    report += `\n#${o.num} - ${o.name} - ${o.date}\n${prods}\n`;
  }
  const chunks = [];
  for (let i = 0; i < report.length; i += 4000) chunks.push(report.slice(i, i + 4000));
  for (const chunk of chunks) tgSend(userId, chunk);
}
function saveOrders() {
  try { fs.writeFileSync(ORDERS_FILE, JSON.stringify(orders)); } catch {}
}

async function processTGCommand(userId, text) {
  if (text === '/start') {
    if (!whatsappConnected && fs.existsSync('whatsapp-qr.png')) tgSendPhoto(userId, 'whatsapp-qr.png', '📱 امسح رمز QR باستخدام واتساب');
    sendStartKeyboard(userId);
  } else if (text === '/toggle' || text === '✅ تشغيل' || text === '⛔ إيقاف') {
    botEnabled = !botEnabled; saveState();
    sendStartKeyboard(userId);
  } else if (text === '/forceopen') {
    forceOpen = true; saveState();
    sendStartKeyboard(userId);
  } else if (text === '/forcenormal') {
    forceOpen = false; saveState();
    sendStartKeyboard(userId);
  } else if (text === '/uptime' || text === '🕒 المدة') {
    const sec = Math.floor((Date.now() - START_TIME) / 1000);
    const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    tgSend(userId, `🕒 مدة التشغيل:\n${d} يوم ${h} ساعة ${m} دقيقة ${s} ثانية`);
  } else if (text === '/orders' || text === '📋 الطلبات') {
    if (orders.length === 0) { tgSend(userId, '📭 لا توجد طلبات بعد'); return; }
    let list = `📋 قائمة الطلبات (${orders.length}):\n\n`;
    for (const o of orders.slice(-20).reverse()) {
      const prods = o.products ? o.products.map(p => `  • ${p.product} x${p.quantity}`).join('\n') : `  • ${o.product} x${o.quantity}`;
      list += `\n#${o.num} - ${o.name} - ${o.date}\n${prods}\n📞 ${o.phone}\n`;
    }
    tgSend(userId, list);
  } else if (text === '/report' || text === '📊 تقرير') {
    sendReport(userId);
  } else if (text.startsWith('/exclude ') || text.startsWith('🚫 استثناء ')) {
    const num = text.split(' ').slice(1).join(' ').trim();
    if (!num) { tgSend(userId, '⚠️ أرسل الرقم مع الأمر'); return; }
    if (!excludedNumbers.includes(num)) { excludedNumbers.push(num); saveState(); }
    tgSend(userId, `✅ تم استثناء ${num}\nالمستثنون: ${excludedNumbers.join(', ') || 'لا يوجد'}`);
  } else if (text.startsWith('/unexclude ') || text.startsWith('✅ إلغاء استثناء ')) {
    const num = text.split(' ').slice(1).join(' ').trim();
    if (!num) { tgSend(userId, '⚠️ أرسل الرقم مع الأمر'); return; }
    excludedNumbers = excludedNumbers.filter(n => n !== num); saveState();
    tgSend(userId, `✅ تم إلغاء استثناء ${num}\nالمستثنون: ${excludedNumbers.join(', ') || 'لا يوجد'}`);
  } else if (text === '/excluded' || text === '🚫 المستثنون') {
    tgSend(userId, excludedNumbers.length ? `🚫 الأرقام المستثناة:\n${excludedNumbers.join('\n')}` : '✅ لا توجد أرقام مستثناة');
  } else if (text === '⚡ معالجة') {
    tgSend(userId, '📝 أرسل رقم الطلب للمعالجة الفورية:\nمثال: معالجة 5');
  } else if (/^(معالجة|\/process)\s*\d+$/i.test(text.trim())) {
    const num = parseInt(text.trim().split(/\s+/).pop(), 10);
    for (const [wa, list] of pendingOrders) {
      const found = list.find(o => o.orderNum === num);
      if (found) { await processPendingOrder(wa, num); tgSend(userId, `⚡ تمت معالجة الطلب #${num} فورياً`); return; }
    }
    tgSend(userId, `⚠️ لا يوجد طلب معلق بالرقم #${num}`);
  } else if (text === '/pending' || text === '⏳ المعلقة') {
    if (pendingOrders.size === 0) { tgSend(userId, '📭 لا توجد طلبات معلقة'); return; }
    let msg = '⏳ الطلبات المعلقة:\n';
    for (const [wa, list] of pendingOrders) {
      for (const p of list) {
        const prods = getProducts(p.info);
        msg += `\n#${p.orderNum}`;
        if (p.queuedAt) msg += ` - ${p.queuedAt}`;
        msg += `\n👤 ${p.pushName}\n${formatProductsList(prods)}\n`;
        const rem = Math.max(0, 300000 - (Date.now() - (p.queuedAtTs || Date.now())));
        const remMin = Math.ceil(rem / 60000);
        msg += `⏱ ${remMin > 0 ? `المعالجة بعد ${remMin} دقيقة` : '⚡ جاري المعالجة'}\n`;
      }
    }
    tgSend(userId, msg);
  } else if (text === '/today' || text === '📅 اليوم') {
    const today = new Date();
    const todayStr = `${today.getDate()}/${today.getMonth()+1}/${today.getFullYear()}`;
    const todaysOrders = orders.filter(o => o.date && o.date.startsWith(todayStr));
    if (todaysOrders.length === 0) { tgSend(userId, '📭 لا توجد طلبات لليوم'); return; }
    tgSend(userId, `📅 طلبات اليوم (${todaysOrders.length}):`);
    for (const o of todaysOrders) {
      try {
        const imgBuf = await generateInvoiceImage({ ...o, orderNumber: o.num, date: o.date });
        const path = `${DATA_DIR}/today_${o.num}.png`;
        fs.writeFileSync(path, imgBuf);
        await tgSendPhoto(userId, path, `📋 فاتورة #${o.num} - ${o.name}`);
        try { fs.unlinkSync(path); } catch {}
      } catch (e) { tgSend(userId, `⚠️ فشل إرسال فاتورة #${o.num}: ${e.message}`); }
    }
  } else if (text === '/totals' || text === '📊 إجمالي المنتجات') {
    if (orders.length === 0) { tgSend(userId, '📭 لا توجد طلبات بعد'); return; }
    const prodMap = {};
    for (const o of orders) {
      const prods = getProducts(o);
      for (const p of prods) {
        const key = p.product.trim();
        prodMap[key] = (prodMap[key] || 0) + Number(p.quantity || 0);
      }
    }
    const products = Object.entries(prodMap).map(([product, quantity]) => ({ product, quantity }));
    products.sort((a, b) => b.quantity - a.quantity);
    const d = new Date();
    const dateStr = `${d.getDate()}/${d.getMonth()+1}/${d.getFullYear()}`;
    try {
      const imgBuf = await generateInvoiceImage({ products, name: 'إجمالي الطلبات', phone: '-', orderNumber: '📊', date: dateStr, title: 'إجمالي الطلبات', hideCustomer: true });
      const path = `${DATA_DIR}/totals.png`;
      fs.writeFileSync(path, imgBuf);
      await tgSendPhoto(userId, path, `📊 إجمالي المنتجات لجميع الطلبات`);
      try { fs.unlinkSync(path); } catch {}
    } catch (e) { tgSend(userId, `⚠️ فشل إنشاء الملخص: ${e.message}`); }
  } else if (text === '/clear' || text === '🗑 مسح') {
    tgSend(userId, '⚠️ هل أنت متأكد من مسح جميع الطلبات المكتملة؟\nأرسل "تأكيد" للمسح أو "إلغاء" للإلغاء');
  } else if (text === 'تأكيد') {
    orders = []; saveOrders();
    tgSend(userId, '✅ تم مسح جميع الطلبات المكتملة');
  } else if (text === 'إلغاء' || text === 'الغاء') {
    tgSend(userId, '✅ تم إلغاء المسح');
  } else if (text.startsWith('/addadmin ')) {
    if (String(userId) !== String(telegramChatId)) { tgSend(userId, '⚠️ فقط الادمن الأساسي يمكنه إضافة ادمنة'); return; }
    const id = text.split(' ')[1];
    if (!id || isNaN(id)) { tgSend(userId, '⚠️ أرسل: /addadmin <رقم المستخدم>'); return; }
    if (!admins.includes(id)) { admins.push(id); saveState(); }
    tgSend(userId, `✅ تم إضافة ${id} كادمن\n👥 الادمنة: ${admins.join(', ') || 'لا يوجد'}`);
  } else if (text.startsWith('/removeadmin ')) {
    if (String(userId) !== String(telegramChatId)) { tgSend(userId, '⚠️ فقط الادمن الأساسي يمكنه حذف ادمنة'); return; }
    const id = text.split(' ')[1];
    if (!id) { tgSend(userId, '⚠️ أرسل: /removeadmin <رقم المستخدم>'); return; }
    admins = admins.filter(a => a !== id); saveState();
    tgSend(userId, `✅ تم حذف ${id} من الادمنة\n👥 الادمنة: ${admins.join(', ') || 'لا يوجد'}`);
  } else if (text === '/admins') {
    showAdminPanel(userId);
  } else if (text === '/ping') {
    const pingStart = Date.now();
    const wa = whatsappConnected ? '✅ متصل' : '❌ غير متصل';
    const sec = Math.floor((pingStart - START_TIME) / 1000);
    const d = Math.floor(sec / 86400);
    tgSend(userId, `🏓 Pong!\n📡 وقت المعالجة: ${Date.now() - pingStart}ms\n💬 واتساب: ${wa}\n🕐 مدة التشغيل: ${d} يوم`);
  } else if (text === '/logout' || text === '🔌 تسجيل خروج واتساب') {
    tgSend(userId, '⚠️ هل أنت متأكد من تسجيل الخروج من واتساب؟\nأرسل "تأكيد خروج" أو "إلغاء"');
  } else if (text === '/relink' || text === '📱 QR جديد') {
    tgSend(userId, '📱 جاري تحضير رمز QR جديد...');
    whatsappConnected = false;
    const authPath = `${DATA_DIR}/wwebjs_auth`;
    try { fs.rmSync(authPath, { recursive: true, force: true }); } catch {}
    try { fs.unlinkSync('whatsapp-qr.png'); } catch {}
    if (waClient) { try { await waClient.destroy(); } catch {} waClient = null; }
    setTimeout(startWhatsApp, 3000);
  } else if (text === 'تأكيد خروج') {
    tgSend(userId, '🔌 جاري تسجيل الخروج من واتساب...');
    whatsappConnected = false;
    const authPath = `${DATA_DIR}/wwebjs_auth`;
    try { fs.rmSync(authPath, { recursive: true, force: true }); } catch {}
    try { fs.unlinkSync('whatsapp-qr.png'); } catch {}
    if (waClient) { try { await waClient.destroy(); } catch {} waClient = null; }
    setTimeout(startWhatsApp, 3000);
  }
}

function makePeer(userId, accessHash) {
  return { _: 'inputPeerUser', user_id: userId, access_hash: accessHash || 0 };
}

const mtproto = new MTProto({
  api_id: API_ID,
  api_hash: API_HASH,
  storageOptions: { path: `${DATA_DIR}/tg_session.json` },
});

function parseMarkdown(text) {
  const entities = [];
  let clean = '';
  let i = 0;
  while (i < text.length) {
    if (text[i] === '*' && i + 1 < text.length && text[i + 1] !== '*') {
      const end = text.indexOf('*', i + 1);
      if (end !== -1) {
        entities.push({ _: 'messageEntityBold', offset: clean.length, length: end - i - 1 });
        clean += text.slice(i + 1, end);
        i = end + 1;
        continue;
      }
    }
    if (text[i] === '_' && i + 1 < text.length && text[i + 1] !== '_') {
      const end = text.indexOf('_', i + 1);
      if (end !== -1) {
        entities.push({ _: 'messageEntityItalic', offset: clean.length, length: end - i - 1 });
        clean += text.slice(i + 1, end);
        i = end + 1;
        continue;
      }
    }
    if (text[i] === '`' && i + 1 < text.length && text[i + 1] !== '`') {
      const end = text.indexOf('`', i + 1);
      if (end !== -1) {
        entities.push({ _: 'messageEntityCode', offset: clean.length, length: end - i - 1 });
        clean += text.slice(i + 1, end);
        i = end + 1;
        continue;
      }
    }
    clean += text[i]; i++;
  }
  return { text: clean, entities: entities.length ? entities : undefined };
}

async function tgSend(chatId, text, opts = {}) {
  try {
    if (!mtproto) { console.error('tgSend: mtproto is UNDEFINED'); return; }
    if (typeof mtproto.call !== 'function') { console.error('tgSend: mtproto.call not a function', typeof mtproto.call); return; }
    const parsed = parseMarkdown(text);
    await mtproto.call('messages.sendMessage', {
      peer: makePeer(chatId, telegramAccessHash),
      message: parsed.text,
      entities: parsed.entities,
      random_id: BigInt(Math.floor(Date.now() + Math.random() * 1000)),
      ...opts,
    }, { dcId: 1 });
  } catch (err) {
    console.error('TG send error:', err.message, err.stack?.slice(0, 200));
  }
}

async function tgSendPhoto(chatId, filePath, caption) {
  try {
    const data = fs.readFileSync(filePath);
    const fileId = BigInt(Math.floor(Date.now() + Math.random() * 1000000));
    const partSize = 512 * 1024;
    const totalParts = Math.ceil(data.length / partSize);
    for (let i = 0; i < totalParts; i++) {
      await mtproto.call('upload.saveFilePart', {
        file_id: fileId, file_part: i,
        bytes: data.slice(i * partSize, Math.min((i + 1) * partSize, data.length)),
      }, { dcId: 1 });
    }
    await mtproto.call('messages.sendMedia', {
      peer: makePeer(chatId, telegramAccessHash),
      media: {
        _: 'inputMediaUploadedPhoto',
        file: { _: 'inputFile', id: fileId, parts: totalParts, name: 'qr.png' },
      },
      message: caption || '',
      random_id: BigInt(Math.floor(Date.now() + Math.random() * 1000)),
    }, { dcId: 1 });
  } catch (err) { console.error('TG send photo error:', err.message); }
}

async function tgSendToAllAdmins(text, opts = {}) {
  if (telegramChatId) await tgSend(telegramChatId, text, opts);
  for (const id of admins) { await tgSend(id, text, opts); }
}
async function tgSendPhotoToAllAdmins(filePath, caption) {
  if (telegramChatId) await tgSendPhoto(telegramChatId, filePath, caption);
  for (const id of admins) { await tgSendPhoto(id, filePath, caption); }
}

async function connectTelegram() {
  let dcId = 1;
  for (let i = 0; i < 20; i++) {
    try {
      const result = await mtproto.call('auth.importBotAuthorization', {
        flags: 0,
        bot_auth_token: BOT_TOKEN,
        api_id: API_ID,
        api_hash: API_HASH,
      }, { dcId });
      await mtproto.setDefaultDc(Number(dcId));
      console.log(`✅ متصل بتلجرام عبر MTProto (DC ${dcId})`);
      await mtproto.call('help.getConfig', {}, { dcId });
      return true;
    } catch (err) {
      const msg = err.error_message || '';
      if (msg.startsWith('USER_MIGRATE_')) {
        dcId = parseInt(msg.split('_').pop(), 10);
        console.log(`↪️ ترحيل إلى DC ${dcId}`);
        continue;
      }
      if (msg.startsWith('FLOOD_WAIT_')) {
        const wait = parseInt(msg.split('_').pop(), 10) + 5;
        console.log(`⏳ انتظار ${wait} ثانية بسبب FLOOD_WAIT`);
        await new Promise(r => setTimeout(r, wait * 1000));
        continue;
      }
      console.log(`⚠️ محاولة ${i + 1} فشلت:`, msg || err);
      await new Promise(r => setTimeout(r, 5000));
    }
  }
  console.log('❌ فشل الاتصال بتلجرام بعد 20 محاولة');
  return false;
}

async function resolveUser(userId) {
  try {
    const users = await mtproto.call('users.getUsers', {
      id: [{ _: 'inputUser', user_id: userId, access_hash: 0 }],
    });
    if (users && users[0] && users[0].access_hash) {
      telegramAccessHash = users[0].access_hash;
      saveState();
    }
  } catch (_) {}
}

function getNextKey() {
  const key = MISTRAL_API_KEYS[mistralKeyIndex];
  mistralKeyIndex = (mistralKeyIndex + 1) % MISTRAL_API_KEYS.length;
  return key;
}

async function aiFetch(body) {
  const keys = [...MISTRAL_API_KEYS];
  for (let attempt = 1; attempt <= 5 * keys.length; attempt++) {
    const key = getNextKey();
    try {
      const res = await fetch('https://api.mistral.ai/v1/chat/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${key}` },
        body: JSON.stringify(body),
      });
      if (res.status === 429) {
        console.log(`⏳ Rate limit على مفتاح، نحول على المفتاح التالي...`);
        continue;
      }
      if (!res.ok) throw new Error(`Mistral ${res.status}: ${await res.text()}`);
      return await res.json();
    } catch (err) {
      if (err.message.startsWith('Mistral 429')) continue;
      if (attempt < 5 * keys.length) {
        const wait = attempt * 10000;
        console.log(`⏳ AI فشل المحاولة ${attempt}/${5 * keys.length}، انتظار ${wait/1000} ثواني...`);
        await new Promise(r => setTimeout(r, wait));
      } else throw err;
    }
  }
}

async function classifyAndReply(messageText, contactName, waNum) {
  try {
    const data = await aiFetch({
      model: 'mistral-large-latest',
      messages: [
        { role: 'system', content: `أنت مساعد متجر لاستقبال طلبات المنتجات فقط.\n\nمعلومات العميل:\nالاسم: ${contactName}\nرقم الهاتف: ${waNum}\n\nصنف الرسالة إلى أحد الأنواع التالية:\n\n1. order: طلب منتج - فقط إذا كانت الرسالة تحتوي على اسم منتج محدد وعدد (مثل: اريد 10 حليب، دوز 5 خبز، عندك بيض؟ بكم الصابون؟). الكلام العام أو السؤال بدون اسم منتج واضح ليس طلباً.\n2. greeting: تحية أو سلام أو كلام عادي أو سؤال عن الحال لا يحتوي على اسم منتج (مثل: بيش، شلونك، هاي، شكو، تمام، مرحبا)\n3. off_topic: أي شيء آخر خارج نطاق المنتجات والطلبات\n\nتعليمات مهمة:\n- "بيش" أو "شلونك" أو "هاي" = greeting وليس order\n- مجرد كلمة بدون سياق طلب = greeting\n- لا تعتبر أي رسالة order إلا إذا كان فيها اسم منتج محدد\n- لا تقسم المنتج لعدة منتجات إلا إذا كان بينهم فاصل واضح مثل فاصلة (,) أو سطر جديد أو كل منتج معه رقمه الخاص\n- مثال: "توست حليب 5" = منتج واحد "توست حليب" وعدد 5\n- مثال: "10 حليب، 5 خبز" = منتجين\n\nأعد JSON:\n{"type":"order|greeting|off_topic","name":"اسم العميل","products":[{"product":"اسم المنتج","quantity":0}]}` },
        { role: 'user', content: messageText },
      ],
      response_format: { type: 'json_object' },
      temperature: 0.1,
    });
    const result = JSON.parse(data.choices[0].message.content);
    const info = result.type === 'order' ? {
      name: result.name || contactName,
      phone: waNum,
      products: result.products && result.products.length > 0 ? result.products : [{ product: result.product || 'غير محدد', quantity: result.quantity || 0 }],
    } : null;
    return { type: result.type || 'off_topic', info };
  } catch (err) {
    if (telegramChatId) tgSend(telegramChatId, `⚠️ AI معطل بعد 5 محاولات (تصنيف): ${err.message.slice(0, 100)}`);
    return { type: 'greeting', info: null };
  }
}

async function extractWithMistral(messageText, contactName, waNum) {
  try {
    const data = await aiFetch({
      model: 'mistral-large-latest',
      messages: [
        { role: 'system', content: `أنت مساعد استخراج طلبات. استخرج من رسالة العميل: اسم العميل، قائمة المنتجات والأعداد.\n\nرقم الهاتف (ثابت): ${waNum}\nالاسم المسجل: ${contactName}\n\nحول الكلمات لأرقام (عشر الاف=10000, خمسة=5).\nلا تقسم المنتج لعدة منتجات إلا إذا كان بينهم فاصل واضح (فاصلة، سطر جديد، أو كل منتج معه رقمه الخاص).\nمثال: "توست حليب 5" = منتج واحد "توست حليب" وعدد 5\nمثال: "10 حليب، 5 خبز" = منتجين\nأعد JSON:\n{"name":"...","products":[{"product":"...","quantity":0}]}` },
        { role: 'user', content: messageText },
      ],
      response_format: { type: 'json_object' },
      temperature: 0,
    });
    const result = JSON.parse(data.choices[0].message.content);
    const products = result.products && result.products.length > 0 ? result.products : [{ product: result.product || 'غير محدد', quantity: result.quantity || 0 }];
    return { name: result.name || contactName, phone: waNum, products };
  } catch (err) {
    if (telegramChatId) tgSend(telegramChatId, `⚠️ AI معطل بعد 5 محاولات (استخراج): ${err.message.slice(0, 100)}`);
    throw new Error(`AI extraction failed: ${err.message}`);
  }
}

function queueOrder(msgText, pushName, waNum, jid, info, orderNum) {
  const timeoutId = setTimeout(() => processPendingOrder(waNum, orderNum), 300000);
  const d = new Date();
  const queuedAt = `${d.getDate()}/${d.getMonth()+1}/${d.getFullYear()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  const list = pendingOrders.get(waNum) || [];
  list.push({ timeoutId, msgText, pushName, jid, orderNum, info, queuedAt, queuedAtTs: d.getTime() });
  pendingOrders.set(waNum, list);
}

async function processPendingOrder(waNum, orderNum) {
  const list = pendingOrders.get(waNum);
  if (!list) return;
  const entry = list.find(o => o.orderNum === orderNum);
  if (!entry) return;
  removePendingOrder(waNum, orderNum);
  const { msgText, pushName, jid, info } = entry;
  try {
    console.log(`🤖 معالجة طلب #${orderNum} من ${pushName}...`);
    await tgSendToAllAdmins(`⚙️ جاري معالجة طلب #${orderNum} ${pushName} (${waNum})`);
    if (waClient) waClient.sendMessage(jid, `🔔 جاري تجهيز طلبك #${orderNum}، سيتم إرسال الفاتورة قريباً\n\n——\nمخبز سنابل الطاحونه 🍞`);
    const extracted = info || await extractWithMistral(msgText, pushName, waNum);
    const products = getProducts(extracted);
    const d = new Date(); const dateStr = `${d.getDate()}/${d.getMonth()+1}/${d.getFullYear()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    const imgBuf = await generateInvoiceImage({ ...extracted, products, orderNumber: orderNum, date: dateStr });
    const invoicePath = `${DATA_DIR}/invoice_${orderNum}.png`;
    fs.writeFileSync(invoicePath, imgBuf);
    const productsTg = products.map(p => `📦 ${p.product}\n🔢 ${p.quantity}`).join('\n');
    const productsWa = products.map(p => `• ${p.product} x${p.quantity}`).join('\n');
    await tgSendPhotoToAllAdmins(invoicePath, `📋 فاتورة جديدة #${orderNum}`);
    await tgSendToAllAdmins(`👤 ${extracted.name}\n📞 ${extracted.phone}\n${productsTg}`);
    try {
      const media = new MessageMedia('image/png', imgBuf.toString('base64'), `invoice_${orderNum}.png`);
      await waClient.sendMessage(jid, media, { caption: `📋 فاتورة طلب #${orderNum}\n👤 ${extracted.name}\n${productsWa}\n——\nمخبز سنابل الطاحونه 🍞` });
    } catch (mediaErr) {
      console.error('⚠️ فشل إرسال الصورة للزبون:', mediaErr.message);
      await waClient.sendMessage(jid, `📋 فاتورة طلب #${orderNum}\n👤 ${extracted.name}\n${productsWa}\n——\nمخبز سنابل الطاحونه 🍞`);
    }
    orders.push({ num: orderNum, name: extracted.name, phone: extracted.phone, products, date: dateStr, waNum });
    saveOrders();
    try { fs.unlinkSync(invoicePath); } catch {}
  } catch (err) {
    console.error('❌ فشل معالجة الطلب:', err.message);
    await tgSendToAllAdmins(`⚠️ فشل معالجة طلب #${orderNum} من ${pushName} (${waNum}): ${err.message}\n\nالرسالة الأصلية:\n${msgText}`);
  }
}

function removePendingOrder(waNum, orderNum) {
  const list = pendingOrders.get(waNum);
  if (!list) return;
  const filtered = list.filter(o => o.orderNum !== orderNum);
  if (filtered.length === 0) pendingOrders.delete(waNum);
  else pendingOrders.set(waNum, filtered);
}

async function handleTGMessage(msg) {
  if (msg._ === 'message' && !msg.out) {
    if (msg.id && processedMsgIds.has(msg.id)) return;
    if (msg.id) { processedMsgIds.add(msg.id); if (processedMsgIds.size > 500) processedMsgIds.clear(); }
    let userId = msg.peer_id?.user_id || (msg.peer_id?._ === 'peerUser' && msg.peer_id.user_id);
    userId = Number(userId);
    if (!userId) return;
    if (!telegramChatId) {
      telegramChatId = userId;
      resolveUser(userId);
      saveState();
      console.log('📨 استقبلت رسالة من:', userId);
    }
    const text = msg.message || '';
    if (String(awaitingAdminAdd) === String(userId)) {
      awaitingAdminAdd = null;
      const id = text.trim();
      if (!id || isNaN(id)) { tgSend(userId, '⚠️ معرف غير صالح. أرسل رقماً صحيحاً'); return; }
      if (!admins.includes(id)) { admins.push(id); saveState(); }
      tgSend(userId, `✅ تم إضافة ${id} كادمن`);
      showAdminPanel(userId);
      return;
    }
    if (String(awaitingExcludeAdd) === String(userId)) {
      awaitingExcludeAdd = null;
      const num = text.trim();
      if (!num) { tgSend(userId, '⚠️ أرسل رقماً صحيحاً'); return; }
      if (!excludedNumbers.includes(num)) { excludedNumbers.push(num); saveState(); }
      tgSend(userId, `✅ تم استثناء ${num}`);
      showExcludedPanel(userId);
      return;
    }
    processTGCommand(userId, text);
  }
}

function showAdminPanel(userId) {
  let text = `👤 الأساسي: ${telegramChatId}\n`;
  text += admins.length ? `👥 الإضافيون (${admins.length}):\n${admins.join('\n')}` : '👥 لا يوجد ادمنة إضافيين';
  const rows = [
    { _: 'keyboardButtonRow', buttons: [
      { _: 'keyboardButtonCallback', text: '➕ إضافة ادمن', data: Buffer.from('/addadmin_prompt') },
    ] },
  ];
  if (admins.length > 0) {
    rows.push({ _: 'keyboardButtonRow', buttons: [
      { _: 'keyboardButtonCallback', text: '🗑 حذف ادمن', data: Buffer.from('/rmadmin') },
    ] });
  }
  rows.push({ _: 'keyboardButtonRow', buttons: [
    { _: 'keyboardButtonCallback', text: '🔙 رجوع', data: Buffer.from('/startmenu') },
  ] });
  tgSend(userId, text, { reply_markup: { _: 'replyInlineMarkup', rows } });
}

function showExcludedPanel(userId) {
  let t = excludedNumbers.length ? `🚫 الأرقام المستثناة:\n${excludedNumbers.join('\n')}` : '✅ لا توجد أرقام مستثناة';
  const rows = [
    { _: 'keyboardButtonRow', buttons: [{ _: 'keyboardButtonCallback', text: '➕ إضافة استثناء', data: Buffer.from('/exclude_prompt') }] },
  ];
  if (excludedNumbers.length > 0) {
    rows.push({ _: 'keyboardButtonRow', buttons: excludedNumbers.map(n => ({ _: 'keyboardButtonCallback', text: `🗑 ${n}`, data: Buffer.from(`/unexclude_${n}`) })) });
  }
  rows.push({ _: 'keyboardButtonRow', buttons: [{ _: 'keyboardButtonCallback', text: '🔙 رجوع', data: Buffer.from('/startmenu') }] });
  tgSend(userId, t, { reply_markup: { _: 'replyInlineMarkup', rows } });
}

function sendStartKeyboard(userId) {
  const waStatus = whatsappConnected ? '✅ متصل' : '❌ غير متصل';
  const enStatus = botEnabled ? '✅ مفعّل' : '⛔ متوقف';
  const foStatus = forceOpen ? '🔓 مفتوح قسري' : '⏰ وقت العمل';
  const now = new Date();
  const totalSec = Math.floor((now.getTime() - START_TIME) / 1000);
  const days = Math.floor(totalSec / 86400);
  const hours = Math.floor((totalSec % 86400) / 3600);
  const mins = Math.floor((totalSec % 3600) / 60);
  const secs = totalSec % 60;
  const uptime = `${days}ي ${hours}س ${mins}د ${secs}ث`;
  const todayPrefix = `${now.getDate()}/${now.getMonth()+1}/${now.getFullYear()}`;
  const todayCount = orders.filter(o => o.date && o.date.startsWith(todayPrefix)).length;
  const text = `🎛 *لوحة تحكم البوت*\n\n` +
    `🔌 *الحالة:*\n` +
    `• واتساب: ${waStatus}\n` +
    `• الاستقبال: ${enStatus}\n` +
    `• طلبات اليوم: ${todayCount}\n` +
    `• مدة التشغيل: ${uptime}\n` +
    `• الحالة: ${foStatus}`;
  tgSend(userId, text, {
    reply_markup: {
      _: 'replyInlineMarkup',
      rows: [
        { _: 'keyboardButtonRow', buttons: [{ _: 'keyboardButtonCallback', text: botEnabled ? '⛔ إيقاف' : '✅ تشغيل', data: Buffer.from('/toggle') }] },
        { _: 'keyboardButtonRow', buttons: [
          { _: 'keyboardButtonCallback', text: '📋 الطلبات', data: Buffer.from('/orders') },
          { _: 'keyboardButtonCallback', text: '📊 تقرير', data: Buffer.from('/report') },
        ] },
        { _: 'keyboardButtonRow', buttons: [
          { _: 'keyboardButtonCallback', text: '⏳ المعلقة', data: Buffer.from('/pending') },
          { _: 'keyboardButtonCallback', text: '📅 اليوم', data: Buffer.from('/today') },
        ] },
        { _: 'keyboardButtonRow', buttons: [
          { _: 'keyboardButtonCallback', text: forceOpen ? '🔒 إغلاق عادي' : '🔓 فتح إجباري', data: Buffer.from(forceOpen ? '/forcenormal' : '/forceopen') },
          { _: 'keyboardButtonCallback', text: '👥 الادمنة', data: Buffer.from('/admins') },
        ] },
        { _: 'keyboardButtonRow', buttons: [
          { _: 'keyboardButtonCallback', text: '🚫 المستثنون', data: Buffer.from('/excluded') },
          { _: 'keyboardButtonCallback', text: '📊 إجمالي المنتجات', data: Buffer.from('/totals') },
        ] },
        { _: 'keyboardButtonRow', buttons: [
          { _: 'keyboardButtonCallback', text: '⚡ معالجة', data: Buffer.from('/process') },
          { _: 'keyboardButtonCallback', text: '🗑 مسح', data: Buffer.from('/clear') },
        ] },
        { _: 'keyboardButtonRow', buttons: [
          { _: 'keyboardButtonCallback', text: '🔌 تسجيل خروج واتساب', data: Buffer.from('/logout') },
          { _: 'keyboardButtonCallback', text: '📱 QR جديد', data: Buffer.from('/relink') },
        ] },
      ],
    },
  });
}

async function handleUpdate(update) {
  if (update._ === 'updateBotCallbackQuery') {
    if (!update.data) return;
    const cmd = new TextDecoder().decode(update.data);
    const userId = Number(update.user_id);
    if (cmd === '/toggle') {
      botEnabled = !botEnabled; saveState();
      sendStartKeyboard(userId);
    } else if (cmd === '/forceopen') {
      tgSend(userId, '⚠️ هل تريد فتح البوت خارج وقت العمل؟', {
        reply_markup: {
          _: 'replyInlineMarkup',
          rows: [
            { _: 'keyboardButtonRow', buttons: [{ _: 'keyboardButtonCallback', text: '✅ نعم، فتح', data: Buffer.from('/forceopen_confirm') }, { _: 'keyboardButtonCallback', text: '❌ إلغاء', data: Buffer.from('/startmenu') }] },
          ],
        },
      });
    } else if (cmd === '/forceopen_confirm') {
      forceOpen = true; saveState();
      sendStartKeyboard(userId);
    } else if (cmd === '/forcenormal') {
      forceOpen = false; saveState();
      sendStartKeyboard(userId);
    } else if (cmd === '/uptime') {
      const sec = Math.floor((Date.now() - START_TIME) / 1000);
      const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
      tgSend(userId, `🕒 مدة التشغيل:\n${d} يوم ${h} ساعة ${m} دقيقة ${s} ثانية`);
    } else if (cmd === '/orders') {
      if (orders.length === 0) { tgSend(userId, '📭 لا توجد طلبات بعد'); return; }
      let list = `📋 قائمة الطلبات (${orders.length}):\n\n`;
      for (const o of orders.slice(-20).reverse()) {
        const prods = o.products ? o.products.map(p => `  • ${p.product} x${p.quantity}`).join('\n') : `  • ${o.product} x${o.quantity}`;
        list += `\n#${o.num} - ${o.name} - ${o.date}\n${prods}\n📞 ${o.phone}\n`;
      }
      tgSend(userId, list);
    } else if (cmd === '/report') {
      sendReport(userId);
    } else if (cmd === '/excluded') {
      showExcludedPanel(userId);
    } else if (cmd === '/exclude_prompt') {
      awaitingExcludeAdd = userId;
      setTimeout(() => { if (String(awaitingExcludeAdd) === String(userId)) awaitingExcludeAdd = null; }, 60000);
      tgSend(userId, '📝 أرسل رقم واتساب (بدون وبدون +) للاستثناء\n⚠️ سينتهي الطلب بعد 60 ثانية', {
        reply_markup: {
          _: 'replyInlineMarkup',
          rows: [
            { _: 'keyboardButtonRow', buttons: [
              { _: 'keyboardButtonCallback', text: '❌ إلغاء', data: Buffer.from('/cancel_exclude') },
            ] },
          ],
        },
      });
    } else if (cmd === '/cancel_exclude') {
      if (String(awaitingExcludeAdd) === String(userId)) awaitingExcludeAdd = null;
      tgSend(userId, '✅ تم إلغاء الإضافة');
      showExcludedPanel(userId);
    } else if (cmd.startsWith('/unexclude_')) {
      const num = cmd.replace('/unexclude_', '');
      excludedNumbers = excludedNumbers.filter(n => n !== num); saveState();
      tgSend(userId, `✅ تم إلغاء استثناء ${num}`);
      showExcludedPanel(userId);
    } else if (cmd === '/clear') {
      tgSend(userId, '⚠️ هل أنت متأكد من مسح جميع الطلبات المكتملة؟', {
        reply_markup: {
          _: 'replyInlineMarkup',
          rows: [
            { _: 'keyboardButtonRow', buttons: [
              { _: 'keyboardButtonCallback', text: '✅ تأكيد', data: Buffer.from('/clear_confirm') },
              { _: 'keyboardButtonCallback', text: '❌ إلغاء', data: Buffer.from('/clear_cancel') },
            ] },
          ],
        },
      });
    } else if (cmd === '/clear_confirm') {
      orders = []; saveOrders();
      tgSend(userId, '✅ تم مسح جميع الطلبات المكتملة');
    } else if (cmd === '/startmenu') {
      sendStartKeyboard(userId);
    } else if (cmd === '/admins') {
      showAdminPanel(userId);
    } else if (cmd === '/addadmin_prompt') {
      if (String(userId) !== String(telegramChatId)) { tgSend(userId, '⚠️ فقط الادمن الأساسي يمكنه إضافة ادمنة'); return; }
      awaitingAdminAdd = userId;
      setTimeout(() => { if (String(awaitingAdminAdd) === String(userId)) awaitingAdminAdd = null; }, 60000);
      tgSend(userId, '📝 أرسل معرف المستخدم (User ID) الذي تريد إضافته كادمن\n⚠️ سينتهي الطلب بعد 60 ثانية', {
        reply_markup: {
          _: 'replyInlineMarkup',
          rows: [
            { _: 'keyboardButtonRow', buttons: [
              { _: 'keyboardButtonCallback', text: '❌ إلغاء', data: Buffer.from('/cancel_addadmin') },
            ] },
          ],
        },
      });
    } else if (cmd === '/cancel_addadmin') {
      if (String(awaitingAdminAdd) === String(userId)) awaitingAdminAdd = null;
      tgSend(userId, '✅ تم إلغاء الإضافة');
      showAdminPanel(userId);
    } else if (cmd === '/rmadmin') {
      if (String(userId) !== String(telegramChatId)) { tgSend(userId, '⚠️ فقط الادمن الأساسي يمكنه حذف ادمنة'); return; }
      if (admins.length === 0) { tgSend(userId, '📭 لا يوجد ادمنة إضافيين'); showAdminPanel(userId); return; }
      const rows = admins.map(id => ({
        _: 'keyboardButtonRow', buttons: [
          { _: 'keyboardButtonCallback', text: `🗑 ${id}`, data: Buffer.from(`/rmadmin_${id}`) },
        ],
      }));
      rows.push({ _: 'keyboardButtonRow', buttons: [
        { _: 'keyboardButtonCallback', text: '🔙 رجوع', data: Buffer.from('/admins') },
      ] });
      tgSend(userId, '👥 اختر الادمن للحذف:', { reply_markup: { _: 'replyInlineMarkup', rows } });
    } else if (cmd.startsWith('/rmadmin_')) {
      if (String(userId) !== String(telegramChatId)) { tgSend(userId, '⚠️ فقط الادمن الأساسي يمكنه حذف ادمنة'); return; }
      const id = cmd.replace('/rmadmin_', '');
      admins = admins.filter(a => a !== id); saveState();
      tgSend(userId, `✅ تم حذف ${id} من الادمنة`);
      showAdminPanel(userId);
    } else if (cmd === '/adminpanel') {
      showAdminPanel(userId);
    } else if (cmd === '/pending') {
      if (pendingOrders.size === 0) { tgSend(userId, '📭 لا توجد طلبات معلقة'); return; }
      let msg = '⏳ الطلبات المعلقة:\n';
      for (const [wa, list] of pendingOrders) {
        for (const p of list) {
          const prods = getProducts(p.info);
          msg += `\n#${p.orderNum}`;
          if (p.queuedAt) msg += ` - ${p.queuedAt}`;
          msg += `\n👤 ${p.pushName}\n`;
          msg += `${formatProductsList(prods)}\n`;
          const rem = Math.max(0, 300000 - (Date.now() - (p.queuedAtTs || Date.now())));
          const remMin = Math.ceil(rem / 60000);
          msg += `⏱ ${remMin > 0 ? `المعالجة بعد ${remMin} دقيقة` : '⚡ جاري المعالجة'}\n`;
        }
      }
      tgSend(userId, msg);
    } else if (cmd === '/process') {
      if (pendingOrders.size === 0) { tgSend(userId, '📭 لا توجد طلبات معلقة'); return; }
      const rows = [];
      for (const [wa, list] of pendingOrders) {
        for (const p of list) {
          rows.push({ _: 'keyboardButtonRow', buttons: [
            { _: 'keyboardButtonCallback', text: `⚡ #${p.orderNum} - ${p.pushName}`, data: Buffer.from(`/process_order_${p.orderNum}`) },
          ] });
        }
      }
      rows.push({ _: 'keyboardButtonRow', buttons: [
        { _: 'keyboardButtonCallback', text: '🔙 رجوع', data: Buffer.from('/startmenu') },
      ] });
      tgSend(userId, '⚡ اختر طلباً للمعالجة الفورية:', { reply_markup: { _: 'replyInlineMarkup', rows } });
    } else if (cmd.startsWith('/process_order_')) {
      const num = parseInt(cmd.replace('/process_order_', ''), 10);
      for (const [wa, list] of pendingOrders) {
        const found = list.find(o => o.orderNum === num);
        if (found) { await processPendingOrder(wa, num); tgSend(userId, `⚡ تمت معالجة الطلب #${num} فورياً`); return; }
      }
      tgSend(userId, `⚠️ لا يوجد طلب معلق بالرقم #${num}`);
    } else if (cmd === '/logout') {
      tgSend(userId, '⚠️ هل أنت متأكد من تسجيل الخروج من واتساب؟', {
        reply_markup: {
          _: 'replyInlineMarkup',
          rows: [
            { _: 'keyboardButtonRow', buttons: [
              { _: 'keyboardButtonCallback', text: '✅ نعم، تسجيل خروج', data: Buffer.from('/logout_confirm') },
              { _: 'keyboardButtonCallback', text: '❌ إلغاء', data: Buffer.from('/startmenu') },
            ] },
          ],
        },
      });
    } else if (cmd === '/logout_confirm') {
      tgSend(userId, '🔌 جاري تسجيل الخروج من واتساب...');
      whatsappConnected = false;
      const authPath = `${DATA_DIR}/wwebjs_auth`;
      try { fs.rmSync(authPath, { recursive: true, force: true }); } catch {}
      try { fs.unlinkSync('whatsapp-qr.png'); } catch {}
      if (waClient) { try { await waClient.destroy(); } catch {} waClient = null; }
      setTimeout(startWhatsApp, 3000);
    } else if (cmd === '/relink') {
      tgSend(userId, '📱 جاري تحضير رمز QR جديد...');
      whatsappConnected = false;
      const authPath = `${DATA_DIR}/wwebjs_auth`;
      try { fs.rmSync(authPath, { recursive: true, force: true }); } catch {}
      try { fs.unlinkSync('whatsapp-qr.png'); } catch {}
      if (waClient) { try { await waClient.destroy(); } catch {} waClient = null; }
      setTimeout(startWhatsApp, 3000);
    } else if (cmd === '/totals') {
      if (orders.length === 0) { tgSend(userId, '📭 لا توجد طلبات بعد'); return; }
      const prodMap = {};
      for (const o of orders) {
        const prods = getProducts(o);
        for (const p of prods) {
          const key = p.product.trim();
          prodMap[key] = (prodMap[key] || 0) + Number(p.quantity || 0);
        }
      }
      const products = Object.entries(prodMap).map(([product, quantity]) => ({ product, quantity }));
      products.sort((a, b) => b.quantity - a.quantity);
      const d = new Date();
      const dateStr = `${d.getDate()}/${d.getMonth()+1}/${d.getFullYear()}`;
      try {
        const imgBuf = await generateInvoiceImage({ products, name: 'إجمالي الطلبات', phone: '-', orderNumber: '📊', date: dateStr, title: 'إجمالي الطلبات', hideCustomer: true });
        const path = `${DATA_DIR}/totals.png`;
        fs.writeFileSync(path, imgBuf);
        await tgSendPhoto(userId, path, `📊 إجمالي المنتجات لجميع الطلبات`);
        try { fs.unlinkSync(path); } catch {}
      } catch (e) { tgSend(userId, `⚠️ فشل إنشاء الملخص: ${e.message}`); }
    } else if (cmd === '/today') {
      const today = new Date();
      const todayStr = `${today.getDate()}/${today.getMonth()+1}/${today.getFullYear()}`;
      const todaysOrders = orders.filter(o => o.date && o.date.startsWith(todayStr));
      if (todaysOrders.length === 0) { tgSend(userId, '📭 لا توجد طلبات لليوم'); return; }
      tgSend(userId, `📅 طلبات اليوم (${todaysOrders.length}):`);
      for (const o of todaysOrders) {
        try {
          const imgBuf = await generateInvoiceImage({ ...o, orderNumber: o.num, date: o.date });
          const path = `${DATA_DIR}/today_${o.num}.png`;
          fs.writeFileSync(path, imgBuf);
          await tgSendPhoto(userId, path, `📋 فاتورة #${o.num} - ${o.name}`);
          try { fs.unlinkSync(path); } catch {}
        } catch (e) { tgSend(userId, `⚠️ فشل إرسال فاتورة #${o.num}: ${e.message}`); }
      }
    }
    try { await mtproto.call('messages.setBotCallbackAnswer', { query_id: update.query_id }, { dcId: 1 }); } catch {}
    return;
  }
  if (update._ === 'updateNewMessage' && update.message) {
    handleTGMessage(update.message);
  } else if (update._ === 'updateShortMessage' && !update.out) {
    if (update.id && processedMsgIds.has(update.id)) return;
    if (update.id) { processedMsgIds.add(update.id); if (processedMsgIds.size > 500) processedMsgIds.clear(); }
    const userId = update.user_id;
    if (!userId) return;
    if (!telegramChatId) { telegramChatId = userId; resolveUser(userId); }
    const text = update.message || '';
    if (String(awaitingAdminAdd) === String(userId)) {
      awaitingAdminAdd = null;
      const id = text.trim();
      if (!id || isNaN(id)) { tgSend(userId, '⚠️ معرف غير صالح. أرسل رقماً صحيحاً'); return; }
      if (!admins.includes(id)) { admins.push(id); saveState(); }
      tgSend(userId, `✅ تم إضافة ${id} كادمن`);
      showAdminPanel(userId);
      return;
    }
    if (String(awaitingExcludeAdd) === String(userId)) {
      awaitingExcludeAdd = null;
      const num = text.trim();
      if (!num) { tgSend(userId, '⚠️ أرسل رقماً صحيحاً'); return; }
      if (!excludedNumbers.includes(num)) { excludedNumbers.push(num); saveState(); }
      tgSend(userId, `✅ تم استثناء ${num}`);
      showExcludedPanel(userId);
      return;
    }
    if (text === '/start') {
      if (!whatsappConnected && fs.existsSync('whatsapp-qr.png')) {
        tgSendPhoto(userId, 'whatsapp-qr.png', '📱 امسح رمز QR باستخدام واتساب');
      }
      sendStartKeyboard(userId);
    } else if (text === '/toggle' || text === '✅ تشغيل' || text === '⛔ إيقاف') {
      botEnabled = !botEnabled; saveState();
      sendStartKeyboard(userId);
    } else if (text === '/forceopen') {
      forceOpen = true; saveState();
      sendStartKeyboard(userId);
    } else if (text === '/forcenormal') {
      forceOpen = false; saveState();
      sendStartKeyboard(userId);
    } else if (text === '/uptime' || text === '🕒 المدة') {
      const sec = Math.floor((Date.now() - START_TIME) / 1000);
      const d = Math.floor(sec / 86400);
      const h = Math.floor((sec % 86400) / 3600);
      const m = Math.floor((sec % 3600) / 60);
      const s = sec % 60;
      tgSend(userId, `🕒 مدة التشغيل:\n${d} يوم ${h} ساعة ${m} دقيقة ${s} ثانية`);
    } else if (text === '/orders' || text === '📋 الطلبات') {
      if (orders.length === 0) { tgSend(userId, '📭 لا توجد طلبات بعد'); return; }
      let list = `📋 قائمة الطلبات (${orders.length}):\n\n`;
      for (const o of orders.slice(-20).reverse()) {
        const prods = o.products ? o.products.map(p => `  • ${p.product} x${p.quantity}`).join('\n') : `  • ${o.product} x${o.quantity}`;
        list += `\n#${o.num} - ${o.name} - ${o.date}\n${prods}\n📞 ${o.phone}\n`;
      }
      tgSend(userId, list);
    } else if (text === '/report' || text === '📊 تقرير') {
      sendReport(userId);
    } else if (text.startsWith('/exclude ') || text.startsWith('🚫 استثناء ')) {
      const num = text.split(' ').slice(1).join(' ').trim();
      if (!num) { tgSend(userId, '⚠️ أرسل الرقم مع الأمر'); return; }
      if (!excludedNumbers.includes(num)) { excludedNumbers.push(num); saveState(); }
      tgSend(userId, `✅ تم استثناء ${num}\nالمستثنون: ${excludedNumbers.join(', ') || 'لا يوجد'}`);
    } else if (text.startsWith('/unexclude ') || text.startsWith('✅ إلغاء استثناء ')) {
      const num = text.split(' ').slice(1).join(' ').trim();
      if (!num) { tgSend(userId, '⚠️ أرسل الرقم مع الأمر'); return; }
      excludedNumbers = excludedNumbers.filter(n => n !== num); saveState();
      tgSend(userId, `✅ تم إلغاء استثناء ${num}\nالمستثنون: ${excludedNumbers.join(', ') || 'لا يوجد'}`);
    } else if (text === '/excluded' || text === '🚫 المستثنون') {
      tgSend(userId, excludedNumbers.length ? `🚫 الأرقام المستثناة:\n${excludedNumbers.join('\n')}` : '✅ لا توجد أرقام مستثناة');
    } else if (text === '⚡ معالجة') {
      tgSend(userId, '📝 أرسل رقم الطلب للمعالجة الفورية:\nمثال: معالجة 5');
    } else if (/^(معالجة|\/process)\s*\d+$/i.test(text.trim())) {
      const num = parseInt(text.trim().split(/\s+/).pop(), 10);
      for (const [wa, list] of pendingOrders) {
        const found = list.find(o => o.orderNum === num);
        if (found) { await processPendingOrder(wa, num); tgSend(userId, `⚡ تمت معالجة الطلب #${num} فورياً`); return; }
      }
      tgSend(userId, `⚠️ لا يوجد طلب معلق بالرقم #${num}`);
    } else if (text === '/pending' || text === '⏳ المعلقة') {
      if (pendingOrders.size === 0) { tgSend(userId, '📭 لا توجد طلبات معلقة'); return; }
      let msg = '⏳ الطلبات المعلقة:\n';
      for (const [wa, list] of pendingOrders) {
        for (const p of list) {
          const prods = getProducts(p.info);
          msg += `\n#${p.orderNum}`;
          if (p.queuedAt) msg += ` - ${p.queuedAt}`;
          msg += `\n👤 ${p.pushName}\n${formatProductsList(prods)}\n`;
          const rem = Math.max(0, 300000 - (Date.now() - (p.queuedAtTs || Date.now())));
          const remMin = Math.ceil(rem / 60000);
          msg += `⏱ ${remMin > 0 ? `المعالجة بعد ${remMin} دقيقة` : '⚡ جاري المعالجة'}\n`;
        }
      }
      tgSend(userId, msg);
    } else if (text === '/today' || text === '📅 اليوم') {
      const today = new Date();
      const todayStr = `${today.getDate()}/${today.getMonth()+1}/${today.getFullYear()}`;
      const todaysOrders = orders.filter(o => o.date && o.date.startsWith(todayStr));
      if (todaysOrders.length === 0) { tgSend(userId, '📭 لا توجد طلبات لليوم'); return; }
      tgSend(userId, `📅 طلبات اليوم (${todaysOrders.length}):`);
      for (const o of todaysOrders) {
        try {
          const imgBuf = await generateInvoiceImage({ ...o, orderNumber: o.num, date: o.date });
          const path = `${DATA_DIR}/today_${o.num}.png`;
          fs.writeFileSync(path, imgBuf);
          await tgSendPhoto(userId, path, `📋 فاتورة #${o.num} - ${o.name}`);
          try { fs.unlinkSync(path); } catch {}
        } catch (e) { tgSend(userId, `⚠️ فشل إرسال فاتورة #${o.num}: ${e.message}`); }
      }
    } else if (text === '/totals' || text === '📊 إجمالي المنتجات') {
      if (orders.length === 0) { tgSend(userId, '📭 لا توجد طلبات بعد'); return; }
      const prodMap = {};
      for (const o of orders) {
        const prods = getProducts(o);
        for (const p of prods) {
          const key = p.product.trim();
          prodMap[key] = (prodMap[key] || 0) + Number(p.quantity || 0);
        }
      }
      const products = Object.entries(prodMap).map(([product, quantity]) => ({ product, quantity }));
      products.sort((a, b) => b.quantity - a.quantity);
      const d = new Date();
      const dateStr = `${d.getDate()}/${d.getMonth()+1}/${d.getFullYear()}`;
      try {
        const imgBuf = await generateInvoiceImage({ products, name: 'إجمالي الطلبات', phone: '-', orderNumber: '📊', date: dateStr, title: 'إجمالي الطلبات', hideCustomer: true });
        const path = `${DATA_DIR}/totals.png`;
        fs.writeFileSync(path, imgBuf);
        await tgSendPhoto(userId, path, `📊 إجمالي المنتجات لجميع الطلبات`);
        try { fs.unlinkSync(path); } catch {}
      } catch (e) { tgSend(userId, `⚠️ فشل إنشاء الملخص: ${e.message}`); }
    } else if (text === '/clear' || text === '🗑 مسح') {
      tgSend(userId, '⚠️ هل أنت متأكد من مسح جميع الطلبات المكتملة؟\nأرسل "تأكيد" للمسح أو "إلغاء" للإلغاء');
    } else if (text === 'تأكيد') {
      orders = []; saveOrders();
      tgSend(userId, '✅ تم مسح جميع الطلبات المكتملة');
    } else if (text === 'إلغاء' || text === 'الغاء') {
      tgSend(userId, '✅ تم إلغاء المسح');
    } else if (text.startsWith('/addadmin ')) {
      if (String(userId) !== String(telegramChatId)) { tgSend(userId, '⚠️ فقط الادمن الأساسي يمكنه إضافة ادمنة'); return; }
      const id = text.split(' ')[1];
      if (!id || isNaN(id)) { tgSend(userId, '⚠️ أرسل: /addadmin <رقم المستخدم>'); return; }
      if (!admins.includes(id)) { admins.push(id); saveState(); }
      tgSend(userId, `✅ تم إضافة ${id} كادمن\n👥 الادمنة: ${admins.join(', ') || 'لا يوجد'}`);
    } else if (text.startsWith('/removeadmin ')) {
      if (String(userId) !== String(telegramChatId)) { tgSend(userId, '⚠️ فقط الادمن الأساسي يمكنه حذف ادمنة'); return; }
      const id = text.split(' ')[1];
      if (!id) { tgSend(userId, '⚠️ أرسل: /removeadmin <رقم المستخدم>'); return; }
      admins = admins.filter(a => a !== id); saveState();
      tgSend(userId, `✅ تم حذف ${id} من الادمنة\n👥 الادمنة: ${admins.join(', ') || 'لا يوجد'}`);
    } else if (text === '/admins') {
      showAdminPanel(userId);
    } else if (text === '/ping') {
      const pingStart = Date.now();
      const wa = whatsappConnected ? '✅ متصل' : '❌ غير متصل';
      const sec = Math.floor((pingStart - startTime) / 1000);
      const d = Math.floor(sec / 86400);
      tgSend(userId, `🏓 Pong!\n📡 وقت المعالجة: ${Date.now() - pingStart}ms\n💬 واتساب: ${wa}\n🕐 مدة التشغيل: ${d} يوم`);
    } else if (text === '/logout' || text === '🔌 تسجيل خروج واتساب') {
      tgSend(userId, '⚠️ هل أنت متأكد من تسجيل الخروج من واتساب؟\nأرسل "تأكيد خروج" أو "إلغاء"');
    } else if (text === '/relink' || text === '📱 QR جديد') {
      tgSend(userId, '📱 جاري تحضير رمز QR جديد...');
      whatsappConnected = false;
      const authPath = `${DATA_DIR}/wwebjs_auth`;
      try { fs.rmSync(authPath, { recursive: true, force: true }); } catch {}
      try { fs.unlinkSync('whatsapp-qr.png'); } catch {}
      if (waClient) { try { await waClient.destroy(); } catch {} waClient = null; }
      setTimeout(startWhatsApp, 3000);
    } else if (text === 'تأكيد خروج') {
      tgSend(userId, '🔌 جاري تسجيل الخروج من واتساب...');
      whatsappConnected = false;
      const authPath = `${DATA_DIR}/wwebjs_auth`;
      try { fs.rmSync(authPath, { recursive: true, force: true }); } catch {}
      try { fs.unlinkSync('whatsapp-qr.png'); } catch {}
      if (waClient) { try { await waClient.destroy(); } catch {} waClient = null; }
      setTimeout(startWhatsApp, 3000);
    }
  }
}

function handleUpdatesContainer(container) {
  for (const u of (container.updates || [])) handleUpdate(u);
}

mtproto.updates.on('updateNewMessage', (u) => handleUpdate(u));
mtproto.updates.on('updateShortMessage', (u) => handleUpdate(u));
mtproto.updates.on('updateShort', (u) => u.update && handleUpdate(u.update));
mtproto.updates.on('updates', (u) => handleUpdatesContainer(u));
mtproto.updates.on('updatesCombined', (u) => handleUpdatesContainer(u));

connectTelegram();

let tgPts = null, tgDate = 0, tgQts = null;

let heartbeatCount = 0;
async function pollUpdates() {
  while (true) {
    await new Promise(r => setTimeout(r, 15000));
    heartbeatCount++;
    try {
      if (tgPts === null) {
        const st = await mtproto.call('updates.getState', {}, { dcId: 1 });
        tgPts = st.pts; tgDate = st.date; tgQts = st.qts;
        console.log('📬 updates.getState OK:', `pts=${tgPts}`, `date=${tgDate}`, `qts=${tgQts}`);
        continue;
      }
      const diff = await mtproto.call('updates.getDifference', { pts: tgPts, date: tgDate, qts: tgQts }, { dcId: 1 });
      if (diff._ === 'updates.difference' || diff._ === 'updates.differenceSlice') {
        for (const m of (diff.new_messages || [])) {
          if (m._ === 'message' && !m.out) { console.log('📬 diff msg:', m.message?.slice(0, 80)); handleTGMessage(m); }
        }
        for (const u of (diff.other_updates || [])) { handleUpdate(u); }
        if (diff._ === 'updates.difference') { tgPts = diff.state.pts; tgQts = diff.state.qts; tgDate = diff.state.date; }
      } else if (diff._ === 'updates.differenceEmpty') { tgDate = diff.date; }
      else if (diff._ === 'updates.differenceTooLong') { tgPts = diff.pts; }
    } catch (e) { console.log('⚠️ poll:', e.error_message || e.message || e); }
  }
}
pollUpdates();

console.log('🚀 جاري تشغيل البوت...');

let waClient = null;
let waStarting = false;

async function startWhatsApp() {
  if (waStarting) { console.log('⏳ واتساب قيد التشغيل بالفعل، تخطي...'); return; }
  waStarting = true;
  if (waClient) {
    try { waClient.removeAllListeners(); await waClient.destroy(); } catch {}
    waClient = null;
  }
  console.log('🔵 بدء تشغيل واتساب (whatsapp-web.js)...');
  waClient = new Client({
    authStrategy: new LocalAuth({ dataPath: `${DATA_DIR}/wwebjs_auth` }),
    authTimeoutMs: 180000,
    restartOnAuthFail: false,
    puppeteer: {
      executablePath: process.env.CHROME_PATH || process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
      headless: true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--no-first-run',
        '--no-zygote',
        '--disable-gpu',
        '--disable-extensions',
        '--disable-background-networking',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-sync',
        '--metrics-recording-only',
      ],
    },
  });

  const BAKERY_SIGNATURE = '\n\n——\nمخبز سنابل الطاحونه 🍞';
  function sendWA(jid, text) { return waClient.sendMessage(jid, text + BAKERY_SIGNATURE); }

  let qrSent = false;
  let qrTimer = null;
  let isDestroyed = false;

  function safeDestroy() {
    if (isDestroyed) return;
    isDestroyed = true;
    waStarting = false;
    whatsappConnected = false;
    try { waClient.removeAllListeners(); waClient.destroy(); } catch {}
    waClient = null;
  }

  waClient.on('qr', (qr) => {
    if (qrSent || isDestroyed) return;
    qrSent = true;
    qrcodeTerminal.generate(qr, { small: true });
    qrcode.toFile('whatsapp-qr.png', qr, { width: 400 }, (err) => {
      if (err) console.error('خطأ في حفظ QR:', err);
      else {
        console.log('📸 تم حفظ QR كصورة: whatsapp-qr.png');
        tgSendPhotoToAllAdmins('whatsapp-qr.png', '📱 امسح رمز QR باستخدام واتساب');
      }
    });
    console.log('📱 امسح رمز QR باستخدام واتساب');
    qrTimer = setTimeout(() => {
      if (whatsappConnected || isDestroyed) return;
      console.log('⏰ لم يتم الاتصال بعد 120 ثانية من QR، إعادة تشغيل...');
      safeDestroy();
      setTimeout(startWhatsApp, 5000);
    }, 120000);
  });

  waClient.on('authenticated', () => {
    if (isDestroyed) return;
    if (qrTimer) { clearTimeout(qrTimer); qrTimer = null; }
    console.log('🔑 تم المصادقة، في انتظار التجهيز...');
    qrTimer = setTimeout(() => {
      if (whatsappConnected || isDestroyed) return;
      console.log('⏰ تمت المصادقة لكن الـ ready لم يصل بعد 90 ثانية، إعادة تشغيل...');
      safeDestroy();
      setTimeout(startWhatsApp, 5000);
    }, 90000);
  });

  waClient.on('ready', () => {
    if (isDestroyed) return;
    whatsappConnected = true;
    waStarting = false;
    if (qrTimer) { clearTimeout(qrTimer); qrTimer = null; }
    console.log('✅ واتساب جاهز');
  });

  waClient.on('disconnected', (reason) => {
    console.log('❌ واتساب فصل:', reason);
    tgSendToAllAdmins(`❌ واتساب فصل: ${reason}`);
    whatsappConnected = false;
    if (reason === 'LOGGED_OUT' || reason === 'LOGOUT') {
      const authPath = `${DATA_DIR}/wwebjs_auth`;
      try { fs.rmSync(authPath, { recursive: true, force: true }); } catch {}
      try { fs.unlinkSync('whatsapp-qr.png'); } catch {}
      console.log('🗑️ تم حذف الجلسة القديمة...');
    }
    safeDestroy();
    setTimeout(startWhatsApp, 5000);
  });

  waClient.on('message', async (msg) => {
    if (msg.fromMe) return;
    if (!botEnabled) return;
    if (msg.isStatus || msg.from?.includes('@broadcast')) return;

    const jid = msg.from;
    let waNum = jid.split('@')[0];
    if (excludedNumbers.includes(waNum)) return;

    let pushName = waNum;
    try {
      const contact = await msg.getContact();
      pushName = contact.pushname || contact.name || waNum;
      if (contact.id && contact.id.user && contact.id.user.length < waNum.length) waNum = contact.id.user;
    } catch (_) {}

    const msgText = msg.body || '';

    await waClient.sendSeen(jid);

    if (!msgText) return;

    if (/^طلباتي$/i.test(msgText.trim())) {
      const userOrders = orders.filter(o => o.waNum === waNum);
      const pendingList = pendingOrders.get(waNum) || [];
      const pendingConf = pendingConfirmations.get(waNum);
      let reply = '';
      if (pendingConf) {
        const confProds = getProducts(pendingConf.info);
        reply += `⏳ طلب بانتظار التأكيد:\n${formatProductsList(confProds)}\nأرسل "نعم" للتأكيد\n\n`;
      }
      if (pendingList.length > 0) {
        reply += '⏳ طلبات معلقة:\n';
        for (const p of pendingList) {
          reply += `\n#${p.orderNum}`;
          if (p.queuedAt) reply += ` - ${p.queuedAt}`;
          reply += '\n';
          const pProds = getProducts(p.info);
          if (pProds.length > 0) reply += `${formatProductsList(pProds)}\n`;
        }
        reply += '\n';
      }
      if (userOrders.length === 0 && pendingList.length === 0 && !pendingConf) { reply = '📭 لا توجد طلبات سابقة'; }
      else if (userOrders.length > 0) {
        reply += '📋 الطلبات المكتملة:\n';
        for (const o of userOrders.slice(-10).reverse()) {
          const prods = o.products ? o.products.map(p => `• ${p.product} x${p.quantity}`).join('\n') : `• ${o.product} x${o.quantity}`;
          reply += `\n#${o.num} - ${o.date}\n${prods}\n`;
        }
      }
      await sendWA(jid, reply);
      return;
    }

    const confirmKeywords = ['نعم', 'اي', 'انعم', 'ok', 'تم', 'yes', 'اكيد', 'طيب', 'yeah', 'yep', 'موافق', 'تمام'];
    const rejectKeywords = ['لا', 'na', 'no', 'الغي', 'الغاء', 'لا شكرا'];
    const pendingAddition = pendingAdditions.get(waNum);
    const pendingConf = pendingConfirmations.get(waNum);
    const trimmed = msgText.trim().toLowerCase();

    if (pendingAddition && confirmKeywords.some(k => trimmed === k || trimmed.startsWith(k + ' '))) {
      pendingAdditions.delete(waNum);
      const existingList = pendingOrders.get(waNum);
      const newProducts = getProducts(pendingAddition.info);
      if (existingList && existingList.length > 0) {
        for (const entry of existingList) {
          const existingProducts = getProducts(entry.info);
          entry.info.products = [...existingProducts, ...newProducts];
          clearTimeout(entry.timeoutId);
          entry.timeoutId = setTimeout(() => processPendingOrder(waNum, entry.orderNum), 300000);
        }
      }
      const orderNums = existingList.map(e => `#${e.orderNum}`).join(', ');
      await sendWA(jid, `✅ تمت إضافة المنتجات إلى طلبك ${orderNums}`);
      await tgSendToAllAdmins(`➕ إضافة منتجات لطلب ${orderNums} من ${pushName} (${waNum})\n${formatProductsList(newProducts)}`);
      return;
    }

    if (pendingAddition && rejectKeywords.some(k => trimmed.startsWith(k))) {
      pendingAdditions.delete(waNum);
      // Treat as new order
      const additionInfo = pendingAddition.info;
      const additionOrderNum = ++orderCounter;
      pendingOrders.set(waNum, [{ msgText: pendingAddition.msgText, pushName: pendingAddition.pushName, jid: pendingAddition.jid, info: additionInfo, orderNum: additionOrderNum }]);
      processPendingOrder(waNum, additionOrderNum);
      const additionProducts = getProducts(additionInfo);
      await sendWA(jid, `✅ تم استلام طلبك #${additionOrderNum}، سيتم تجهيز الفاتورة\n📋 ${formatProductsList(additionProducts)}`);
      await tgSendToAllAdmins(`📥 طلب جديد #${additionOrderNum} من ${pendingAddition.pushName} (${waNum})\n${formatProductsList(additionProducts)}\n⚡ جاري المعالجة`);
      return;
    }

    if (pendingConf && confirmKeywords.some(k => trimmed === k || trimmed.startsWith(k + ' '))) {
      clearTimeout(pendingConf.timeoutId);
      const orderNum = ++orderCounter;
      pendingOrders.set(pendingConf.waNum, [{ msgText: pendingConf.msgText, pushName: pendingConf.pushName, jid: pendingConf.jid, info: pendingConf.info, orderNum }]);
      processPendingOrder(pendingConf.waNum, orderNum);
      pendingConfirmations.delete(waNum);
      const confirmProducts = getProducts(pendingConf.info);
      await sendWA(jid, `✅ تم تأكيد الطلب\n📋 رقم الطلب: #${orderNum}\n${formatProductsList(confirmProducts)}\n🔔 يتم تجهيز الفاتورة الآن\n📝 للإلغاء أرسل: إلغاء ${orderNum}`);
      await tgSendToAllAdmins(`📥 طلب جديد #${orderNum} من ${pendingConf.pushName} (${waNum})\n${formatProductsList(confirmProducts)}\n⚡ جاري التجهيز`);
      return;
    }

    if (pendingConf && rejectKeywords.some(k => trimmed.startsWith(k))) {
      clearTimeout(pendingConf.timeoutId);
      pendingConfirmations.delete(waNum);
      await sendWA(jid, '❌ تم إلغاء الطلب');
      await tgSendToAllAdmins(`❌ إلغاء طلب (قبل التأكيد) من ${pushName} (${waNum})`);
      return;
    }

    const baghdadHour = (new Date().getUTCHours() + 3) % 24;
    if (!forceOpen && baghdadHour >= 4 && baghdadHour < 10) {
      await sendWA(jid, '🔴 المعمل مغلق حالياً\n⏰ أوقات العمل: من 10 صباحاً إلى 4 فجراً\n🕐 بتوقيت بغداد\n\nسيتم استقبال طلباتك عندما نفتح');
      await tgSendToAllAdmins(`🔴 رسالة خارج أوقات العمل من ${pushName} (${waNum}): ${msgText.slice(0, 100)}`);
      return;
    }

    const classification = await classifyAndReply(msgText, pushName, waNum);

    if (classification.type === 'order') {
      const pendingList = pendingOrders.get(waNum);
      if (pendingList && pendingList.length > 0) {
        const orderNums = pendingList.map(e => `#${e.orderNum}`).join(', ');
        pendingAdditions.set(waNum, { msgText, pushName, waNum, jid, info: classification.info });
        await sendWA(jid, `🔔 لديك طلب ${orderNums} قيد التنفيذ. هل تريد إضافة المنتجات الجديدة إليه؟\n✅ أرسل "نعم"\n❌ أرسل "لا"`);
        await tgSendToAllAdmins(`📥 طلب إضافة من ${pushName} (${waNum}) لطلب ${orderNums}\nالرسالة: ${msgText.slice(0, 100)}\n🔔 في انتظار رد الزبون`);
        return;
      }
      if (pendingConfirmations.has(waNum)) {
        clearTimeout(pendingConfirmations.get(waNum).timeoutId);
        pendingConfirmations.delete(waNum);
      }
      const info = classification.info;
      const orderNum = ++orderCounter;
      pendingOrders.set(waNum, [{ msgText, pushName, jid, info, orderNum }]);
      processPendingOrder(waNum, orderNum);
      const prods = getProducts(info);
      await sendWA(jid, `✅ تم استلام طلبك #${orderNum}، سيتم تجهيز الفاتورة\n📋 ${formatProductsList(prods)}`);
      await tgSendToAllAdmins(`📥 طلب جديد #${orderNum} من ${pushName} (${waNum})\n${formatProductsList(prods)}\n⚡ جاري المعالجة`);
      return;
    } else {
      await sendWA(jid, '⚠️ لم يتم التعرف على طلب صحيح. يرجى إرسال طلبك مع اسم المنتج والعدد المطلوب.\nمثال: "10 حليب" أو "5 خبز، 20 صمون"');
    }
  });

  try {
    await waClient.initialize();
    waStarting = false;
  } catch (err) {
    const errMsg = err.message?.slice(0, 200) || String(err).slice(0, 200);
    console.log('⚠️ فشل تهيئة واتساب:', errMsg);
    whatsappConnected = false;
    waStarting = false;
    try { waClient.removeAllListeners(); await waClient.destroy(); } catch {}
    waClient = null;
    let wait = 10000;
    if (errMsg.includes('ERR_TIMED_OUT') || errMsg.includes('net::')) {
      wait = 30000;
      console.log('🌐 خطأ شبكة، انتظار أطول قبل إعادة المحاولة...');
    } else if (errMsg.includes('detached') || errMsg.includes('Target closed') || errMsg.includes('Session closed')) {
      wait = 20000;
      console.log('🔌 مشكلة في المتصفح، انتظار قبل إعادة التشغيل...');
    }
    console.log(`🔄 إعادة المحاولة بعد ${wait/1000} ثواني...`);
    setTimeout(startWhatsApp, wait);
  }
}

startWhatsApp();

process.on('unhandledRejection', (err) => {
  const msg = err?.message || '';
  if (msg.includes('read properties of undefined') || msg.includes('resolve') || msg.includes('detached') || msg.includes('Target closed')) return;
  console.error('⚠️ Unhandled Rejection:', msg.slice(0, 200));
});
process.once('SIGINT', () => { process.exit(); });
process.once('SIGTERM', () => { process.exit(); });