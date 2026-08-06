# PowerShell Deployment Script for Google Cloud Run
# Make sure you have Google Cloud SDK installed (gcloud command available)

$ProjectID = Read-Host "Enter your Google Cloud Project ID"
$Region = "us-central1"
$ServiceName = "recommendation-engine"

Write-Host "`n--- Starting Deployment to Google Cloud Run ---" -ForegroundColor Cyan

# 1. Enable billing and required APIs
Write-Host "[1/4] Ensuring APIs are enabled..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com containerregistry.googleapis.com cloudbuild.googleapis.com --project=$ProjectID

# 2. Build the Docker container using Google Cloud Build
Write-Host "[2/4] Building container image using Cloud Build..." -ForegroundColor Yellow
$ImageTag = "gcr.io/$ProjectID/$ServiceName"
gcloud builds submit --tag $ImageTag --project=$ProjectID

# 3. Deploy the container image to Cloud Run
Write-Host "[3/4] Deploying to Cloud Run..." -ForegroundColor Yellow
gcloud run deploy $ServiceName `
    --image $ImageTag `
    --platform managed `
    --region $Region `
    --allow-unauthenticated `
    --project=$ProjectID

# 4. Success message
Write-Host "`n--- Deployment Complete! ---" -ForegroundColor Green
$ServiceUrl = gcloud run services describe $ServiceName --platform managed --region $Region --project=$ProjectID --format="value(status.url)"
Write-Host "Service URL: $ServiceUrl" -ForegroundColor Green
Write-Host "Test URL: $ServiceUrl/recommend?user_id=user_alice" -ForegroundColor Green
