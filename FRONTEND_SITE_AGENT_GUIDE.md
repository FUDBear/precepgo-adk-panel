# Frontend Guide: Site Agent API Integration

## Overview
The Site Agent analyzes all evaluations from the `agent_evaluations` collection and generates comprehensive site reports listing clinical sites, case types, and preceptor information.

## API Endpoint

### Generate Site Report
**Endpoint:** `POST /agents/site/generate-report`

**Base URL:** 
- Local: `http://localhost:8000`
- Production: `https://precepgo-adk-panel-724021185717.us-central1.run.app`

**Full URL:** `{BASE_URL}/agents/site/generate-report`

**Request:**
```javascript
// No request body needed - just POST
```

**Response:**
```json
{
  "ok": true,
  "report_id": "abc123xyz",
  "summary": {
    "total_sites": 15,
    "total_preceptors": 20,
    "total_evaluations": 155
  },
  "message": "Site report generated successfully"
}
```

**Error Response:**
```json
{
  "detail": "Site Agent not available. Please ensure agents/site_agent.py is properly configured."
}
```

## Frontend Implementation Examples

### React/Next.js Example

```javascript
// utils/api.js or similar
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const generateSiteReport = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/agents/site/generate-report`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to generate site report');
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error generating site report:', error);
    throw error;
  }
};
```

### React Component Example

```jsx
import { useState } from 'react';
import { generateSiteReport } from '@/utils/api';

export default function SiteReportGenerator() {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  const handleGenerateReport = async () => {
    setLoading(true);
    setError(null);
    setReport(null);

    try {
      const result = await generateSiteReport();
      
      if (result.ok) {
        setReport(result);
        console.log('Report generated:', result.report_id);
      } else {
        setError('Failed to generate report');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="site-report-generator">
      <button 
        onClick={handleGenerateReport}
        disabled={loading}
        className="btn btn-primary"
      >
        {loading ? 'Generating...' : '🏥 Generate Site Report'}
      </button>

      {error && (
        <div className="alert alert-error">
          Error: {error}
        </div>
      )}

      {report && (
        <div className="alert alert-success">
          <h3>✅ Site Report Generated Successfully</h3>
          <p><strong>Report ID:</strong> {report.report_id}</p>
          <p><strong>Total Sites:</strong> {report.summary.total_sites}</p>
          <p><strong>Total Preceptors:</strong> {report.summary.total_preceptors}</p>
          <p><strong>Total Evaluations:</strong> {report.summary.total_evaluations}</p>
          <p>
            View report in Firestore: <code>agent_sites/{report.report_id}</code>
          </p>
        </div>
      )}
    </div>
  );
}
```

### Vue.js Example

```vue
<template>
  <div class="site-report-generator">
    <button 
      @click="generateReport"
      :disabled="loading"
      class="btn btn-primary"
    >
      {{ loading ? 'Generating...' : '🏥 Generate Site Report' }}
    </button>

    <div v-if="error" class="alert alert-error">
      Error: {{ error }}
    </div>

    <div v-if="report" class="alert alert-success">
      <h3>✅ Site Report Generated Successfully</h3>
      <p><strong>Report ID:</strong> {{ report.report_id }}</p>
      <p><strong>Total Sites:</strong> {{ report.summary.total_sites }}</p>
      <p><strong>Total Preceptors:</strong> {{ report.summary.total_preceptors }}</p>
      <p><strong>Total Evaluations:</strong> {{ report.summary.total_evaluations }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const loading = ref(false);
const report = ref(null);
const error = ref(null);

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const generateReport = async () => {
  loading.value = true;
  error.value = null;
  report.value = null;

  try {
    const response = await fetch(`${API_BASE_URL}/agents/site/generate-report`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.detail || 'Failed to generate site report');
    }

    const data = await response.json();
    report.value = data;
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
};
</script>
```

### Vanilla JavaScript Example

```javascript
// siteAgent.js
const API_BASE_URL = 'http://localhost:8000'; // or your production URL

async function generateSiteReport() {
  const button = document.getElementById('generateReportBtn');
  const resultDiv = document.getElementById('reportResult');
  
  button.disabled = true;
  button.textContent = 'Generating...';
  resultDiv.innerHTML = '<p>⏳ Generating site report...</p>';

  try {
    const response = await fetch(`${API_BASE_URL}/agents/site/generate-report`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    const data = await response.json();

    if (data.ok) {
      resultDiv.innerHTML = `
        <div class="success">
          <h3>✅ Site Report Generated</h3>
          <p><strong>Report ID:</strong> ${data.report_id}</p>
          <p><strong>Total Sites:</strong> ${data.summary.total_sites}</p>
          <p><strong>Total Preceptors:</strong> ${data.summary.total_preceptors}</p>
          <p><strong>Total Evaluations:</strong> ${data.summary.total_evaluations}</p>
        </div>
      `;
    } else {
      resultDiv.innerHTML = `<div class="error">Error: ${data.detail || 'Unknown error'}</div>`;
    }
  } catch (error) {
    resultDiv.innerHTML = `<div class="error">Error: ${error.message}</div>`;
  } finally {
    button.disabled = false;
    button.textContent = '🏥 Generate Site Report';
  }
}

// HTML
// <button id="generateReportBtn" onclick="generateSiteReport()">🏥 Generate Site Report</button>
// <div id="reportResult"></div>
```

## Response Data Structure

### Success Response
```typescript
interface SiteReportResponse {
  ok: boolean;
  report_id: string;
  summary: {
    total_sites: number;
    total_preceptors: number;
    total_evaluations: number;
  };
  message: string;
}
```

### Report Data in Firestore
After generation, the report is saved to `agent_sites/{report_id}` with:
- `report_text`: AI-generated comprehensive report
- `analysis_data`: Structured data with:
  - `sites`: Array of site objects with case types, evaluation counts, preceptors
  - `preceptors`: Array of preceptor objects with student counts, case types, evaluation counts
- `generated_at`: Timestamp
- `total_evaluations_analyzed`: Number of evaluations processed

## Error Handling

### Common Errors

1. **503 Service Unavailable**
   ```json
   {
     "detail": "Site Agent not available. Please ensure agents/site_agent.py is properly configured."
   }
   ```
   - **Solution**: Check that the Site Agent is initialized in `main.py`

2. **500 Internal Server Error**
   ```json
   {
     "detail": "Error generating site report: [error message]"
   }
   ```
   - **Solution**: Check server logs for detailed error information

3. **Network Errors**
   - **Solution**: Verify API_BASE_URL is correct and server is running

## Loading States

The report generation can take 10-30 seconds depending on:
- Number of evaluations in the database
- AI processing time (Gemini API)
- Network latency

**Recommendation**: Show a loading spinner and disable the button during generation.

## Example Loading UI

```jsx
const [loading, setLoading] = useState(false);

// In your component
<button disabled={loading}>
  {loading ? (
    <>
      <Spinner /> Generating Site Report...
    </>
  ) : (
    '🏥 Generate Site Report'
  )}
</button>
```

## Fetching Generated Reports

To fetch a generated report from Firestore:

```javascript
// If you have Firestore SDK in your frontend
import { getFirestore, doc, getDoc } from 'firebase/firestore';

const fetchSiteReport = async (reportId) => {
  const db = getFirestore();
  const reportRef = doc(db, 'agent_sites', reportId);
  const reportSnap = await getDoc(reportRef);
  
  if (reportSnap.exists()) {
    return reportSnap.data();
  } else {
    throw new Error('Report not found');
  }
};
```

## Integration Checklist

- [ ] Set `API_BASE_URL` environment variable or constant
- [ ] Create API utility function for `generateSiteReport()`
- [ ] Add button/UI element to trigger report generation
- [ ] Implement loading state during generation
- [ ] Handle success response and display report summary
- [ ] Handle and display errors appropriately
- [ ] Optionally: Add link to view full report in Firestore
- [ ] Test with local development server
- [ ] Test with production API endpoint

## Notes

- The report generation is **asynchronous** and may take time
- Reports are saved to Firestore collection `agent_sites`
- Each report has a unique `report_id` for reference
- The report includes AI-generated insights and structured data
- Previous reports are not overwritten - each generation creates a new report

