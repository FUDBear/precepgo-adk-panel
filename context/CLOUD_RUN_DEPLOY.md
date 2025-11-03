# Cloud Run Deployment Guide

## Quick Deploy

Run the deployment script:
```bash
./deploy_to_cloud_run.sh
```

## Manual Deployment Steps

### 1. Build and Push Container Image
```bash
PROJECT_ID="precepgo-mentor-ai"
SERVICE_NAME="precepgo-adk-panel"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

# Build and push
gcloud builds submit --tag ${IMAGE_NAME} --timeout=20m
```

### 2. Deploy to Cloud Run
```bash
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --set-env-vars "GEMINI_API_KEY=your-key,FIREBASE_PROJECT_ID=auth-demo-90be0,USE_VECTOR_SEARCH=true,GOOGLE_CLOUD_PROJECT=precepgo-mentor-ai,GOOGLE_CLOUD_REGION=us-central1" \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10
```

### 3. Set Environment Variables in Cloud Run Console

Go to: https://console.cloud.google.com/run/detail/us-central1/precepgo-adk-panel/environment-variables

Set these variables:
- `GEMINI_API_KEY` - Your Gemini API key
- `FIREBASE_PROJECT_ID` - `auth-demo-90be0`
- `USE_VECTOR_SEARCH` - `true`
- `GOOGLE_CLOUD_PROJECT` - `precepgo-mentor-ai`
- `GOOGLE_CLOUD_REGION` - `us-central1`

### 4. Grant Firestore Permissions

Grant the Cloud Run service account access to Firebase:

```bash
# Get Cloud Run service account
CLOUD_RUN_SA=$(gcloud run services describe precepgo-adk-panel \
  --region us-central1 \
  --format="value(spec.template.spec.serviceAccountName)")

# If empty, use default compute service account
if [ -z "$CLOUD_RUN_SA" ]; then
  CLOUD_RUN_SA="724021185717-compute@developer.gserviceaccount.com"
fi

# Grant Firestore access
gcloud projects add-iam-policy-binding auth-demo-90be0 \
  --member="serviceAccount:${CLOUD_RUN_SA}" \
  --role="roles/datastore.user"
```

### 5. Verify Deployment

```bash
# Get service URL
SERVICE_URL=$(gcloud run services describe precepgo-adk-panel \
  --region us-central1 \
  --format="value(status.url)")

# Test health endpoint
curl ${SERVICE_URL}/health

# Test dashboard
open ${SERVICE_URL}/dashboard
```

## Environment Variables Required

| Variable | Value | Required |
|----------|-------|----------|
| `GEMINI_API_KEY` | Your Gemini API key | ✅ Yes |
| `FIREBASE_PROJECT_ID` | `auth-demo-90be0` | ✅ Yes |
| `USE_VECTOR_SEARCH` | `true` | ✅ Yes |
| `GOOGLE_CLOUD_PROJECT` | `precepgo-mentor-ai` | ✅ Yes |
| `GOOGLE_CLOUD_REGION` | `us-central1` | ✅ Yes |
| `MCP_URL` | (optional) Fallback MCP server | ❌ No |

## Troubleshooting

### Check Logs
```bash
gcloud run logs read precepgo-adk-panel --region us-central1 --limit 50
```

### Check Service Status
```bash
gcloud run services describe precepgo-adk-panel --region us-central1
```

### Enable Firestore API for Firebase Project
```bash
gcloud services enable firestore.googleapis.com --project=auth-demo-90be0
```

