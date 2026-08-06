# Deployment

## Netlify — NOT SUPPORTED

This app uses **Python Flask + TensorFlow** (~264MB). Netlify is for static sites and
lightweight serverless functions (50MB limit, 10s timeout). It cannot run this app.

## Railway (recommended — 1-click deploy)

1. Push this repo to GitHub
2. Go to https://railway.app and click **New Project > Deploy from GitHub repo**
3. Railway auto-detects Python, runs `pip install -r requirements.txt`
4. Start command will be picked from `Procfile`: `python app.py --no-ssl`
5. The app reads `$PORT` from Railway's environment automatically

The free tier (~$5/mo credit, no card needed) covers this app.

## Render

1. Push to GitHub
2. Go to https://render.com → **New Web Service**
3. Connect your repo
4. Set:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py --no-ssl`
5. Free tier includes 512MB RAM (enough for TensorFlow CPU)
