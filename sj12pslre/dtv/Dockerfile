FROM python:3.9-slim

# Default shell
SHELL ["/bin/bash", "-c"]

# FFmpeg, Fonts, Timezone, curl, procps install karna
RUN apt-get update && apt-get install -y ffmpeg fontconfig fonts-dejavu-core tzdata curl procps psmisc && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app
RUN mkdir -p $HOME/app/stream

# Simple 24/7 RTMP Restream Script with Bottom-Right Telegram Watermark
RUN cat << 'EOF' > run.sh
#!/bin/bash
FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf

# ⚡ MULTI-THREADED Python Server (No Buffering) ⚡
cat << 'PYEOF' > /home/user/app/server.py
import http.server, socketserver
class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()
class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
server = ThreadingServer(("", 7860), Handler)
server.serve_forever()
PYEOF

cd /home/user/app/stream && python3 /home/user/app/server.py &

# ==========================================
# 📺 AAPKA NAYA 24/7 LIVE CHANNEL LINK (INPUT) 📺
# ==========================================
LIVE_LINK="http://miarea.vip:8080/AsgarDiscord/TubnaAl2fi/36029"

# ==========================================
# 🚀 AAPKA USCREEN RTMP SERVER (OUTPUT) 🚀
# ==========================================
RTMP_URL="rtmp://global-live.uscreen.app:5222/app/9a6f0189-f1ab-eb88-e5f6-27cd2845fe64"

while true; do
  # Purana cache clean karna
  killall -9 ffmpeg 2>/dev/null
  
  echo "Starting 1080p RTMP Push to Uscreen with Bottom-Right Watermark..."
  
  # 🚨 PURE 1080p RTMP PUSH ENGINE WITH STRICT VLC HEADERS & BOTTOM RIGHT TEXT 🚨
  ffmpeg -thread_queue_size 1024 -reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5 \
  -headers $'User-Agent: VLC/3.0.16 LibVLC/3.0.16\r\nAccept: */*\r\nConnection: keep-alive\r\n' \
  -user_agent "VLC/3.0.16 LibVLC/3.0.16" \
  -fflags +genpts+discardcorrupt -i "$LIVE_LINK" \
  -vf "scale=1920:1080,format=yuv420p,drawtext=fontfile=${FONT}:text='Join Telegram - @dtv_hindi':fontcolor=white:fontsize=40:x=W-tw-40:y=H-th-40" \
  -c:v libx264 -preset veryfast -tune zerolatency -profile:v main -flags +cgop -b:v 4500k -maxrate 5500k -bufsize 11000k -g 60 -sc_threshold 0 \
  -threads 0 -c:a aac -ar 48000 -ac 2 -b:a 128k \
  -f flv "$RTMP_URL" > /home/user/app/stream/ffmpeg.log 2>&1
  
  # Agar stream backend se disconnect hoti hai toh 2 second baad auto-restart ho jayegi
  sleep 2
done
EOF

RUN chmod +x run.sh

EXPOSE 7860
CMD ["./run.sh"]
