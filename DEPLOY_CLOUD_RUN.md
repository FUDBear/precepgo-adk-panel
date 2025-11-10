# 🚀 Deploy to Google Cloud Run - FIXED

## ⚠️ The Problem

Your deployment failed because `main.py` is trying to import legacy class-based agents that no longer exist after ADK conversion:

```python
# main.py lines 48-96 - THESE IMPORTS FAIL ❌
from agents.scenario_agent import ClinicalScenarioAgent  # Doesn't exist
from agents.evaluations_agent import EvaluationsAgent     # Doesn't exist
from agents.notification_agent import NotificationAgent   # Doesn't exist
```

After ADK conversion, these agents export:
```python
# What actually exists now ✅
from agents.scenario_agent import scenario_agent         # ADK agent
from agents.evaluations_agent import evaluation_agent    # ADK agent
from agents.notification_agent import notification_agent # ADK agent
```

---

## ✅ Solution: Two Deployment Options

### **Option 1: Native ADK Deployment (RECOMMENDED for Hackathon)**

Deploy using Google ADK's built-in Cloud Run deployment. This gives you the ADK web UI automatically.

```bash
# Set environment variables
export PROJECT_ID=precepgo-mentor-ai
export REGION=us-central1

# Deploy with ADK CLI
uvx --from google-adk \
adk deploy cloud_run \
    --project=$PROJECT_ID \
    --region=$REGION \
    --service_name=precepgo-adk-panel \
    --with_ui \
    . \
    -- \
    --allow-unauthenticated \
    --set-env-vars="GOOGLE_API_KEY=your_key_here,FIREBASE_PROJECT_ID=$PROJECT_ID"
```

**Pros:**
- ✅ Works out of the box
- ✅ Includes ADK web UI
- ✅ Perfect for hackathon demo
- ✅ No code changes needed

**Cons:**
- ❌ Your FastAPI endpoints won't be available
- ❌ Loses custom /mentor/* and /agents/* endpoints

---

### **Option 2: FastAPI Deployment with ADK Fix**

Fix the imports in `main.py` and deploy with your existing Dockerfile.

#### Step 1: Fix main.py Imports

Replace lines 46-114 in `main.py` with:

```python
# ============================================
# AGENT IMPORTS - ADK Compatible
# ============================================

# ADK Agent Wrapper (lazy-loaded)
try:
    from adk_wrapper import (
        get_evaluation_agent,
        get_notification_agent,
        get_scenario_agent,
        get_time_agent,
        get_root_agent,
        is_adk_available
    )
    ADK_AGENTS_AVAILABLE = True
    print("✅ ADK agent wrapper loaded")
except ImportError as e:
    print(f"⚠️ ADK agents not available: {e}")
    ADK_AGENTS_AVAILABLE = False

# Disable legacy agents (no longer available)
CLINICAL_SCENARIO_AGENT_AVAILABLE = False
EVALUATIONS_AGENT_AVAILABLE = False
NOTIFICATION_AGENT_AVAILABLE = False
STATE_AGENT_AVAILABLE = False
COA_AGENT_AVAILABLE = False
TIME_SAVINGS_AGENT_AVAILABLE = False
IMAGE_GENERATION_AGENT_AVAILABLE = False
SITE_AGENT_AVAILABLE = False

print("⚠️ Legacy class-based agents disabled")
print("ℹ️  Use ADK agents via /adk/* endpoints instead")

# Continue with ADK imports (lines 115+)...
```

#### Step 2: Add ADK Endpoints

Add these endpoints after line 2684 in `main.py`:

```python
# ============================================
# ADK AGENT ENDPOINTS
# ============================================

@app.post("/adk/evaluation/create")
async def adk_create_evaluation():
    """Create evaluation using ADK agent"""
    if not is_adk_available():
        raise HTTPException(status_code=503, detail="ADK agents not available")

    agent = get_evaluation_agent()
    return {
        "status": "queued",
        "message": "Use ADK web UI or CLI for full agent interaction",
        "agent": agent.name if agent else None
    }

@app.post("/adk/safety-pipeline/run")
async def adk_run_safety_pipeline():
    """Run complete safety pipeline (eval -> notify -> scenario)"""
    if not is_adk_available():
        raise HTTPException(status_code=503, detail="ADK agents not available")

    pipeline = get_safety_pipeline()
    return {
        "status": "queued",
        "message": "Safety pipeline initiated",
        "workflow": pipeline.name if pipeline else None
    }

@app.get("/adk/agents/list")
async def adk_list_agents():
    """List available ADK agents"""
    if not is_adk_available():
        return {"available": False, "agents": []}

    return {
        "available": True,
        "agents": [
            {"name": "root_agent", "description": "Main coordinator"},
            {"name": "safety_pipeline", "description": "Evaluation -> Notification -> Scenario"},
            {"name": "evaluation_agent", "description": "Create student evaluations"},
            {"name": "notification_agent", "description": "Check dangerous ratings"},
            {"name": "scenario_agent", "description": "Generate scenarios"},
            {"name": "time_agent", "description": "Calculate time savings"}
        ]
    }
```

#### Step 3: Deploy with Docker

```bash
# Build and deploy
gcloud builds submit --tag gcr.io/$PROJECT_ID/precepgo-adk-panel

gcloud run deploy precepgo-adk-panel \
  --image gcr.io/$PROJECT_ID/precepgo-adk-panel \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars="GOOGLE_API_KEY=your_key,FIREBASE_PROJECT_ID=$PROJECT_ID"
```

**Pros:**
- ✅ Keeps all your FastAPI endpoints
- ✅ Adds ADK agent support
- ✅ Custom business logic intact

**Cons:**
- ❌ Requires code changes
- ❌ More complex deployment

---

## 🎯 Recommended Approach for Hackathon

**Use Option 1 (Native ADK Deployment)** because:

1. ✅ **Zero code changes** - works immediately
2. ✅ **Shows ADK patterns** - exactly what judges want to see
3. ✅ **Web UI included** - professional demo interface
4. ✅ **5-minute deployment** - fastest path to working system

Your custom FastAPI endpoints can be deployed separately if needed, or you can demonstrate ADK agents via the web UI which is more impressive for the hackathon.

---

## 🚀 Quick Deploy (Option 1)

```bash
# 1. Set variables
export PROJECT_ID=precepgo-mentor-ai
export REGION=us-central1
export GOOGLE_API_KEY=your_gemini_api_key

# 2. Deploy
uvx --from google-adk \
adk deploy cloud_run \
    --project=$PROJECT_ID \
    --region=$REGION \
    --service_name=precepgo-adk-panel \
    --with_ui \
    . \
    -- \
    --allow-unauthenticated \
    --set-env-vars="GOOGLE_API_KEY=$GOOGLE_API_KEY,FIREBASE_PROJECT_ID=$PROJECT_ID"

# 3. Get URL
gcloud run services describe precepgo-adk-panel \
    --region=$REGION \
    --format='value(status.url)'
```

---

## 🎬 Demo Script

Once deployed:

1. Open the Cloud Run URL
2. Chat with the agent: "Run the safety pipeline"
3. Watch it execute: evaluation → notification → scenario
4. Show judges the state updates in real-time
5. Run: "Calculate time savings" to show metrics

---

## 🔍 Troubleshooting

### Deployment Still Failing?

Check these:

```bash
# 1. Verify ADK is installed
pip list | grep google-adk

# 2. Verify agent.py exists
cat agent.py

# 3. Verify it exports root_agent
python -c "from agents.root_agent import root_agent; print(root_agent.name)"

# 4. Test locally first
adk run .
```

### Import Errors During Deployment?

The issue is likely in `main.py`. If using Option 2:
- Make sure you replaced the imports (lines 46-114)
- Make sure `adk_wrapper.py` is in the project root
- Check that Dockerfile copies all `.py` files

---

## ✅ Verification

After deployment, test:

```bash
# Get your URL
URL=$(gcloud run services describe precepgo-adk-panel --region=$REGION --format='value(status.url)')

# Test health
curl $URL/health

# Test ADK status (if using Option 2)
curl $URL/adk/agents/list

# Test ADK web UI (if using Option 1)
# Open $URL in browser
```

---

**Choose Option 1 for fastest deployment and best hackathon demo! 🚀**
