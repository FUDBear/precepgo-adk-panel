# ADK Agent Testing & Usage Guide

## ✅ Current Status

Your agents have been migrated to Google ADK and are properly configured:

- ✅ `evaluation_agent` - Uses `SequentialAgent` with 7 sub-agents
- ✅ `notification_agent` - Uses `SequentialAgent` with 3 sub-agents  
- ✅ `scenario_agent` - Uses `SequentialAgent` with 6 sub-agents
- ✅ `time_agent` - Uses `Agent` with tools
- ✅ `safety_pipeline` - Uses `SequentialAgent` to chain eval → notify → scenario
- ✅ `root_agent` - Main coordinator using `Agent` with all sub-agents

## 🧪 Testing ADK Agents

### Quick Test
```bash
python3 test_adk_agents.py
```

This will verify:
1. ADK imports work
2. Root agent loads correctly
3. All sub-agents are properly configured
4. Agents follow ADK patterns (`Agent`, `SequentialAgent`, `ToolContext`)

### Interactive Testing

**CLI Mode:**
```bash
adk run .
```

**Web UI:**
```bash
adk web
# Open http://localhost:8000
```

**Example Interactions:**
- "Run the safety pipeline" → Triggers complete workflow
- "Create an evaluation" → Runs evaluation_agent
- "Calculate time savings" → Runs time_agent

## 🔄 Automated Mode vs ADK Agents

### Current System (Legacy)

The `/agents/automated-mode/toggle` endpoint uses the **legacy StateAgent scheduler** which:
- Runs agents on timers (every 5 minutes, etc.)
- Uses OLD class-based agents (`EvaluationsAgent`, `NotificationAgent`, etc.)
- Manages state in Firestore `all_states` document

**This is NOT using ADK agents** - it's the old system kept for backward compatibility.

### ADK Agents (New System)

ADK agents are **conversational** - they respond to user prompts, not timers. To use them:

1. **Conversational (Recommended):**
   ```bash
   adk run .  # CLI
   adk web    # Web UI
   ```

2. **Programmatic (For Automation):**
   ```python
   from google.adk.runners import Runner
   from google.adk.sessions import InMemorySessionService
   from agent import root_agent
   
   session_service = InMemorySessionService()
   runner = Runner(
       app_name="precepgo-adk-panel",
       agent=root_agent,
       session_service=session_service
   )
   
   # Run agent programmatically
   result = runner.run(
       user_id="automated-user",
       session_id="auto-session",
       message="Run the safety pipeline"
   )
   ```

## 📋 Going Forward

### ✅ DO Use ADK Patterns

- Use `Agent` and `SequentialAgent` from `google.adk.agents`
- Use `ToolContext` parameter in all tools
- Use key templating `{key?}` in instructions
- Export agents from `agent.py` for ADK CLI/web

### ❌ DON'T Mix Systems

- Don't call OLD class-based agents (`EvaluationsAgent.create_and_save_demo_evaluation()`)
- Don't use `state_agent` scheduler for ADK agents
- Don't create custom scheduling - use ADK's Runner API if needed

## 🚀 Next Steps

1. **Test ADK Agents:**
   ```bash
   python3 test_adk_agents.py
   ```

2. **Try Conversational Interface:**
   ```bash
   adk run .
   # Type: "Run the safety pipeline"
   ```

3. **Deploy ADK Agents:**
   ```bash
   uvx --from google-adk \
   adk deploy cloud_run \
       --project=$PROJECT_ID \
       --region=$REGION \
       --service_name=precepgo-adk-panel \
       --with_ui \
       . \
       -- \
       --service-account=$SERVICE_ACCOUNT \
       --allow-unauthenticated
   ```

## 📝 Notes

- The toggle endpoint (`/agents/automated-mode/toggle`) is for the **legacy system only**
- For ADK agents, use conversational interfaces or programmatic Runner API
- ADK agents don't have built-in scheduling - use external schedulers (cron, Cloud Scheduler) if needed
- See `ADK_MIGRATION_SUMMARY.md` for full migration details

