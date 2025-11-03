#!/bin/bash

# Cloud Run Deployment Script for PrecepGo ADK Panel

set -e

PROJECT_ID="precepgo-mentor-ai"
SERVICE_NAME="precepgo-adk-panel"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🚀 Deploying PrecepGo ADK Panel to Cloud Run"
echo "=============================================="
echo "Project: ${PROJECT_ID}"
echo "Service: ${SERVICE_NAME}"
echo "Region: ${REGION}"
echo ""

# Step 1: Set project
echo "📋 Step 1: Setting GCP project..."
gcloud config set project ${PROJECT_ID}

# Step 2: Enable required APIs
echo ""
echo "📋 Step 2: Enabling required APIs..."
gcloud services enable cloudbuild.googleapis.com --quiet
gcloud services enable run.googleapis.com --quiet
# Enable Firestore API for both projects
gcloud services enable firestore.googleapis.com --project=${PROJECT_ID} --quiet || echo "Firestore API may already be enabled for ${PROJECT_ID}"
gcloud services enable firestore.googleapis.com --project=auth-demo-90be0 --quiet || echo "Firestore API may already be enabled for auth-demo-90be0"

# Step 3: Build container image
echo ""
echo "📋 Step 3: Building container image..."
gcloud builds submit --tag ${IMAGE_NAME} --timeout=20m

# Step 4: Deploy to Cloud Run
echo ""
echo "📋 Step 4: Deploying to Cloud Run..."

# Get environment variables from .env file if it exists
ENV_VARS=""
if [ -f .env ]; then
    echo "   Loading environment variables from .env file..."
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ $key =~ ^#.*$ ]] && continue
        [[ -z "$key" ]] && continue
        
        # Skip GEMINI_API_KEY - it's set as a secret, not env var
        [[ "$key" == "GEMINI_API_KEY" ]] && continue
        
        # Remove quotes if present
        value=$(echo "$value" | sed 's/^"\(.*\)"$/\1/' | sed "s/^'\(.*\)'$/\1/")
        
        # Skip if value is empty
        [[ -z "$value" ]] && continue
        
        # Append to ENV_VARS
        if [ -z "$ENV_VARS" ]; then
            ENV_VARS="${key}=${value}"
        else
            ENV_VARS="${ENV_VARS},${key}=${value}"
        fi
    done < .env
fi

# Deploy with environment variables
if [ -n "$ENV_VARS" ]; then
    echo "   Deploying with environment variables from .env..."
    gcloud run deploy ${SERVICE_NAME} \
        --image ${IMAGE_NAME} \
        --platform managed \
        --region ${REGION} \
        --allow-unauthenticated \
        --update-env-vars "${ENV_VARS}" \
        --memory 2Gi \
        --cpu 2 \
        --timeout 300 \
        --max-instances 10 \
        --set-secrets "GEMINI_API_KEY=gemini-api-key:latest"
else
    echo "   Deploying without .env file (updating key env vars)..."
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
fi

# Step 5: Grant Firestore permissions to Cloud Run service account
echo ""
echo "📋 Step 5: Granting Firestore permissions..."

# Get Cloud Run service account
CLOUD_RUN_SA=$(gcloud run services describe ${SERVICE_NAME} \
    --region ${REGION} \
    --format="value(spec.template.spec.serviceAccountName)" 2>/dev/null || \
    echo "${PROJECT_ID}-compute@developer.gserviceaccount.com")

if [ -z "$CLOUD_RUN_SA" ] || [ "$CLOUD_RUN_SA" = "default" ]; then
    # Try to get the compute service account
    PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)" 2>/dev/null || echo "")
    if [ -n "$PROJECT_NUMBER" ]; then
        CLOUD_RUN_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
    else
        CLOUD_RUN_SA="${PROJECT_ID}@appspot.gserviceaccount.com"
    fi
fi

echo "   Cloud Run service account: ${CLOUD_RUN_SA}"

# Grant Firestore access to the Firebase project (auth-demo-90be0)
FIREBASE_PROJECT="auth-demo-90be0"
echo "   Granting Cloud Datastore User role for Firebase project: ${FIREBASE_PROJECT}..."

gcloud projects add-iam-policy-binding ${FIREBASE_PROJECT} \
    --member="serviceAccount:${CLOUD_RUN_SA}" \
    --role="roles/datastore.user" \
    --quiet || echo "   ⚠️  Could not grant permissions (may need manual setup in Firebase Console)"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📍 Service URL:"
gcloud run services describe ${SERVICE_NAME} \
    --region ${REGION} \
    --format="value(status.url)"
echo ""
echo "📋 Next steps:"
echo "   1. Verify environment variables are set in Cloud Run console"
echo "   2. Test the deployment: curl \$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format='value(status.url)')/health"
echo "   3. Visit dashboard: \$(gcloud run services describe ${SERVICE_NAME} --region ${REGION} --format='value(status.url)')/dashboard"

