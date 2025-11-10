# Frontend Integration Guide: Time Savings Analytics Agent

## Backend Service URL

**Production Backend:**
```
https://precepgo-adk-panel-724021185717.us-central1.run.app
```

**Note:** The backend is already deployed and CORS is configured to allow requests from your frontend.

---

## Time Savings Analytics Agent API Endpoints

### 1. Get Time Savings Analytics

**Endpoint:** `GET /agents/time-savings/analytics`

**Query Parameters:**
- `timeframe` (required): `daily` | `weekly` | `monthly` | `semester` | `all_time`
- `user_id` (optional): Filter by specific user ID
- `include_insights` (optional): `true` | `false` (default: `true`)

**Example Request:**
```typescript
const response = await fetch(
  'https://precepgo-adk-panel-724021185717.us-central1.run.app/agents/time-savings/analytics?timeframe=monthly&include_insights=true',
  {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  }
);

const data = await response.json();
```

**Response Format:**
```typescript
{
  "timeframe": "monthly",
  "total_hours_saved": 745.5,
  "fte_equivalent": 4.3,
  "cost_savings": 32165.25,
  "total_tasks": 150,
  "task_breakdown": {
    "evaluation_completion": 45,
    "admin_review": 45,
    "scenario_generation": 12,
    "coa_compliance_check": 8,
    "notification_check": 25,
    "problem_identification": 15
  },
  "agent_breakdown": {
    "evaluations_agent": 315.0,
    "scenario_agent": 25.6,
    "coa_agent": 8.27,
    "notification_agent": 15.67
  },
  "top_agent": "evaluations_agent",
  "average_hourly_rate": 43.75,
  "insights": "AI-generated insights string here..."
}
```

---

### 2. Get Detailed Time Savings Report

**Endpoint:** `GET /agents/time-savings/report`

**Query Parameters:**
- `timeframe` (required): `daily` | `weekly` | `monthly` | `semester` | `all_time`
- `format` (optional): `summary` | `detailed` (default: `summary`)
- `user_id` (optional): Filter by specific user ID
- `include_insights` (optional): `true` | `false` (default: `true`)

**Example Request:**
```typescript
const response = await fetch(
  'https://precepgo-adk-panel-724021185717.us-central1.run.app/agents/time-savings/report?timeframe=monthly&format=detailed&include_insights=true',
  {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  }
);

const report = await response.json();
```

**Response Format:**
```typescript
{
  "format": "detailed",
  "timeframe": "monthly",
  "generated_at": "2025-01-05T22:15:00.000Z",
  "metrics": {
    "total_hours_saved": 745.5,
    "fte_equivalent": 4.3,
    "cost_savings": 32165.25,
    "total_tasks": 150
  },
  "breakdown": {
    "by_task_type": {
      "evaluation_completion": 45,
      "admin_review": 45,
      "scenario_generation": 12,
      // ... etc
    },
    "by_agent": {
      "evaluations_agent": 315.0,
      "scenario_agent": 25.6,
      // ... etc
    }
  },
  "top_agent": "evaluations_agent",
  "insights": "AI-generated insights..."
}
```

---

### 3. Start Task Tracking

**Endpoint:** `POST /agents/time-savings/task/start`

**Request Body:**
```typescript
{
  "task_type": "evaluation_completion" | "admin_review" | "problem_identification" | 
                "test_generation" | "coa_compliance_check" | "scenario_generation" | 
                "notification_check",
  "user_id": "user123",
  "is_ai_assisted": true,
  "agent_name": "evaluations_agent", // optional
  "metadata": {} // optional - any additional data
}
```

**Response:**
```typescript
{
  "task_id": "abc123xyz",
  "status": "started"
}
```

---

### 4. Complete Task Tracking

**Endpoint:** `POST /agents/time-savings/task/complete`

**Request Body:**
```typescript
{
  "task_id": "abc123xyz",
  "duration_minutes": 8.5, // optional - will calculate if not provided
  "metadata": {} // optional
}
```

**Response:**
```typescript
{
  "status": "completed",
  "time_saved_minutes": 42.0,
  "time_saved_hours": 0.7
}
```

---

## Timeframe Options

Use these exact string values for the `timeframe` parameter:

- `"daily"` - Last 24 hours
- `"weekly"` - Last 7 days
- `"monthly"` - Last 30 days
- `"semester"` - Last 120 days (~4 months)
- `"all_time"` - All available data

---

## Task Type Enum Values

Use these exact string values for `task_type`:

- `"evaluation_completion"` - Preceptor evaluation completion
- `"admin_review"` - Administrative review and filing
- `"problem_identification"` - Problem and trend identification
- `"test_generation"` - Remedial test question creation
- `"coa_compliance_check"` - COA standards compliance check
- `"scenario_generation"` - Clinical scenario generation
- `"notification_check"` - Manual monitoring and alert generation

---

## Expected Realistic Savings Values

Based on realistic benchmarks, expect these savings per task:

- **Evaluation Completion**: ~42 minutes saved per evaluation
- **Admin Review**: ~23 minutes saved per review
- **Problem Identification**: ~83 minutes saved per identification
- **Scenario Generation**: ~128 minutes saved per scenario
- **COA Compliance Check**: ~62 minutes saved per check
- **Notification Check**: ~44 minutes saved per check

For a 100-student program over 1 month, expect:
- **Total Hours Saved**: 745+ hours
- **FTE Equivalent**: 4.3+ FTE
- **Cost Savings**: $32,000+ (using $43.75/hr average)

---

## Dashboard Display Recommendations

### Key Metrics to Display

1. **Total Hours Saved** (large, prominent)
   - Format: `745.5 hours` or `745.5 hrs`
   - Show with trend indicator (↑/↓)

2. **FTE Equivalent**
   - Format: `4.3 FTE`
   - Helpful tooltip: "Full-Time Equivalent employees saved"

3. **Cost Savings**
   - Format: `$32,165.25` or `$32.2K`
   - Use currency formatting

4. **Total Tasks Automated**
   - Format: `150 tasks`

### Charts to Include

1. **Time Savings Over Time** (Line Chart)
   - X-axis: Date/Time
   - Y-axis: Hours Saved
   - Show trend line

2. **Savings by Task Type** (Bar Chart or Pie Chart)
   - Show breakdown from `task_breakdown`
   - Color-code by task type

3. **Savings by Agent** (Bar Chart)
   - Show breakdown from `agent_breakdown`
   - Highlight top agent

4. **Comparison View** (Before/After)
   - Show manual time vs AI-assisted time
   - Example: "50 min → 8 min (84% faster)"

### AI Insights Section

Display the `insights` field in a highlighted box:
- Use yellow/amber background (`#fff3cd`)
- Format as bullet points or paragraphs
- Include an icon (💡 or 🤖)

---

## Example React Component

```typescript
import React, { useState, useEffect } from 'react';

const BACKEND_URL = 'https://precepgo-adk-panel-724021185717.us-central1.run.app';

interface TimeSavingsData {
  timeframe: string;
  total_hours_saved: number;
  fte_equivalent: number;
  cost_savings: number;
  total_tasks: number;
  task_breakdown: Record<string, number>;
  agent_breakdown: Record<string, number>;
  top_agent: string;
  insights: string;
}

export const TimeSavingsDashboard: React.FC = () => {
  const [timeframe, setTimeframe] = useState<'daily' | 'weekly' | 'monthly' | 'semester' | 'all_time'>('monthly');
  const [data, setData] = useState<TimeSavingsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAnalytics = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(
        `${BACKEND_URL}/agents/time-savings/analytics?timeframe=${timeframe}&include_insights=true`
      );
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const result = await response.json();
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch analytics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAnalytics();
  }, [timeframe]);

  if (loading) return <div>Loading analytics...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!data) return null;

  return (
    <div className="time-savings-dashboard">
      {/* Timeframe Selector */}
      <select 
        value={timeframe} 
        onChange={(e) => setTimeframe(e.target.value as typeof timeframe)}
      >
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
        <option value="semester">Semester</option>
        <option value="all_time">All Time</option>
      </select>

      {/* Key Metrics */}
      <div className="metrics-grid">
        <div className="metric-card">
          <h3>Total Hours Saved</h3>
          <p className="metric-value">{data.total_hours_saved.toFixed(1)} hrs</p>
        </div>
        
        <div className="metric-card">
          <h3>FTE Equivalent</h3>
          <p className="metric-value">{data.fte_equivalent.toFixed(1)} FTE</p>
        </div>
        
        <div className="metric-card">
          <h3>Cost Savings</h3>
          <p className="metric-value">
            ${data.cost_savings.toLocaleString('en-US', { 
              minimumFractionDigits: 2, 
              maximumFractionDigits: 2 
            })}
          </p>
        </div>
        
        <div className="metric-card">
          <h3>Total Tasks</h3>
          <p className="metric-value">{data.total_tasks}</p>
        </div>
      </div>

      {/* Task Breakdown */}
      <div className="task-breakdown">
        <h3>Savings by Task Type</h3>
        {Object.entries(data.task_breakdown).map(([task, count]) => (
          <div key={task} className="task-item">
            <span>{task.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
            <span>{count} tasks</span>
          </div>
        ))}
      </div>

      {/* Agent Breakdown */}
      <div className="agent-breakdown">
        <h3>Savings by Agent</h3>
        {Object.entries(data.agent_breakdown).map(([agent, hours]) => (
          <div key={agent} className="agent-item">
            <span>{agent.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
            <span>{hours.toFixed(1)} hrs</span>
          </div>
        ))}
      </div>

      {/* Top Agent */}
      {data.top_agent && (
        <div className="top-agent">
          <h3>🏆 Top Performing Agent</h3>
          <p>{data.top_agent.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</p>
        </div>
      )}

      {/* AI Insights */}
      {data.insights && (
        <div className="insights-box">
          <h3>💡 AI-Powered Insights</h3>
          <div className="insights-content">{data.insights}</div>
        </div>
      )}
    </div>
  );
};
```

---

## Error Handling

The API may return errors in this format:

```typescript
{
  "detail": "Error message here"
}
```

Handle these cases:
- `404` - Endpoint not found
- `500` - Server error (check backend logs)
- Network errors - Show user-friendly message

---

## Important Notes

1. **Scheduled Analytics**: The backend automatically runs analytics every hour and saves results to Firestore. Your frontend queries will get the latest calculated data.

2. **Real-time Updates**: For real-time updates, poll the analytics endpoint every 30-60 seconds, or use WebSocket if you implement it.

3. **CORS**: Already configured in the backend to allow your frontend origin.

4. **No Authentication Required**: All endpoints are publicly accessible (as per current backend configuration).

5. **Data Persistence**: All time savings data is stored in Firestore collection `agent_time` document `time_saved`. The backend aggregates this data when you request analytics.

---

## Testing

Test the endpoints directly:

```bash
# Get monthly analytics
curl "https://precepgo-adk-panel-724021185717.us-central1.run.app/agents/time-savings/analytics?timeframe=monthly"

# Get detailed report
curl "https://precepgo-adk-panel-724021185717.us-central1.run.app/agents/time-savings/report?timeframe=all_time&format=detailed"
```

---

## Next Steps for Frontend

1. ✅ Create a Time Savings Analytics component/page
2. ✅ Add timeframe selector dropdown
3. ✅ Display key metrics (hours, FTE, cost, tasks)
4. ✅ Create charts for breakdowns (task type, agent)
5. ✅ Display AI insights in a highlighted section
6. ✅ Add refresh button to manually update data
7. ✅ Implement auto-refresh every 30-60 seconds
8. ✅ Add loading states and error handling
9. ✅ Style with your design system (Tailwind/Material/etc.)

---

## Support

If you encounter issues:
1. Check backend logs: `gcloud logging read "resource.type=cloud_run_revision" --limit 50`
2. Verify CORS is working (check browser Network tab)
3. Ensure timeframe values match exactly (case-sensitive)
4. Verify backend is running and accessible

