# Frontend Deployment Guide - PrecepGo ADK Panel

## 🎯 Overview

This guide provides everything needed to build and deploy the frontend application that connects to the PrecepGo ADK Panel backend service running on Google Cloud Run.

## 🔗 Backend Service Information

**Service URL:** `https://precepgo-adk-panel-724021185717.us-central1.run.app`

**Health Check Endpoint:** `https://precepgo-adk-panel-724021185717.us-central1.run.app/health`

**Dashboard Endpoint:** `https://precepgo-adk-panel-724021185717.us-central1.run.app/dashboard`

---

## 📡 API Endpoints for Agent Control

### Base URL
```
https://precepgo-adk-panel-724021185717.us-central1.run.app
```

### 1. Health Check
```http
GET /health
```
**Response:**
```json
{
  "status": "healthy"
}
```

### 2. Get Agent Status
```http
GET /agents/{agent_name}/status
```
**Parameters:**
- `agent_name`: One of: `evaluation_agent`, `scenario_agent`, `notification_agent`, `coa_agent`

**Response:**
```json
{
  "agent": "evaluation_agent",
  "state": "idle",
  "result": {
    "doc_id": "abc123",
    "case_type": "General Anesthesia",
    "student": "John Doe"
  },
  "error": null
}
```

**States:** `idle`, `generating`, `completed`, `error`

### 3. Create Demo Evaluation
```http
POST /agents/evaluation/create-demo
```
**Request Body:** `{}` (no body needed)

**Response:**
```json
{
  "ok": true,
  "firestore_doc_id": "eval_123",
  "firestore_parent_doc_id": "parent_456",
  "case_type": "General Anesthesia",
  "preceptee_user_name": "John Doe",
  "preceptor_comment": "Short evaluation comment...",
  "focus_areas": "• Airway management\n• Spinal technique",
  "preceptor_ratings": {
    "preparation": 4,
    "technical_skills": 3,
    "clinical_reasoning": 4
  }
}
```

### 4. Generate Scenario
```http
POST /mentor/make-scenario
```
**Request Body:** `{}` (no body needed)

**Response:**
```json
{
  "ok": true,
  "scenario": {
    "case": {
      "name": "Appendectomy",
      "type": "General Surgery"
    },
    "patient": {
      "full_name": "Jane Smith",
      "age": 35,
      "asa_class": "ASA II"
    },
    "student": {
      "name": "John Doe",
      "class_standing": "SRNA Year 2"
    },
    "case_rationale": "Why this scenario helps...",
    "student_analysis": {
      "recent_cases": ["Case1", "Case2"],
      "weak_areas": ["Area1", "Area2"]
    }
  }
}
```

### 5. Run Safety Check (Notification Agent)
```http
POST /agents/notification/safety-check
```
**Request Body:** `{}` (no body needed)

**Response:**
```json
{
  "ok": true,
  "checked_count": 10,
  "dangerous_count": 2,
  "notifications_created": 2,
  "notifications": [
    {
      "id": "notif_123",
      "evaluation_id": "eval_456",
      "student_name": "John Doe",
      "dangerous_rating": -1,
      "reason": "Safety concern detected"
    }
  ]
}
```

### 6. Generate COA Compliance Reports
```http
POST /agents/coa-compliance/generate-reports
```
**Request Body:** `{}` (no body needed)

**Response:**
```json
{
  "ok": true,
  "reports": {
    "summary": {
      "total_evaluations": 100,
      "compliant": 95,
      "non_compliant": 5
    },
    "violations": [
      {
        "evaluation_id": "eval_123",
        "violation_type": "missing_comment",
        "severity": "high"
      }
    ]
  }
}
```

### 7. Automated Mode - Start
```http
POST /agents/automated-mode/start
```
**Request Body:** `{}` (no body needed)

**Response:**
```json
{
  "ok": true,
  "message": "Automated mode started for 15 minutes",
  "duration_minutes": 15
}
```

### 8. Automated Mode - Stop
```http
POST /agents/automated-mode/stop
```
**Request Body:** `{}` (no body needed)

**Response:**
```json
{
  "ok": true,
  "message": "Automated mode stopped"
}
```

### 9. Automated Mode - Status
```http
GET /agents/automated-mode/status
```
**Response:**
```json
{
  "active": true,
  "start_time": "2025-11-05T01:00:00Z",
  "end_time": "2025-11-05T01:15:00Z",
  "elapsed_minutes": 5,
  "remaining_minutes": 10
}
```

---

## 🚀 Frontend Deployment to Google Cloud Run

### Prerequisites
1. Google Cloud Project: `precepgo-mentor-ai`
2. Region: `us-central1`
3. gcloud CLI installed and authenticated

### Step 1: Create Dockerfile

Create a `Dockerfile` in your frontend directory:

```dockerfile
# Use Node.js 18 or 20 LTS
FROM node:20-slim

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production

# Copy application files
COPY . .

# Build the application (adjust for your framework)
# For React/Vite:
# RUN npm run build
# For Next.js:
# RUN npm run build

# Expose port
EXPOSE 8080

# Set environment variable for port
ENV PORT=8080

# Start the application
# For React/Vite (serve built files):
# CMD ["npx", "serve", "-s", "dist", "-l", "8080"]

# For Next.js:
# CMD ["npm", "start"]

# For other frameworks, adjust accordingly
CMD ["npm", "start"]
```

### Step 2: Create .dockerignore

```dockerignore
node_modules
npm-debug.log
.git
.gitignore
.env.local
.env.development.local
.env.test.local
.env.production.local
.next
dist
build
coverage
.nyc_output
```

### Step 3: Create Deployment Script

Create `deploy_frontend.sh`:

```bash
#!/bin/bash

set -e

PROJECT_ID="precepgo-mentor-ai"
SERVICE_NAME="precepgo-adk-frontend"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "🚀 Deploying PrecepGo ADK Frontend to Cloud Run"
echo "=============================================="
echo "Project: ${PROJECT_ID}"
echo "Service: ${SERVICE_NAME}"
echo "Region: ${REGION}"
echo ""

# Set project
gcloud config set project ${PROJECT_ID}

# Enable APIs
gcloud services enable cloudbuild.googleapis.com --quiet
gcloud services enable run.googleapis.com --quiet

# Build container image
echo "📋 Building container image..."
gcloud builds submit --tag ${IMAGE_NAME} --timeout=20m

# Deploy to Cloud Run
echo "📋 Deploying to Cloud Run..."
gcloud run deploy ${SERVICE_NAME} \
  --image ${IMAGE_NAME} \
  --platform managed \
  --region ${REGION} \
  --allow-unauthenticated \
  --update-env-vars "REACT_APP_API_URL=https://precepgo-adk-panel-724021185717.us-central1.run.app" \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📍 Service URL:"
gcloud run services describe ${SERVICE_NAME} \
  --region ${REGION} \
  --format="value(status.url)"
```

Make it executable:
```bash
chmod +x deploy_frontend.sh
```

### Step 4: Environment Variables

Create a `.env.production` file:

```env
REACT_APP_API_URL=https://precepgo-adk-panel-724021185717.us-central1.run.app
REACT_APP_ENV=production
```

### Step 5: Deploy

```bash
./deploy_frontend.sh
```

---

## 🔧 Frontend Integration Example

### Fetch API Helper

```javascript
// api.js
const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://precepgo-adk-panel-724021185717.us-central1.run.app';

export const api = {
  // Health check
  async healthCheck() {
    const response = await fetch(`${API_BASE_URL}/health`);
    return response.json();
  },

  // Get agent status
  async getAgentStatus(agentName) {
    const response = await fetch(`${API_BASE_URL}/agents/${agentName}/status`);
    return response.json();
  },

  // Create demo evaluation
  async createDemoEvaluation() {
    const response = await fetch(`${API_BASE_URL}/agents/evaluation/create-demo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    return response.json();
  },

  // Generate scenario
  async generateScenario() {
    const response = await fetch(`${API_BASE_URL}/mentor/make-scenario`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    return response.json();
  },

  // Run safety check
  async runSafetyCheck() {
    const response = await fetch(`${API_BASE_URL}/agents/notification/safety-check`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    return response.json();
  },

  // Generate COA reports
  async generateCOAReports() {
    const response = await fetch(`${API_BASE_URL}/agents/coa-compliance/generate-reports`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    return response.json();
  },

  // Generate site report
  async generateSiteReport() {
    const response = await fetch(`${API_BASE_URL}/agents/site/generate-report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    return response.json();
  },

  // Automated mode - start
  async startAutomatedMode() {
    const response = await fetch(`${API_BASE_URL}/agents/automated-mode/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    return response.json();
  },

  // Automated mode - stop
  async stopAutomatedMode() {
    const response = await fetch(`${API_BASE_URL}/agents/automated-mode/stop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' }
    });
    return response.json();
  },

  // Automated mode - status
  async getAutomatedModeStatus() {
    const response = await fetch(`${API_BASE_URL}/agents/automated-mode/status`);
    return response.json();
  }
};
```

### React Component Example

```jsx
// AgentControl.jsx
import React, { useState, useEffect } from 'react';
import { api } from './api';

function AgentControl() {
  const [status, setStatus] = useState(null);
  const [automatedMode, setAutomatedMode] = useState(false);

  useEffect(() => {
    // Check automated mode status every 5 seconds
    const interval = setInterval(async () => {
      const status = await api.getAutomatedModeStatus();
      setAutomatedMode(status.active);
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  const handleCreateEvaluation = async () => {
    try {
      const result = await api.createDemoEvaluation();
      console.log('Evaluation created:', result);
      alert('✅ Evaluation created successfully!');
    } catch (error) {
      console.error('Error:', error);
      alert('❌ Failed to create evaluation');
    }
  };

  const handleGenerateScenario = async () => {
    try {
      const result = await api.generateScenario();
      console.log('Scenario generated:', result);
      alert('✅ Scenario generated successfully!');
    } catch (error) {
      console.error('Error:', error);
      alert('❌ Failed to generate scenario');
    }
  };

  const handleStartAutomatedMode = async () => {
    try {
      const result = await api.startAutomatedMode();
      setAutomatedMode(true);
      alert('✅ Automated mode started!');
    } catch (error) {
      console.error('Error:', error);
      alert('❌ Failed to start automated mode');
    }
  };

  return (
    <div>
      <h1>Agent Control Panel</h1>
      
      {automatedMode && (
        <div className="alert">
          🤖 Automated mode is active
        </div>
      )}

      <button 
        onClick={handleCreateEvaluation}
        disabled={automatedMode}
      >
        Create Demo Evaluation
      </button>

      <button 
        onClick={handleGenerateScenario}
        disabled={automatedMode}
      >
        Generate Scenario
      </button>

      <button onClick={handleStartAutomatedMode}>
        Start Automated Mode
      </button>
    </div>
  );
}

export default AgentControl;
```

---

## 📋 Environment Variables for Frontend

| Variable | Value | Required |
|----------|-------|----------|
| `REACT_APP_API_URL` | `https://precepgo-adk-panel-724021185717.us-central1.run.app` | ✅ Yes |
| `REACT_APP_ENV` | `production` | ❌ No |

---

## 🔐 CORS Configuration

The backend already allows CORS from all origins. If you need to restrict it, update the backend's CORS settings in `main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.run.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 🧪 Testing Endpoints

### Test Health Check
```bash
curl https://precepgo-adk-panel-724021185717.us-central1.run.app/health
```

### Test Create Evaluation
```bash
curl -X POST https://precepgo-adk-panel-724021185717.us-central1.run.app/agents/evaluation/create-demo \
  -H "Content-Type: application/json"
```

### Test Automated Mode Status
```bash
curl https://precepgo-adk-panel-724021185717.us-central1.run.app/agents/automated-mode/status
```

---

## 📝 Notes

1. **Error Handling**: All endpoints return JSON. Check for `ok: true` in responses.

2. **Polling**: For real-time updates, poll the status endpoints every 5-10 seconds.

3. **Automated Mode**: When automated mode is active, disable manual agent buttons in the UI.

4. **Timeouts**: Some operations (like generating evaluations) may take 30-60 seconds.

5. **Rate Limiting**: Be mindful of API rate limits. Don't spam requests.

---

## 🆘 Troubleshooting

### CORS Errors
- Ensure backend CORS middleware is configured correctly
- Check that frontend is using the correct API URL

### 404 Errors
- Verify the service URL is correct
- Check that the endpoint path matches exactly

### Timeout Errors
- Increase timeout in Cloud Run deployment (currently 300 seconds)
- Consider implementing retry logic with exponential backoff

### Authentication Errors
- Backend is currently configured with `--allow-unauthenticated`
- No authentication tokens needed for API calls

---

## 📞 Support

For backend issues or questions:
- Check backend logs: `gcloud run logs read precepgo-adk-panel --region us-central1`
- Verify service status: `gcloud run services describe precepgo-adk-panel --region us-central1`

---

**Last Updated:** November 5, 2025
**Backend Version:** Latest (with automated mode)
**Backend Service:** `precepgo-adk-panel`

