const express = require('express');
const puppeteer = require('puppeteer');
const path = require('path');

const app = express();
// Hugging Face Spaces defaults to port 7860
const PORT = process.env.PORT || 7860;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve the UI
app.get('/', (req, res) => {
    res.send(`
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Puppeteer Screenshot App</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; line-height: 1.6; }
                input[type="text"] { width: 100%; padding: 10px; margin-bottom: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
                button { background-color: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; width: 100%; }
                button:hover { background-color: #0056b3; }
                #result { margin-top: 20px; text-align: center; }
                img { max-width: 100%; border: 1px solid #ddd; border-radius: 4px; margin-top: 10px; }
            </style>
        </head>
        <body>
            <h2>Hugging Face Puppeteer Screenshotter</h2>
            <form action="/screenshot?uiMode=ui" method="POST">
                <label for="url">Enter Website URL:</label>
                <input type="text" id="url" name="url" placeholder="https://example.com" required>
                <button type="submit">Take Screenshot</button>
            </form>
        </body>
        </html>
    `);
});

// Handle the Screenshot requests
app.post('/screenshot', async (req, res) => {
    const { url } = req.body;
    if (!url) return res.status(400).send('URL is required');

    const uiMode = req.query.uiMode || 'api';

    let browser;
    try {
        // Crucial flags for running Puppeteer inside a Docker container safely
        browser = await puppeteer.launch({
            headless: 'shell',
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-zygote'
            ]
        });

        const page = await browser.newPage();
        await page.setViewport({ width: 1920, height: 1080 });
        
        // 1. Wait until DOMContentLoaded with a strict 30s timeout
        await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 120000 });
        
        // 2. Optimized screenshot setup: webp format, returned as a base64 string
        const base64Image = await page.screenshot({ 
            type: 'webp',
            quality: 80, // Optional: adjust quality (0-100) to optimize file size further
            encoding: 'base64',
          fullPage: true
        });

        // Close browser immediately to save RAM
        await browser.close();

        // 3. Return the base64 string. 
        // Wrapping it in an img tag so you can see it instantly, 
        // but you can change this to `res.send(base64Image)` if you just want the raw string payload.

        if(uiMode == 'ui') {
            
        res.set('Content-Type', 'text/html');
        res.send(`
            <h3>Optimized WebP (Base64) Result:</h3>
            <img src="data:image/webp;base64,${base64Image}" alt="Screenshot" />
            <br/><br/>
            <textarea style="width:100%; height:150px;" readonly>data:image/webp;base64,${base64Image}</textarea>
        `);
        } else {
            res.set('Content-Type', 'application/json');

            res.send(JSON.stringify({img : base64Image}));
        }

    } catch (error) {
        if (browser) await browser.close();
        res.status(500).send(`Failed to take screenshot: ${error.message}`);
    }
});

app.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});