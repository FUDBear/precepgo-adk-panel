#!/bin/bash
# Quick Deploy Script for Cloud Run
# Run this to deploy your ADK agents immediately!

set -e  # Exit on error

echo "🚀 PrecepGo ADK Panel - Cloud Run Deployment"
echo "============================================"
echo ""

# Check if running from correct directory
if [ ! -f "agent.py" ]; then
    echo "❌ Error: agent.py not found"
    echo "   Please run this script from the project root directory"
    exit 1
fi

# Get project ID
echo "📋 Step 1: Configure deployment"
echo ""
read -p "Enter your GCP Project ID [precepgo-mentor-ai]: " PROJECT_ID
PROJECT_ID=${PROJECT_ID:-precepgo-mentor-ai}

read -p "Enter region [us-central1]: " REGION
REGION=${REGION:-us-central1}

read -p "Enter service name [precepgo-adk-panel]: " SERVICE_NAME
SERVICE_NAME=${SERVICE_NAME:-precepgo-adk-panel}

# Get API key
if [ -z "$GOOGLE_API_KEY" ]; then
    read -p "Enter your Google API Key: " GOOGLE_API_KEY
fi

echo ""
echo "Configuration:"
echo "  Project ID: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Service: $SERVICE_NAME"
echo "  API Key: ${GOOGLE_API_KEY:0:10}..."
echo ""

read -p "Continue with deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled"
    exit 0
fi

echo ""
echo "🔧 Step 2: Installing ADK CLI..."
uvx --from google-adk adk --version || {
    echo "❌ Failed to install ADK CLI"
    echo "   Try: pip install google-adk"
    exit 1
}

echo ""
echo "🚀 Step 3: Deploying to Cloud Run..."
echo "   This will take 5-10 minutes..."
echo ""

uvx --from google-adk \
adk deploy cloud_run \
    --project=$PROJECT_ID \
    --region=$REGION \
    --service_name=$SERVICE_NAME \
    --with_ui \
    . \
    -- \
    --allow-unauthenticated \
    --set-env-vars="GOOGLE_API_KEY=$GOOGLE_API_KEY,FIREBASE_PROJECT_ID=$PROJECT_ID"

# Get the URL
echo ""
echo "🎉 Deployment complete!"
echo ""
echo "Getting service URL..."
URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)' 2>/dev/null || echo "")

if [ -n "$URL" ]; then
    echo ""
    echo "✅ Your agents are now running at:"
    echo "   $URL"
    echo ""
    echo "📖 Try these commands in the web UI:"
    echo "   • Hello"
    echo "   • Run the safety pipeline"
    echo "   • Calculate time savings"
    echo ""
else
    echo "⚠️  Could not retrieve URL automatically"
    echo "   Check Cloud Run console: https://console.cloud.google.com/run"
fi

echo ""
echo "🎯 Next steps:"
echo "   1. Open the URL in your browser"
echo "   2. Chat with your agents"
echo "   3. Demo the safety pipeline for judges!"
echo ""
echo "Good luck at the hackathon! 🚀"
