#!/bin/bash
# Quick start script for PrecepGo ADK Panel
# Start: bash "/Users/joshuaburleson/Documents/App Development/precepgo-adk-panel/START_SERVER.sh"

cd "/Users/joshuaburleson/Documents/App Development/precepgo-adk-panel"

echo "🚀 Starting PrecepGo ADK Panel..."
echo ""

# Activate virtual environment
if [ -d "venv" ]; then
    echo "✅ Activating virtual environment..."
    source venv/bin/activate
else
    echo "❌ Virtual environment not found!"
    echo "   Creating it now..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found!"
    echo "   Copying from env.example..."
    cp env.example .env
    echo "   Please edit .env and add your GEMINI_API_KEY"
    echo "   Get your key from: https://makersuite.google.com/app/apikey"
    exit 1
fi

# Check if GEMINI_API_KEY is set
if ! grep -q "GEMINI_API_KEY=" .env || grep -q "GEMINI_API_KEY=your-" .env; then
    echo "⚠️  GEMINI_API_KEY not set in .env file!"
    echo "   Please edit .env and add your actual API key"
    echo "   Get your key from: https://makersuite.google.com/app/apikey"
    exit 1
fi

echo "✅ All checks passed!"
echo ""
# Check if port 8080 is in use and kill it
if lsof -ti:8080 > /dev/null 2>&1; then
    echo "⚠️  Port 8080 is already in use. Stopping existing process..."
    lsof -ti:8080 | xargs kill -9 2>/dev/null
    sleep 2
    echo "✅ Port 8080 freed"
fi

echo ""
echo "🌐 Starting server on http://localhost:8080"
echo "📊 Dashboard: http://localhost:8080/dashboard"
echo "📖 API Docs: http://localhost:8080/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
uvicorn main:app --host 0.0.0.0 --port 8080 --reload

