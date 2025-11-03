# 🚀 Local Setup & Deployment Guide

## Prerequisites

1. **Python 3.8+** (check with: `python3 --version`)
2. **pip** (Python package manager)
3. **Git** (if cloning the repo)

## Step-by-Step Setup

### 1. Navigate to Project Directory

```bash
cd "/Users/joshuaburleson/Documents/App Development/precepgo-adk-panel"
```

### 2. Create Virtual Environment (if not already created)

```bash
python3 -m venv venv
```

### 3. Activate Virtual Environment

**On macOS/Linux:**
```bash
source venv/bin/activate Ecosystem
```

You should see `(venv)` in your terminal prompt when activated.

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- FastAPI (web framework)
- uvicorn (ASGI server)
- google-generativeai (Gemini API)
- python-dotenv (environment variables)
- And other required packages

### 5. Set Up Environment Variables

**Option A: Copy the example file**
```bash
cp env.example .env
```

**Option B: Create .env manually**
```bash
nano .env
```

Add your configuration:
```bash
# Google Gemini API Key (required)
GEMINI_API_KEY=your-actual-gemini-api-key-here

# MCP Server URL (optional - fallback to local files)
MCP_URL=https://precepgo-data-mcp-g4y4qz5rfa-uw.a.run.app

# Google Cloud Project (optional)
GOOGLE_CLOUD_PROJECT=precepgo-mentor-ai
GOOGLE_CLOUD_REGION=us-central1
```

**Get your Gemini API key:**
1. Go to: https://makersuite.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key
4. Paste it in `.env` file

### 6. Verify Setup

```bash
python3 -c "from gemini_agent import GeminiAgent; print('✅ All imports work!')"
```

### 7. Run the Server

**Option A: Run directly with Python**
```bash
python3 main.py
```

**Option B: Run with uvicorn (recommended for development)**
```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

The `--reload` flag automatically restarts the server when you change code.

### 8. Access the Application

Open your web browser and go to:
- **Dashboard**: http://localhost:8080/dashboard
- **API Root**: http://localhost:8080/
- **Health Check**: http://localhost:8080/health
- **API Docs**: http://localhost:8080/docs (FastAPI automatic documentation)

## Testing the Application

### 1. Test Health Endpoint
```bash
curl http://localhost:8080/health
```

Expected response:
```json
{
  "status": "healthy",
  "mcp_url_configured": true
}
```

### 2. Test Research Trigger
```bash
curl -X POST http://localhost:8080/research/trigger
```

This will start generating questions from all 5 Barash sections (takes 1-2 minutes).

### 3. Check Generated Questions
```bash
curl http://localhost:8080/research/questions
```

Or open the file directly:
```bash
cat Questions.md
```

## Troubleshooting

### "Module not found" errors
```bash
# Make sure venv is activated (you should see (venv) in prompt)
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### "GEMINI_API_KEY not found" error
```bash
# Check .env file exists and has the key
cat .env

# Verify it's being loaded
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('GEMINI_API_KEY'))"
```

### Port 8080 already in use
```bash
# Find what's using port 8080
lsof -i :8080

# Kill the process (replace PID with actual process ID)
kill -9 <PID>

# Or use a different port
uvicorn main:app --host 0.0.0.0 --port 8081
```

### MCP Server connection issues
- The app will fallback to local files if MCP_URL is not configured
- Check your MCP_URL is correct in `.env`
- Verify the MCP server is running and accessible

## Development Tips

### Run with auto-reload (recommended)
```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

This restarts automatically when you save changes to Python files.

### View server logs
Logs appear in the terminal where you started the server. If running in background:
```bash
tail -f server.log
```

### Deactivate virtual environment
When you're done:
```bash
deactivate
```

## Quick Start (All-in-One)

```bash
# Navigate to project
cd "/Users/joshuaburleson/Documents/App Development/precepgo-adk-panel"

# Activate venv
source venv/bin/activate

# (First time only) Install dependencies
pip install -r requirements.txt

# (First time only) Set up .env file
cp env.example .env
nano .env  # Add your GEMINI_API_KEY

# Run server
uvicorn main:app --host 0.0.0.bility0 --port 8080 --reload
```

Then open: **http://localhost:8080/dashboard**

## What Each Port Does

- **8080**: Main application (FastAPI)
- **Dashboard**: http://localhost:8080/dashboard - Web interface
- **API Docs**: http://localhost:8080/docs - Interactive API documentation
- **Health**: http://localhost:8080/health - Health check endpoint

---

**That's it!** You should now have the application running locally. 🎉

