# 🚀 Quick Start: Scheduled Research Agent

## What You Now Have

A **fully automated research agent** powered by **Google Vertex AI (Gemini 1.5 Pro)** that:
- ✅ Runs every 5 minutes automatically
- ✅ Analyzes Barash Section 2 chapters  
- ✅ Generates 20 MCQ questions per cycle
- ✅ Uses ONLY the actual Barash text (no hallucinations!)
- ✅ Saves results to `Questions.md`

## How to Run Locally

### Step 1: Authenticate with Google Cloud
```bash
./setup_gcloud_auth.sh
```

### Step 2: Set Your MCP URL (Optional)
```bash
export MCP_URL="https://your-mcp-server.run.app"
```

### Step 3: Start the Server
```bash
python3 main.py
```

### Step 4: Open Dashboard
```
http://localhost:8080/dashboard
```

You'll see:
- 🔬 **Scheduled Research Agent** status panel (blue box)
- 🚀 **Trigger Research Now** button (manual trigger)
- 🔄 **Refresh Status** button (update display)

## What Happens Next

### Automatic Mode
```
00:00 - Server starts
00:00 - Research Task #1 runs immediately
00:05 - Research Task #2 (after 5 minutes)
00:10 - Research Task #3 (after 5 minutes)
... continues every 5 minutes ...
```

### Each Research Cycle Does This:

1. **Selects a Barash Chapter** (random from 6 chapters)
   ```
   "Genomic Basis of Perioperative Precision Medicine"
   "Experimental Design and Statistics"
   "Inflammation, Wound Healing, and Infection"
   "The Allergic Response"  
   "Mechanisms of Anesthesia and Consciousness"
   "Basic Principles of Clinical Pharmacology"
   ```

2. **Fetches Full Chapter Content**
   - Tries MCP server first
   - Falls back to local file: `data/Section 2 - Basic Science and Fundamental's.txt`

3. **Vertex AI Deep Research** (Gemini 1.5 Pro)
   - Analyzes up to 100,000 characters
   - Identifies key concepts
   - Creates 20 questions following Bloom's Taxonomy

4. **Saves to Questions.md**
   - Formatted exactly like your example
   - Includes timestamp and metadata
   - Overwrites previous version

## Check Results

### View Generated Questions
```bash
cat Questions.md
```

### Check Latest Status
```bash
curl http://localhost:8080/research/status | jq
```

### Watch Live Logs
```bash
# In your terminal where server is running
# You'll see:
🔬 Starting scheduled research at 2025-10-29 14:30:00
📖 Fetching chapter: Mechanisms of Anesthesia and Consciousness
📊 Chapter loaded: Mechanisms of Anesthesia and Consciousness
📝 Word count: 12,450
🤖 Generating 20 questions with Gemini 1.5 Pro...
✅ Generated 20 questions and saved to Questions.md
⏳ Next research scheduled in 5 minutes...
```

## Manual Triggers

### Via Dashboard
1. Go to http://localhost:8080/dashboard
2. Click "🚀 Trigger Research Now"
3. Wait for completion alert
4. Check `Questions.md`

### Via API
```bash
curl -X POST http://localhost:8080/research/trigger
```

### Via Python
```python
import requests
response = requests.post("http://localhost:8080/research/trigger")
print(response.json())
```

## Example Output (Questions.md)

```markdown
# Multiple Choice Questions: Genomic Basis of Perioperative Precision Medicine
## Based on Barash, Cullen, and Stoelting's Clinical Anesthesia, 9th Edition

**Generated:** 2025-10-29 14:30:00
**Chapter:** Genomic Basis of Perioperative Precision Medicine
**Source:** Barash, Cullen, and Stoelting's Clinical Anesthesia - Section 2

---

## Questions

**1. Perioperative genomic variation influences surgical outcomes through multiple complex mechanisms. Based on the question, what is the best answer?**

A) Genomic variation primarily determines preoperative comorbidities...

B) Genomic variation modulates dynamic host responses to surgical injury...

C) Genomic variation affects only long-term postoperative outcomes...

**Correct Answer:** B

**Explanation:** Barash emphasizes that genomic and epigenomic variation...

[... 19 more questions ...]
```

## Troubleshooting

### "Vertex AI not available"
```bash
# Run authentication script
./setup_gcloud_auth.sh

# Check project is set
gcloud config get-value project
# Should show: precepgo-mentor-ai
```

### "MCP_URL not set"
```bash
# Set environment variable
export MCP_URL="https://your-mcp-service.run.app"

# Or edit main.py to use local file only
# (it already has fallback logic)
```

### Questions.md not updating
```bash
# Check file permissions
ls -la Questions.md

# Check server logs for errors
# Look for ❌ error messages
```

### Research not running
```bash
# Check status endpoint
curl http://localhost:8080/research/status

# Manually trigger once to test
curl -X POST http://localhost:8080/research/trigger
```

## Advanced Configuration

### Change Schedule Interval
Edit `main.py` line ~147:
```python
await asyncio.sleep(300)  # 300 seconds = 5 minutes
# Change to:
await asyncio.sleep(600)  # 10 minutes
await asyncio.sleep(60)   # 1 minute (not recommended - rate limits!)
```

### Change Number of Questions
Edit `main.py` line ~647:
```python
"create exactly 20 multiple choice questions"
# Change to:
"create exactly 50 multiple choice questions"
```

### Use Different Chapters
Edit `main.py` lines ~556-563:
```python
chapters = [
    "Your Custom Chapter 1",
    "Your Custom Chapter 2",
    # etc.
]
```

## Deploy to Production

### Build Docker Image
```bash
docker build -t gcr.io/precepgo-mentor-ai/precepgo-adk-panel .
docker push gcr.io/precepgo-mentor-ai/precepgo-adk-panel
```

### Deploy to Cloud Run
```bash
gcloud run deploy precepgo-adk-panel \
  --image gcr.io/precepgo-mentor-ai/precepgo-adk-panel \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars MCP_URL=https://your-mcp-service.run.app \
  --memory 2Gi \
  --timeout 300
```

### Set Up Monitoring
```bash
# View logs
gcloud run services logs read precepgo-adk-panel --region us-central1 --tail

# Check metrics
gcloud run services describe precepgo-adk-panel --region us-central1
```

## 🎉 You're All Set!

Your scheduled research agent is now:
- ✅ Using Vertex AI (Gemini 1.5 Pro)
- ✅ Running every 5 minutes
- ✅ Analyzing Barash chapters deeply
- ✅ Generating 20 questions per cycle
- ✅ Saving to Questions.md
- ✅ Fully automated!

Just start the server and watch it work! 🚀

---

**Questions?** Check the logs or trigger manually to see what's happening.

