# Maintenance Guide - Admin Operations

This guide provides instructions for maintaining the **Arabic Books Publisher** application, updating credentials, monitoring system logs, and backing up databases.

## 1. Monitoring Logs
The system writes plain-text logs to the file `/app/logs/publisher.log` inside the container. 

### Console Logs
Console logs are formatted with colored category tags:
* `[SYSTEM]`: General framework state and scheduler events.
* `[DATABASE]`: Firestore read/write/count queries.
* `[BOOK]`: Downloader and validator metrics (file checking, Arabic language check, covers).
* `[AI]`: Gemini API calls, key changes, and prompt processing.
* `[TELEGRAM]`: Channel scheduling history queries and file transfers.

### Log Rotation & Retention
The system handles log files automatically:
* Every **24 hours**, the scheduler triggers a cleanup job.
* Files are compressed/rotated if they exceed **10 MB** (`config.LOG_MAX_BYTES`).
* Any log file older than **9 days** (`config.LOG_RETENTION_DAYS`) is deleted to prevent container storage exhaustion.

## 2. Managing Credentials (API Keys & Session Rotations)
If a Gemini key is blocked or a Telegram session is banned, the application handles it gracefully using the **Failover Pool**:
- Banned/invalid keys are automatically marked as `INVALID` in memory and skipped.
- Rate-limited keys are set to `RATE_LIMITED` and enter a cooling-off period of **5 minutes**.
- Transient network failures put the key to sleep for **1 minute** (`COOLING_DOWN`).

### How to rotate keys:
1. Generate new keys/sessions.
2. Update the environment secrets in your HuggingFace Spaces Settings tab.
3. HuggingFace will automatically restart the space container with the new environment variables.
4. The **Credential Discovery Engine** will identify the new secrets and load them at startup without requiring any source code modifications.

## 3. Manual Override (Maintenance & Safe Mode Flags)
You can toggle system behavior without redeploying code by changing flags in Firestore or environment variables:

- **MAINTENANCE_MODE**:
  - Set to `True` to temporarily halt all scrapers, downloaders, and Telegram scheduling queues.
  - The web dashboard will remain active and continue serving status reports.
- **SAFE_MODE**:
  - Set to `True` (default) to enforce stricter rate limiting and auto-slowdowns (e.g. increasing delays between successive scraper searches and downloading attempts) when network blocks or API errors are detected.
- **DRY_RUN**:
  - Set to `True` to test scrapers, validation logic, and AI prompt engineering without publishing files to Telegram.

## 4. Backing up Firestore Data
It is highly recommended to export your Firestore database documents once a month. Since the database is relatively small:
1. Navigate to the Google Firebase Console.
2. Select your project.
3. Go to **Firestore Database**.
4. You can use standard Google Cloud SDK commands to export collections to Google Cloud Storage:
   ```bash
   gcloud firestore export gs://your-backup-bucket-name
   ```
5. If you need to rebuild the project database in a different project, you can import this bucket.
