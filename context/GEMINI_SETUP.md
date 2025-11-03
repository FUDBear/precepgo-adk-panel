# 🔑 Gemini API Setup for Google ADK Hackathon

## Quick Setup (2 minutes)

### Step 1: Get Your Gemini API Key

1. Visit: **https://makersuite.google.com/app/apikey**
2. Click **"Create API Key"**
3. Select your Google Cloud project: **precepgo-mentor-ai**
4. Copy the API key

### Step 2: Set Environment Variable

**In your terminal (where you run the server):**

```bash
export GEMINI_API_KEY="your-api-key-here"
```

### Step 3: Start Server

```bash
cd "/Users/joshuaburleson/Documents/App Development/precepgo-adk-panel"
source venv/bin/activate
python main.py
```

### Step 4: Test It!

Visit http://localhost:8080/dashboard and click **"🚀 Trigger Research Now"**

## Expected Output

When it works, you'll see:

```
✅ Gemini API configured successfully
🚀 Starting scheduled research task...
🔬 Starting deep research on Barash chapter...
📖 Fetching chapter: [Chapter Name]
📊 Chapter loaded: [Chapter Name]
📝 Word count: 129283
🤖 Attempting Gemini API question generation...
🤖 Generating 20 questions with Gemini API...
✅ Gemini API generation successful!
✅ Generated 20 questions and saved to Questions.md
```

## For Cloud Run Deployment

Set the environment variable in Cloud Run:

```bash
gcloud run services update precepgo-adk-panel \
  --region us-central1 \
  --set-env-vars GEMINI_API_KEY="your-api-key-here"
```

Or use Google Secret Manager (more secure):

```bash
# Create secret
echo -n "your-api-key-here" | gcloud secrets create gemini-api-key --data-file=-

# Update Cloud Run to use secret
gcloud run services update precepgo-adk-panel \
  --region us-central1 \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest
```

---

**That's it!** Once you set the API key, the research agent will work perfectly! 🚀

