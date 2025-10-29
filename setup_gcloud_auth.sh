#!/bin/bash
# Setup script for Google Cloud authentication for PrecepGo ADK Panel

echo "🔐 Setting up Google Cloud Authentication for PrecepGo ADK Panel"
echo "================================================================"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI is not installed"
    echo "📥 Please install it from: https://cloud.google.com/sdk/docs/install"
    echo ""
    echo "After installation, run:"
    echo "  gcloud init"
    echo "  gcloud auth application-default login"
    exit 1
fi

echo "✅ gcloud CLI is installed"
echo ""

# Check current authentication status
echo "🔍 Checking authentication status..."
if gcloud auth application-default print-access-token &> /dev/null; then
    echo "✅ Application Default Credentials are already configured"
    echo ""
    CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
    echo "📋 Current Project: $CURRENT_PROJECT"
    echo ""
    
    # Check if it's the right project
    if [ "$CURRENT_PROJECT" != "precepgo-mentor-ai" ]; then
        echo "⚠️  Current project is not 'precepgo-mentor-ai'"
        echo "🔧 Setting project to precepgo-mentor-ai..."
        gcloud config set project precepgo-mentor-ai
    fi
else
    echo "⚠️  Application Default Credentials not configured"
    echo "🔧 Running authentication..."
    echo ""
    
    # Set project
    gcloud config set project precepgo-mentor-ai
    
    # Authenticate
    gcloud auth application-default login
fi

echo ""
echo "✅ Google Cloud authentication is now configured!"
echo ""
echo "🚀 You can now start the server with:"
echo "   source venv/bin/activate"
echo "   MCP_URL=https://precepgo-data-mcp-g4y4qz5rfa-uw.a.run.app python3 main.py"
echo ""
echo "🌐 Or visit the dashboard at: http://localhost:8080/dashboard"

