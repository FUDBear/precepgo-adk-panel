# PrecepGo ADK Panel - Quick API Reference

## Base URL
```
https://precepgo-adk-panel-724021185717.us-central1.run.app
```

## Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/agents/evaluation/create-demo` | Create demo evaluation |
| `POST` | `/mentor/make-scenario` | Generate scenario |
| `POST` | `/agents/notification/safety-check` | Run safety check |
| `POST` | `/agents/coa-compliance/generate-reports` | Generate COA reports |
| `POST` | `/agents/site/generate-report` | Generate site report (analyzes all evaluations) |
| `POST` | `/agents/automated-mode/start` | Start automated mode (15 min) |
| `POST` | `/agents/automated-mode/stop` | Stop automated mode |
| `GET` | `/agents/automated-mode/status` | Get automated mode status |
| `GET` | `/agents/{agent_name}/status` | Get agent status |

## Agent Names
- `evaluation_agent`
- `scenario_agent`
- `notification_agent`
- `coa_agent`
- `site_agent`

## Response Format
All endpoints return JSON:
```json
{
  "ok": true,
  "data": { ... }
}
```

## Error Format
```json
{
  "ok": false,
  "detail": "Error message"
}
```

## Example Usage

```javascript
// Create evaluation
const response = await fetch('https://precepgo-adk-panel-724021185717.us-central1.run.app/agents/evaluation/create-demo', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' }
});
const data = await response.json();
```

```javascript
// Generate site report
const response = await fetch('https://precepgo-adk-panel-724021185717.us-central1.run.app/agents/site/generate-report', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' }
});
const data = await response.json();
// Returns: { ok: true, report_id: "abc123", summary: { total_sites: 15, total_preceptors: 20, total_evaluations: 155 } }
```

```javascript
// Check automated mode
const response = await fetch('https://precepgo-adk-panel-724021185717.us-central1.run.app/agents/automated-mode/status');
const status = await response.json();
// Returns: { active: true/false, start_time, end_time, elapsed_minutes, remaining_minutes }
```

