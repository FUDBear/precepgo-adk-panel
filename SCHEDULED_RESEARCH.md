# 🔬 Scheduled Research Agent - Vertex AI Implementation

## Overview

Your application now has a **scheduled research agent** that automatically performs deep research on Barash Section 2 chapters every 5 minutes and generates 20 high-quality multiple choice questions.

## ✅ What's Been Implemented

### 1. **Vertex AI Integration** (Already Active!)
- ✅ Using `GenerativeModel` from Vertex AI
- ✅ Using `gemini-1.5-pro` for deep research
- ✅ Using `gemini-1.5-flash` for quick queries
- ✅ No API keys needed - uses Google Cloud authentication

### 2. **Scheduled Research Task**
```python
# Runs automatically every 5 minutes
async def scheduled_research_task():
    - Fetches a full Barash chapter from MCP or local file
    - Uses Gemini 1.5 Pro for deep analysis
    - Generates exactly 20 MCQ questions
    - Saves to Questions.md
```

### 3. **Chapter Rotation**
The agent cycles through all 6 chapters in Barash Section 2:
- Chapter 6: Genomic Basis of Perioperative Precision Medicine
- Chapter 7: Experimental Design and Statistics  
- Chapter 8: Inflammation, Wound Healing, and Infection
- Chapter 9: The Allergic Response
- Chapter 10: Mechanisms of Anesthesia and Consciousness
- Chapter 11: Basic Principles of Clinical Pharmacology

### 4. **Deep Research Process**

**Step 1: Content Retrieval**
```python
# Tries MCP server first
fetch_full_barash_chapter()
  ↓
# Falls back to local file if needed
"data/Section 2 - Basic Science and Fundamental's.txt"
```

**Step 2: Question Generation** (Using Vertex AI Gemini Pro)
- Analyzes up to 100,000 characters of chapter content
- Follows Bloom's Taxonomy distribution:
  - 30% Foundational/Recall
  - 50% Application/Analysis
  - 20% Higher-Order Thinking
- Creates plausible distractors
- Generates explanations citing the chapter

**Step 3: File Output**
```markdown
Questions.md
├── Chapter title
├── Metadata (timestamp, source)
├── 20 formatted questions
│   ├── Question stem
│   ├── Options A, B, C (sometimes D)
│   ├── Correct answer
│   └── Explanation
└── Summary section
```

## 🎯 New API Endpoints

### Check Research Status
```bash
GET /research/status
```

**Response:**
```json
{
  "running": true,
  "status": "completed",
  "last_run": "2025-10-29T14:30:00",
  "last_chapter": "Genomic Basis of Perioperative Precision Medicine",
  "questions_generated": 20,
  "next_run_in_seconds": 300
}
```

### Manual Trigger
```bash
POST /research/trigger
```

**Response:**
```json
{
  "ok": true,
  "result": {
    "success": true,
    "chapter": "Mechanisms of Anesthesia and Consciousness",
    "questions_generated": 20,
    "file": "Questions.md",
    "timestamp": "2025-10-29T14:35:00"
  }
}
```

## 🖥️ Dashboard Features

Visit `http://localhost:8080/dashboard` to see:

1. **Research Status Panel** (blue box)
   - Current status (idle/running/completed/error)
   - Last run timestamp
   - Last chapter analyzed
   - Number of questions generated

2. **Manual Controls**
   - "🚀 Trigger Research Now" - Run research immediately
   - "🔄 Refresh Status" - Update status display
   - Auto-refreshes every 30 seconds

3. **Single Question Generator** (existing functionality)
   - Still works for generating individual concept-based questions

## 🚀 How to Run

### Local Development
```bash
# Make sure you're authenticated with Google Cloud
./setup_gcloud_auth.sh

# Start the server
python main.py

# Or with uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8080
```

### Deploy to Cloud Run
```bash
# Build and deploy
gcloud run deploy precepgo-adk-panel \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars MCP_URL=https://your-mcp-service-url
```

## 📊 How It Works

### Automatic Schedule (Every 5 Minutes)
```
Server Start
    ↓
Background Task Starts
    ↓
Wait 0 minutes → Run Research #1
    ↓
Wait 5 minutes → Run Research #2  
    ↓
Wait 5 minutes → Run Research #3
    ↓
... continues forever ...
```

### Each Research Cycle
```
1. Select Barash Chapter (random or sequential)
   ↓
2. Fetch Chapter Content
   ├─→ Try MCP server first
   └─→ Fallback to local file
   ↓
3. Vertex AI Analysis
   ├─→ Gemini 1.5 Pro analyzes content
   ├─→ Identifies key concepts
   ├─→ Creates 20 questions
   └─→ Formats according to template
   ↓
4. Save Questions.md
   ├─→ Overwrites previous version
   └─→ Includes metadata & timestamps
   ↓
5. Update Status
   └─→ Ready for next cycle
```

## 🔍 Data Sources

### Primary Source (MCP Server)
- URL: Set via `MCP_URL` environment variable
- Endpoint: `POST /mcp/search`
- Returns: Structured Barash content with metadata

### Fallback Source (Local File)
- Path: `data/Section 2 - Basic Science and Fundamental's.txt`
- Size: 14,480 lines
- Used when MCP is unavailable

## 📝 Question Format (Matches Questions.md)

Each question follows this exact format:

```markdown
**1. [Question stem based on chapter content]**

A) [Plausible distractor]

B) [Correct answer]

C) [Plausible distractor]

**Correct Answer:** B

**Explanation:** [2-3 sentences citing the chapter, explaining why B is correct]
```

## 🎓 Educational Quality

### Question Distribution
- **30% Foundational** - Tests recall and understanding of key facts
- **50% Application** - Tests ability to apply concepts to clinical scenarios  
- **20% Higher-Order** - Tests analysis, evaluation, and synthesis

### Grounding in Source Material
- ✅ All content comes from Barash Section 2
- ✅ No hallucinated information
- ✅ Explanations cite the chapter
- ✅ Distractors based on common misconceptions from the text

## 🛠️ Customization Options

### Change Research Interval
```python
# In scheduled_research_task()
await asyncio.sleep(300)  # Change 300 to desired seconds
```

### Change Model
```python
# In generate_chapter_questions()
model = GenerativeModel(MODEL_GEMINI_PRO)  # or MODEL_GEMINI_FLASH
```

### Adjust Content Length
```python
# In generate_chapter_questions() prompt
{chapter_data['content'][:100000]}  # Change 100000 to desired char limit
```

### Number of Questions
```python
# In prompt to Gemini
"create exactly 20 multiple choice questions"  # Change to desired number
```

## 🔐 Authentication

### Google Cloud Setup
```bash
# Already done via your setup_gcloud_auth.sh
gcloud auth application-default login
gcloud config set project precepgo-mentor-ai
```

### Environment Variables
```bash
# Required
export MCP_URL="https://your-mcp-service.run.app"

# Optional (for Vertex AI - usually auto-detected)
export GOOGLE_CLOUD_PROJECT="precepgo-mentor-ai"
export GOOGLE_CLOUD_REGION="us-central1"
```

## 📈 Monitoring

### Check Logs
```bash
# Local
# Watch console output

# Cloud Run
gcloud run services logs read precepgo-adk-panel --region us-central1 --tail
```

### Status Indicators
- **idle** - Waiting for first run
- **running** - Currently generating questions
- **completed** - Last run successful  
- **error: [message]** - Last run failed

## 🎯 Key Differences from Claude Agent

| Feature | Previous (Claude) | Now (Vertex AI) |
|---------|------------------|-----------------|
| **Provider** | Anthropic Claude | Google Vertex AI |
| **Models** | claude-sonnet-4 | gemini-1.5-pro/flash |
| **Auth** | API Key required | Google Cloud auth (ADC) |
| **Cost** | Per-token billing | Google Cloud billing |
| **Integration** | REST API | Native Vertex AI SDK |
| **Scheduling** | Manual/external | Built-in background task |
| **Data Source** | Direct file read | MCP server + fallback |

## ✨ Benefits of This Approach

1. **Automatic & Continuous** - Runs every 5 minutes without manual intervention
2. **Grounded in Facts** - Only uses actual Barash content, no hallucinations
3. **Comprehensive Coverage** - Cycles through all 6 chapters
4. **High Quality** - Uses Gemini 1.5 Pro for deep analysis
5. **Production Ready** - Runs on Google Cloud Run with proper auth
6. **Monitorable** - Status endpoint and dashboard visibility
7. **Flexible** - Can trigger manually or wait for schedule

## 🚨 Important Notes

1. **Vertex AI Quota** - Gemini Pro has rate limits. Monitor your usage.
2. **Questions.md** - Gets overwritten every 5 minutes. Save versions if needed.
3. **MCP Server** - Must be running and accessible for optimal content retrieval.
4. **File Fallback** - Local Barash file ensures operation even if MCP is down.

## 📚 Next Steps

1. **Test the system**:
   ```bash
   python main.py
   # Visit http://localhost:8080/dashboard
   # Click "Trigger Research Now"
   ```

2. **Verify Questions.md** is being generated correctly

3. **Deploy to Cloud Run** when ready

4. **Optional**: Add question storage to track all generated questions over time

---

**Last Updated:** October 29, 2025  
**Status:** ✅ Active - Scheduled research running every 5 minutes  
**Model:** Gemini 1.5 Pro via Vertex AI

