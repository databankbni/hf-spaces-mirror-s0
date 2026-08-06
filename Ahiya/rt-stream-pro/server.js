const express = require('express');
const { spawn } = require('child_process');
const app = express();
const port = 7860;

app.use(express.urlencoded({ extended: true }));

let ffmpegProcess = null;
let lastData = { url: '', key: '', quality: '2500k' };

app.get('/', (req, res) => {
    res.send(`
    <html>
    <body style="background:#111; color:#fff; font-family:sans-serif; text-align:center; padding:20px;">
        <h2>RT PRO - STABLE ENGINE</h2>
        <p>Status: <b style="color:${ffmpegProcess ? '#0f0' : '#f00'}">${ffmpegProcess ? 'LIVE RUNNING (Stable)' : 'OFFLINE'}</b></p>
        <form action="/start" method="POST">
            <input type="text" name="url" value="${lastData.url}" placeholder="Video MP4 URL" style="width:80%; padding:10px; margin:5px;"><br>
            <input type="text" name="key" value="${lastData.key}" placeholder="Stream Key" style="width:80%; padding:10px; margin:5px;"><br>
            <select name="quality" style="width:80%; padding:10px; margin:5px;">
                <option value="2500k" ${lastData.quality === '2500k' ? 'selected' : ''}>2500 kbps (Stable)</option>
                <option value="4000k" ${lastData.quality === '4000k' ? 'selected' : ''}>4000 kbps (HD)</option>
            </select><br>
            <button type="submit" style="padding:15px 30px; background:#2ecc71; color:white; border:none; cursor:pointer;">GO LIVE</button>
        </form>
        <form action="/stop" method="POST">
            <button type="submit" style="padding:10px 20px; background:#e74c3c; color:white; border:none; cursor:pointer; margin-top:10px;">STOP</button>
        </form>
    </body>
    </html>`);
});

app.post('/start', (req, res) => {
    lastData = req.body;
    if (ffmpegProcess) ffmpegProcess.kill('SIGKILL');

    // YouTube ke liye "smooth streaming" settings
    ffmpegProcess = spawn('ffmpeg', [
        '-re',
        '-stream_loop', '-1',
        '-i', lastData.url,
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-tune', 'zerolatency',
        '-b:v', lastData.quality,
        '-maxrate', lastData.quality,
        '-bufsize', '2000k', // YouTube ke liye zaroori buffer
        '-g', '60',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-ar', '44100',
        '-f', 'flv',
        `rtmp://a.rtmp.youtube.com/live2/${lastData.key}`
    ]);

    ffmpegProcess.stderr.on('data', (d) => console.log(`FFmpeg: ${d}`));
    res.redirect('/');
});

app.post('/stop', (req, res) => {
    if (ffmpegProcess) ffmpegProcess.kill('SIGKILL');
    ffmpegProcess = null;
    res.redirect('/');
});

app.listen(port);
