---
title: Vibe Feed Backend
emoji: 🎥
colorFrom: purple
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Video Recommendation Engine API (Hugging Face Backend)

This is a serverless Python FastAPI recommendation backend designed for a video-based social media application. It is ready for local testing and direct deployment to **Google Cloud Run**.

## Project Files
* [main.py](file:///C:/Users/Akhilesh/.gemini/antigravity/scratch/video-social-backend/main.py): Contains the FastAPI code, mockup user interest tags, and scoring logic.
* [Dockerfile](file:///C:/Users/Akhilesh/.gemini/antigravity/scratch/video-social-backend/Dockerfile): Configures the Docker container for production.
* [requirements.txt](file:///C:/Users/Akhilesh/.gemini/antigravity/scratch/video-social-backend/requirements.txt): Lists dependencies (FastAPI, Uvicorn, etc.).
* [deploy.ps1](file:///C:/Users/Akhilesh/.gemini/antigravity/scratch/video-social-backend/deploy.ps1): A PowerShell script to build and deploy to Google Cloud Run.

---

## 1. Run & Test Locally

You can test the API locally in PowerShell before deploying it.

### Step 1: Install Dependencies
Create a virtual environment (optional but recommended) and install:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Step 2: Run the Server
```powershell
python main.py
```
The server will start on `http://localhost:8080`.

### Step 3: Test the Recommendations
Open your browser or run a GET request to:
* Root endpoint: `http://localhost:8080/`
* Alice (personalized recommendations for tech/webdev): `http://localhost:8080/recommend?user_id=user_alice`
* Bob (personalized recommendations for gaming/music): `http://localhost:8080/recommend?user_id=user_bob`
* Unknown User (popular videos fallback): `http://localhost:8080/recommend?user_id=unknown_user`

---

## 2. Deploy to Google Cloud Run

To deploy your backend to Cloud Run, you need the **Google Cloud SDK (gcloud CLI)** installed on your machine.

### Option A: Use the Automation Script
Open PowerShell in this directory and execute:
```powershell
.\deploy.ps1
```
The script will ask for your **GCP Project ID**, automatically enable the required Cloud Run & Cloud Build APIs, compile your container on Google Cloud Build, and deploy it to a serverless Cloud Run instance.

### Option B: Manual Deploy Commands
If you prefer running commands step-by-step:

1. **Log in to your Google Account:**
   ```powershell
   gcloud auth login
   ```
2. **Set your current project:**
   ```powershell
   gcloud config set project YOUR_PROJECT_ID
   ```
3. **Build the container using Cloud Build:**
   ```powershell
   gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/recommendation-engine
   ```
4. **Deploy to Cloud Run:**
   ```powershell
   gcloud run deploy recommendation-engine --image gcr.io/YOUR_PROJECT_ID/recommendation-engine --platform managed --region us-central1 --allow-unauthenticated
   ```

---

## 3. How to Connect to Firebase Hosting

Once your Cloud Run service is deployed, you'll receive a service URL (e.g. `https://recommendation-engine-xxxxxx.a.run.app`). You can link this directly to your Firebase Frontend:

1. **Direct API Call:**
   In your client application frontend code (HTML/JS), fetch recommendations using the URL:
   ```javascript
   const userId = "user_alice";
   const response = await fetch(`https://YOUR_CLOUD_RUN_URL/recommend?user_id=${userId}`);
   const data = await response.json();
   console.log(data.recommendations);
   ```

2. **Rewrite via Firebase Hosting (Optional - avoids CORS configuration):**
   If you want to proxy requests through your Firebase Hosting domain, edit your `firebase.json` configuration file to include a rewrite rule:
   ```json
   {
     "hosting": {
       "rewrites": [
         {
           "source": "/api/**",
           "run": {
             "serviceId": "recommendation-engine",
             "region": "us-central1"
           }
         }
       ]
     }
   }
   ```
   Now, any request to `https://your-firebase-subdomain.web.app/api/recommend?user_id=user_alice` will be securely proxied to your Cloud Run recommendation service.
