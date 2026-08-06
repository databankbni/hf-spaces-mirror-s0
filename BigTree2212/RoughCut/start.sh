#!/bin/bash
set -e

# bgutil-pot runs as a background sidecar, loopback-only -- yt-dlp reaches it
# over http://127.0.0.1:4416 via the youtubepot-bgutilhttp extractor-args.
# The plugin degrades gracefully if the server isn't reachable yet (skips
# the token instead of hard-failing), so we don't block startup waiting on
# it -- just give it a moment's head start before gunicorn takes traffic.
bgutil-pot server --host 127.0.0.1 --port 4416 &
sleep 1

# Optional: a logged-in YouTube session as an extra signal alongside the PO
# Token, for requests the token alone still can't clear. HF Space secrets are
# plain env vars (not files), so the cookies.txt (Netscape format) is stored
# base64-encoded in the YOUTUBE_COOKIES_B64 secret and decoded back to a real
# file here, once, at container start -- never committed to the repo.
if [ -n "$YOUTUBE_COOKIES_B64" ]; then
  echo "$YOUTUBE_COOKIES_B64" | base64 -d > "$HOME/app/youtube_cookies.txt"
  export YOUTUBE_COOKIES_FILE="$HOME/app/youtube_cookies.txt"
fi

exec gunicorn --bind 0.0.0.0:7860 --workers 1 --threads 4 --timeout 0 app:app
