# Cloud Run Deployment Checklist

## Pre-Deployment Checklist

### 1. Environment Variables
Ensure these are set in Cloud Run (or will be set during deployment):
- ✅ `FIREBASE_PROJECT_ID=auth-demo-90be0`
- ✅ `GOOGLE_CLOUD_PROJECT=precepgo-mentor-ai`
- ✅ `GOOGLE_CLOUD_REGION=us-central1`
- ✅ `USE_VECTOR_SEARCH=true`
- ✅ `GEMINI_API_KEY` (set as secret or env var)

### 2. APIs Enabled
- ✅ Cloud Build API
- ✅ Cloud Run API
- ✅ Firestore API (for auth-demo-90be0)
- ✅ Vertex AI API (aiplatform.googleapis.com)
- ✅ Gemini for Google Cloud API (cloudaicompanion.googleapis.com) - **Required for Vertex AI GenerativeModel**

### 3. Permissions
- ✅ Cloud Run service account has Firestore access to `auth-demo-90be0`

## Deployment Steps

### Option 1: Automated Deployment Script
```bash
./deploy_to_cloud_run.sh
```

### Option 2: Manual Deployment

1. **Build and push image:**
```bash
PROJECT_ID="precepgo-mentor-ai"
SERVICE_NAME="precepgo-adk-panel"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

gcloud builds submit --tag ${IMAGE_NAME} --timeout=20m
```

2. **Deploy to Cloud Run:**
```bash
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --update-env-vars "FIREBASE_PROJECT_ID=auth-demo-90be0,USE_VECTOR_SEARCH=true,GOOGLE_CLOUD_PROJECT=precepgo-mentor-ai,GOOGLE_CLOUD_REGION=us-central1" \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10
```

3. **Grant Firestore permissions:**
```bash
# Get service account
PROJECT_NUMBER=$(gcloud projects describe precepgo-mentor-ai --format="value(projectNumber)")
CLOUD_RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

# Grant access
gcloud projects add-iam-policy-binding auth-demo-90be0 \
  --member="serviceAccount:${CLOUD_RUN_SA}" \
  --role="roles/datastore.user"
```

## Post-Deployment Verification

1. **Check health endpoint:**
```bash
SERVICE_URL=$(gcloud run services describe precepgo-adk-panel --region us-central1 --format="value(status.url)")
curl ${SERVICE_URL}/health
```

Expected response:
```json
{
  "status": "healthy",
  "mcp_url_configured": false,
  "firestore_available": true
}
```

2. **Test scenario generation:**
```bash
curl -X POST ${SERVICE_URL}/mentor/make-scenario \
  -H "Content-Type: application/json"
```

3. **Check logs:**
```bash
gcloud run logs read precepgo-adk-panel --region us-central1 --limit 50
```

## Troubleshooting

### Firestore Connection Issues
- Verify `FIREBASE_PROJECT_ID=auth-demo-90be0` is set
- Check Cloud Run service account has `roles/datastore.user` on `auth-demo-90be0`
- Verify Firestore API is enabled for `auth-demo-90be0`

### Build Failures
- Check Dockerfile syntax
- Verify all required files are copied (data/*.json)
- Check requirements.txt is complete

### Runtime Errors
- Check logs: `gcloud run logs read precepgo-adk-panel --region us-central1`
- Verify environment variables are set correctly
- Check service account permissions

