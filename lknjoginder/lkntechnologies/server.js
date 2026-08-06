const express = require('express');
const fs = require('fs');
const path = require('path');
const os = require('os');
const multer = require('multer');

const app = express();
const PORT = 7860;
const SITES_DIR = path.join(__dirname, 'sites');
const DB_FILE = path.join(__dirname, 'database.json');

// Ensure directories and database exist
if (!fs.existsSync(SITES_DIR)) fs.mkdirSync(SITES_DIR, { recursive: true });
if (!fs.existsSync(DB_FILE)) fs.writeFileSync(DB_FILE, JSON.stringify({ clients: [], queries: [] }, null, 2));

// Setup file uploader
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const site = req.query.site || 'client1';
    const dir = path.join(SITES_DIR, site);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    cb(null, dir);
  },
  filename: (req, file, cb) => cb(null, file.originalname)
});
const upload = multer({ storage });

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ==========================================
// 1. MASTER cPANEL & WHM DASHBOARD
// ==========================================
app.get(['/', '/admin', '/cpanel'], (req, res) => {
  const sites = fs.readdirSync(SITES_DIR);
  const dbData = JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));

  res.send(`
    <html>
      <head>
        <title>LKN Technologies - Cloud cPanel & WHM</title>
        <style>
          body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }
          .navbar { background: #1e293b; padding: 15px 25px; border-radius: 8px; border-left: 5px solid #ff6c2c; display: flex; justify-content: space-between; align-items: center; }
          .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-top: 20px; }
          .card { background: #1e293b; padding: 20px; border-radius: 10px; border: 1px solid #334155; }
          h2 { color: #38bdf8; font-size: 18px; margin-top: 0; border-bottom: 1px solid #334155; padding-bottom: 10px; display: flex; align-items: center; gap: 8px; }
          .btn { background: #ff6c2c; color: white; padding: 8px 14px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; font-size: 13px; font-weight: bold; margin-top: 5px; }
          .btn-blue { background: #0284c7; }
          .btn-green { background: #10b981; }
          input, select { padding: 8px; background: #0f172a; border: 1px solid #334155; color: white; border-radius: 4px; width: 100%; margin-bottom: 10px; box-sizing: border-box; }
          ul { list-style: none; padding: 0; }
          li { background: #0f172a; padding: 10px; margin: 6px 0; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #1e293b; }
          code { color: #38bdf8; }
        </style>
      </head>
      <body>
        <div class="navbar">
          <div><h1 style="margin:0;font-size:22px;color:#ff6c2c;">🟧 LKN Cloud cPanel & WHM <span style="font-size:12px;background:#10b981;color:white;padding:3px 8px;border-radius:12px;">● RUNNING ON HUGGINGFACE</span></h1></div>
          <div><span style="color:#94a3b8;">RAM: ${(os.totalmem()/1024/1024/1024).toFixed(1)} GB | Port: 7860</span></div>
        </div>

        <div class="grid">
          <!-- 1. SOFTACULOUS STYLE 1-CLICK INSTALLER -->
          <div class="card">
            <h2>⚡ Softaculous 1-Click App Installer</h2>
            <p style="font-size:13px;color:#94a3b8;">Install instant website templates into any domain folder:</p>
            <form action="/install-app" method="POST">
              <label>Select Client Folder:</label>
              <input type="text" name="siteName" placeholder="e.g. client1, startup, shop" required>
              <label>Select App Template:</label>
              <select name="appType">
                <option value="startup">🚀 IT Services Startup Website</option>
                <option value="shop">🛒 E-Commerce Shop Template</option>
                <option value="blog">📝 Modern Blog & CMS</option>
              </select>
              <button type="submit" class="btn btn-green" style="width:100%;">⚡ 1-Click Install Now</button>
            </form>
          </div>

          <!-- 2. HOSTED DOMAINS & FILE MANAGER -->
          <div class="card">
            <h2>🌐 Addon Domains & File Manager</h2>
            <p style="font-size:13px;color:#94a3b8;">Active website folders in <code>/sites/</code>:</p>
            <ul>
              ${sites.map(s => `
                <li>
                  <span>📁 <b>${s}</b></span>
                  <div>
                    <a href="/site/${s}" target="_blank" class="btn btn-blue">View Live</a>
                    <a href="/files?site=${s}" class="btn">Manage Files</a>
                  </div>
                </li>`).join('') || '<p style="color:#64748b;">No sites yet. Install one above!</p>'}
            </ul>
          </div>

          <!-- 3. DATABASE MANAGER (phpMyAdmin style) -->
          <div class="card">
            <h2>🐬 Database Manager (SQL / JSON)</h2>
            <p style="font-size:13px;color:#94a3b8;">Active Database: <code>database.json (Connected)</code></p>
            <p style="font-size:14px;"><b>Stored Clients / Records:</b> ${dbData.clients.length}</p>
            <form action="/add-db-record" method="POST" style="display:flex;gap:5px;">
              <input type="text" name="clientName" placeholder="New Client DB Record Name..." required style="margin:0;">
              <button type="submit" class="btn btn-blue" style="margin:0;">+ Add DB Record</button>
            </form>
            <ul style="max-height:120px;overflow-y:auto;margin-top:10px;">
              ${dbData.clients.map(c => `<li><span>🗄️ ${c.name}</span> <span style="font-size:11px;color:#64748b;">${c.date}</span></li>`).join('')}
            </ul>
          </div>

          <!-- 4. DNS ZONE & ROUTING -->
          <div class="card">
            <h2>🌍 DNS Zone Editor & Routing</h2>
            <p style="font-size:13px;color:#cbd5e1;line-height:1.6;">
              <b>How to connect custom domain in Cloudflare:</b><br>
              1. Type: <code>CNAME</code><br>
              2. Name: <code>www</code> or <code>@</code><br>
              3. Target: <code>your-space-name.hf.space</code><br>
              4. When visitors open your domain, Port 7860 routes them to their exact site folder!
            </p>
          </div>
        </div>
      </body>
    </html>
  `);
});

// ==========================================
// 2. SOFTACULOUS 1-CLICK INSTALLER LOGIC
// ==========================================
app.post('/install-app', (req, res) => {
  const { siteName, appType } = req.body;
  const dir = path.join(SITES_DIR, siteName);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

  let htmlContent = '';
  if (appType === 'startup') {
    htmlContent = `<body style="background:#0b0f19;color:#fff;font-family:sans-serif;text-align:center;padding:60px;"><h1 style="color:#38bdf8;font-size:40px;">🚀 ${siteName.toUpperCase()} - IT Services & Cloud Consulting</h1><p style="font-size:20px;color:#94a3b8;">Enterprise Software Development • Cyber Security • DevOps Migration</p><button style="background:#0284c7;color:white;padding:12px 25px;border:none;border-radius:6px;font-size:16px;margin-top:20px;">Contact Our IT Team</button></body>`;
  } else if (appType === 'shop') {
    htmlContent = `<body style="background:#111;color:#fff;font-family:sans-serif;text-align:center;padding:60px;"><h1 style="color:#10b981;font-size:40px;">🛒 ${siteName.toUpperCase()} - E-Commerce Store</h1><p style="font-size:20px;">Premium IT Hardware • Laptops • Cloud Servers</p><div style="display:inline-block;border:1px solid #333;padding:20px;border-radius:10px;margin-top:20px;"><h3>Enterprise Server Blade</h3><p color="#10b981">$999.00</p><button style="background:#10b981;color:white;padding:10px 20px;border:none;border-radius:5px;">Buy Now</button></div></body>`;
  } else {
    htmlContent = `<body style="background:#1e1e24;color:#fff;font-family:sans-serif;text-align:center;padding:60px;"><h1 style="color:#ff6c2c;font-size:40px;">📝 ${siteName.toUpperCase()} - Tech Blog & News</h1><p>Latest updates in AI, Cloud Computing, and Server Architecture.</p><hr style="border-top:1px solid #333;margin:30px 0;"><p>Article: How LKN Technologies built a cPanel inside Hugging Face!</p></body>`;
  }

  fs.writeFileSync(path.join(dir, 'index.html'), htmlContent);
  res.redirect('/?installed=' + siteName);
});

// ==========================================
// 3. FILE MANAGER & UPLOADER LOGIC
// ==========================================
app.get('/files', (req, res) => {
  const site = req.query.site || 'client1';
  const dir = path.join(SITES_DIR, site);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  const files = fs.readdirSync(dir);

  res.send(`
    <body style="background:#0f172a;color:#fff;font-family:sans-serif;padding:30px;">
      <h2>📂 File Manager for folder: <code>/sites/${site}</code></h2>
      <a href="/" style="color:#38bdf8;">⬅️ Back to WHM Dashboard</a>
      <hr style="border-top:1px solid #334155;margin:20px 0;">
      <form action="/upload-file?site=${site}" method="POST" enctype="multipart/form-data" style="background:#1e293b;padding:15px;border-radius:8px;">
        <b>⬆️ Upload Website File (HTML/CSS/Images):</b><br><br>
        <input type="file" name="file" required style="background:transparent;border:none;">
        <button type="submit" style="background:#10b981;color:white;padding:8px 15px;border:none;border-radius:5px;cursor:pointer;">Upload to ${site}</button>
      </form>
      <h3>Files in Folder:</h3>
      <ul>
        ${files.map(f => `<li style="background:#1e293b;padding:10px;margin:5px 0;border-radius:5px;">📄 <b>${f}</b> (${(fs.statSync(path.join(dir,f)).size/1024).toFixed(1)} KB)</li>`).join('') || '<p>Folder is empty</p>'}
      </ul>
    </body>
  `);
});

app.post('/upload-file', upload.single('file'), (req, res) => {
  res.redirect('/files?site=' + req.query.site);
});

// ==========================================
// 4. DATABASE RECORD LOGIC
// ==========================================
app.post('/add-db-record', (req, res) => {
  const dbData = JSON.parse(fs.readFileSync(DB_FILE, 'utf8'));
  dbData.clients.push({ name: req.body.clientName, date: new Date().toLocaleString() });
  fs.writeFileSync(DB_FILE, JSON.stringify(dbData, null, 2));
  res.redirect('/');
});

// ==========================================
// 5. MULTI-DOMAIN REVERSE ROUTER
// ==========================================
app.use('/site/:name', (req, res, next) => {
  const dir = path.join(SITES_DIR, req.params.name);
  express.static(dir)(req, res, next);
});

app.listen(PORT, '0.0.0.0', () => console.log(`LKN Cloud cPanel & WHM running on Port ${PORT}`));