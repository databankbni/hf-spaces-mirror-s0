const express = require('express');
const cors = require('cors');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { commit } = require('@huggingface/hub');
require('dotenv').config();

const app = express();
const port = process.env.PORT || 7860; // HF Spaces uses 7860

// Configure Multer for in-memory file uploads
const upload = multer({ storage: multer.memoryStorage() });

app.use(cors());
app.use(express.json());

// Secure admin route (Basic Auth placeholder, can be enhanced)
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin123';

app.post('/api/auth', (req, res) => {
    if (req.body.password === ADMIN_PASSWORD) {
        res.json({ success: true, token: 'temp-admin-token' });
    } else {
        res.status(401).json({ success: false, error: 'Invalid password' });
    }
});

// The Publish API: Receives files and config, commits them to Hugging Face
app.post('/api/publish', upload.fields([
    { name: 'caricature', maxCount: 1 },
    { name: 'backgroundMusic', maxCount: 1 }
]), async (req, res) => {
    // Check simple token
    if (req.headers.authorization !== 'Bearer temp-admin-token') {
        return res.status(401).json({ error: 'Unauthorized' });
    }

    try {
        const clientName = req.body.clientName;
        if (!clientName) return res.status(400).json({ error: 'clientName is required' });

        const configJson = req.body.configJson;
        
        const operations = [];

        // 1. Add config.json
        if (configJson) {
            operations.push({
                operation: "addOrUpdate",
                path: `event/${clientName}/config.json`,
                content: new Blob([configJson], { type: 'application/json' })
            });
        }

        // 2. Add uploaded files
        if (req.files && req.files.caricature) {
            operations.push({
                operation: "addOrUpdate",
                path: `event/${clientName}/caricature.png`,
                content: new Blob([req.files.caricature[0].buffer])
            });
        }

        if (req.files && req.files.backgroundMusic) {
            operations.push({
                operation: "addOrUpdate",
                path: `event/${clientName}/background.mp3`,
                content: new Blob([req.files.backgroundMusic[0].buffer])
            });
        }

        // Commit to Hugging Face
        const commitInfo = await commit({
            repo: { type: "space", name: "KVEvenTech/invite" },
            credentials: { accessToken: process.env.HF_TOKEN },
            title: `Auto-Deploy: Generated new invitation for ${clientName}`,
            operations: operations
        });

        res.json({ success: true, url: `/event/${clientName}/`, commit: commitInfo });

    } catch (error) {
        console.error("Deploy Error:", error);
        res.status(500).json({ success: false, error: error.message });
    }
});

app.get('/', (req, res) => {
    res.redirect('/admin/index.html');
});



// Dynamic routing for the unified React Frontend Engine
app.get('/event/:clientName', (req, res, next) => {
    // Exclude API or static file requests (e.g. .css, .js, .png, .json)
    if (req.path.includes('.')) {
        return next();
    }

    const clientName = req.params.clientName;
    let indexPath = path.join(__dirname, 'event', clientName, 'index.html');
    const configPath = path.join(__dirname, 'event', clientName, 'config.json');

    if (!fs.existsSync(indexPath)) {
        indexPath = path.join(__dirname, 'index.html');
    }

    fs.readFile(indexPath, 'utf8', (err, htmlData) => {
        if (err) return res.status(500).send('Error reading index.html');

        // Try to read client config to inject Open Graph tags
        fs.readFile(configPath, 'utf8', (err, configDataStr) => {
            if (!err) {
                try {
                    const config = JSON.parse(configDataStr);
                    const nameStr = config.groomName ? `${config.brideName} & ${config.groomName}` : config.brideName;
                    const ceremonyTitle = config.events?.halfSaree?.title || 'Wedding Ceremony';
                    const title = `${nameStr} — ${ceremonyTitle}`;
                    const description = config.intro?.sequenceInvite || 'You are invited to celebrate with us.';
                    const ogImage = `https://kveventech-invite.hf.space/event/${clientName}/caricature.png`;
                    
                    // Replace generic tags with specific tags in a highly robust way
                    htmlData = htmlData.replace(/<title>.*<\/title>/i, `<title>${title}</title>`);
                    
                    htmlData = htmlData.replace(/<meta\s+property="og:title"\s+content="[^"]*"\s*\/?>|<meta\s+content="[^"]*"\s+property="og:title"\s*\/?>/i, `<meta property="og:title" content="${title}" />`);
                    htmlData = htmlData.replace(/<meta\s+name="twitter:title"\s+content="[^"]*"\s*\/?>|<meta\s+content="[^"]*"\s+name="twitter:title"\s*\/?>/i, `<meta name="twitter:title" content="${title}" />`);
                    
                    htmlData = htmlData.replace(/<meta\s+name="description"\s+content="[^"]*"\s*\/?>|<meta\s+content="[^"]*"\s+name="description"\s*\/?>/i, `<meta name="description" content="${description}" />`);
                    htmlData = htmlData.replace(/<meta\s+property="og:description"\s+content="[^"]*"\s*\/?>|<meta\s+content="[^"]*"\s+property="og:description"\s*\/?>/i, `<meta property="og:description" content="${description}" />`);
                    htmlData = htmlData.replace(/<meta\s+name="twitter:description"\s+content="[^"]*"\s*\/?>|<meta\s+content="[^"]*"\s+name="twitter:description"\s*\/?>/i, `<meta name="twitter:description" content="${description}" />`);
                    
                    htmlData = htmlData.replace(/<meta\s+property="og:image"\s+content="[^"]*"\s*\/?>|<meta\s+content="[^"]*"\s+property="og:image"\s*\/?>/i, `<meta property="og:image" content="${ogImage}" />`);
                    htmlData = htmlData.replace(/<meta\s+name="twitter:image"\s+content="[^"]*"\s*\/?>|<meta\s+content="[^"]*"\s+name="twitter:image"\s*\/?>/i, `<meta name="twitter:image" content="${ogImage}" />`);
                    
                    htmlData = htmlData.replace(/<meta\s+property="og:url"\s+content="[^"]*"\s*\/?>|<meta\s+content="[^"]*"\s+property="og:url"\s*\/?>/i, `<meta property="og:url" content="https://kveventech-invite.hf.space/event/${clientName}/" />`);
                } catch (e) {
                    console.error("Error parsing config for OG tags", e);
                }
            }
            res.send(htmlData);
        });
    });
});

// Serve static files (this serves assets, admin portal, etc.)
app.use(express.static(__dirname));


// Shared Wishes API (real-time sync across devices)
const WISHES_FILE = path.join(__dirname, 'wishes.json');

const defaultWishes = [
    { name: "The Fernandes Family", message: "Wishing you both a lifetime of love, laughter, and endless happiness! 🥂", style: "gold" },
    { name: "Rahul & Sneha", message: "So thrilled to witness your beautiful union. Congratulations guys! ✨", style: "navy" },
    { name: "Aunt Maria", message: "May God shower your marriage with abundant blessings and joy. 🤍", style: "white" }
];

app.get('/api/wishes', (req, res) => {
    const eventName = req.query.event || 'default';
    const eventWishesFile = path.join(__dirname, `wishes_${eventName}.json`);
    
    fs.readFile(eventWishesFile, 'utf8', (err, data) => {
        if (err) {
            return res.json(defaultWishes);
        }
        try {
            const wishes = JSON.parse(data);
            res.json(wishes);
        } catch (e) {
            res.json(defaultWishes);
        }
    });
});

app.post('/api/wishes', (req, res) => {
    const { name, message, style } = req.body;
    const eventName = req.query.event || 'default';
    const eventWishesFile = path.join(__dirname, `wishes_${eventName}.json`);
    
    if (!name || !message) {
        return res.status(400).json({ error: 'Name and message are required' });
    }

    fs.readFile(eventWishesFile, 'utf8', (err, data) => {
        let wishes = [];
        if (!err) {
            try {
                wishes = JSON.parse(data);
            } catch (e) {
                wishes = [...defaultWishes];
            }
        } else {
            wishes = [...defaultWishes];
        }

        wishes.unshift({ name, message, style, date: new Date().toISOString() });

        fs.writeFile(eventWishesFile, JSON.stringify(wishes, null, 2), 'utf8', async (writeErr) => {
            if (writeErr) {
                console.error("Error writing wishes file:", writeErr);
            }

            // Automatically commit wishes.json back to the Hugging Face space repository for permanent persistence
            try {
                if (process.env.HF_TOKEN) {
                    await commit({
                        repo: { type: "space", name: "KVEvenTech/invite" },
                        credentials: { accessToken: process.env.HF_TOKEN },
                        title: `Wishes Wall: New blessing from ${name}`,
                        operations: [{
                            operation: "addOrUpdate",
                            path: "wishes.json",
                            content: new Blob([JSON.stringify(wishes, null, 2)], { type: 'application/json' })
                        }]
                    });
                    console.log("Wishes committed to HF Space successfully.");
                }
            } catch (commitErr) {
                console.error("Failed to commit wishes to HF Space:", commitErr);
            }

            res.json({ success: true, wishes });
        });
    });
});

// Health check endpoint for cronjob pings to keep the space awake
app.get('/api/health', (req, res) => {
    res.json({ status: 'ok', timestamp: new Date().toISOString(), uptime: process.uptime() });
});

// Serve all static files (HTML, assets, images, audio, etc.)
app.use(express.static(path.join(__dirname), {
    setHeaders: (res, filePath) => {
        if (filePath.endsWith('.webp') || filePath.endsWith('.jpg') || filePath.endsWith('.png')) {
            res.setHeader('Cache-Control', 'public, max-age=86400');
        }
    }
}));

// SPA fallback — serve index.html for any /event/* routes not matched above
app.get('/event/:eventName', (req, res) => {
    const eventName = req.params.eventName;
    const eventIndex = path.join(__dirname, 'event', eventName, 'index.html');
    if (fs.existsSync(eventIndex)) {
        res.sendFile(eventIndex);
    } else {
        res.status(404).send('Event not found');
    }
});

// Root fallback
app.get('/{*path}', (req, res) => {
    const rootIndex = path.join(__dirname, 'index.html');
    if (fs.existsSync(rootIndex)) {
        res.sendFile(rootIndex);
    } else {
        res.status(404).send('Not found');
    }
});

// Self-ping every 25 minutes to keep the HF Space awake
const SPACE_URL = process.env.SPACE_URL || 'https://kveventech-invite.hf.space';
setInterval(async () => {
    try {
        const http = require('https');
        http.get(`${SPACE_URL}/api/health`, (res) => {
            console.log(`[Keep-alive] Self-ping status: ${res.statusCode}`);
        }).on('error', (e) => {
            console.warn('[Keep-alive] Self-ping failed:', e.message);
        });
    } catch (e) {
        console.warn('[Keep-alive] Error:', e.message);
    }
}, 25 * 60 * 1000);

app.listen(port, () => {
    console.log(`Server listening on port ${port}`);
});
