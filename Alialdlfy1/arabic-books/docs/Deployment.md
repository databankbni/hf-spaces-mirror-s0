# Deployment Guide - HuggingFace Spaces

This guide walks you through deploying the **Arabic Books Publisher** as a Docker space on HuggingFace, ensuring it runs completely autonomously in the cloud.

## Step 1: Create a New Space on HuggingFace
1. Log in to your [HuggingFace account](https://huggingface.co).
2. Go to **Spaces** and click **Create new Space**.
3. Set the following settings:
   - **Space name**: `arabic-books-publisher` (or choice of your own)
   - **License**: `mit` (or choice of your own)
   - **SDK**: Select **Docker** (Very Important!).
   - **Template**: Choose **Blank** (do not use predefined templates).
   - **Visibility**: Public or Private (Private is recommended to secure logs, though credentials will be hidden in Secrets settings).
4. Click **Create Space**.

## Step 2: Configure Space Secrets (Environment Variables)
Navigate to your Space's page, click on the **Settings** tab, scroll down to the **Variables and secrets** section, and add the following **Secret** keys (do not add them as standard variables to keep them hidden):

| Secret Key | Description | Example / Format |
|---|---|---|
| `TELEGRAM_API_ID` | Telegram API App ID | `1234567` |
| `TELEGRAM_API_HASH` | Telegram API Hash | `your_api_hash_string` |
| `TELEGRAM_SESSION_1` | Telethon Session String for User | `1BJWap1wBu...` |
| `TELEGRAM_BOT_TOKEN_1` | Alternative: Telegram Bot Token | `123456789:ABCDef...` |
| `GEMINI_API_KEY_1` | Primary Gemini API Key | `AIzaSy...` |
| `GEMINI_API_KEY_2` | Secondary Gemini API Key (Failover) | `AIzaSy...` |
| `FIREBASE_SERVICE_ACCOUNT_JSON_B64` | Base64-encoded Service Account JSON | `ewogICJ0eXBlIj...` |
| `DRY_RUN` | Dry-run flag (Set to False for production) | `False` |
| `SAFE_MODE` | Slow down on errors | `True` |

### How to get the Telethon Session String (`TELEGRAM_SESSION`):
You can generate a session string on your local machine by running a quick Python script:
```python
from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = 1234567 # Replace with your API ID
api_hash = "your_hash" # Replace with your API Hash

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("Your Session String:")
    print(client.session.save())
```
Copy the printed long string and save it as `TELEGRAM_SESSION_1` in the HF Secrets.

### How to get Base64 Firebase Credentials (`FIREBASE_SERVICE_ACCOUNT_JSON_B64`):
1. Download your service account JSON file from Firebase Console (Project Settings -> Service Accounts -> Generate new private key).
2. Convert the content of the file to Base64. You can do this via terminal:
   - **Windows PowerShell**:
     ```powershell
     [Convert]::ToBase64String([IO.File]::ReadAllBytes("service-account.json"))
     ```
   - **Linux / macOS**:
     ```bash
     base64 -w 0 service-account.json
     ```
3. Copy the output and save it as `FIREBASE_SERVICE_ACCOUNT_JSON_B64` in the HF Secrets.

## Step 3: Push Code to HuggingFace
HuggingFace Spaces are backed by a Git repository. You can push the codebase directly to the HF remote.

1. Clone your HF space repository locally:
   ```bash
   git clone https://huggingface.co/spaces/YOUR_USERNAME/YOUR_SPACE_NAME
   cd YOUR_SPACE_NAME
   ```
2. Copy all the project files (`app.py`, `config.py`, `Dockerfile`, `requirements.txt`, `VERSION`, `CHANGELOG.md`, `README.md`, `core/`, `database/`, `providers/`, `telegram/`, `books/`, `sources/`, `queue/`, `scheduler/`, `monitoring/`, `ai/`, `utils/`, `docs/`) into the cloned directory.
3. Commit and push the code:
   ```bash
   git add .
   git commit -m "Deploy Arabic Books Publisher Enterprise Edition v1.0"
   git push
   ```

## Step 4: Monitor Build and Deployment
1. Go back to your HuggingFace Space webpage.
2. The space status will change to **Building**. You can click on **See logs** to monitor the progress of the Docker build.
3. Once compiled, the status will change to **Running**.
4. The space screen will render the application's Arabic status dashboard.
5. Watch the **Container logs** tab to see initial logs:
   - Initializing Firestore connection.
   - Running Credential Discovery Engine.
   - Synchronizing Telegram schedules.
   - Replenishing queue.
