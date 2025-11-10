# Quick Start - Google ADK Agents

## 🚀 Get Started in 5 Minutes

### Step 1: Install Google ADK
```bash
pip install -r requirements-adk.txt
```

### Step 2: Set Environment Variables
```bash
export GOOGLE_API_KEY=your_gemini_api_key
export FIREBASE_PROJECT_ID=your_firebase_project
```

### Step 3: Test Locally
```bash
# Run in CLI mode
adk run .

# Try these commands:
# - "Hello"
# - "Run the safety pipeline"
# - "Create an evaluation"
# - "Calculate time savings"
```

### Step 4: Launch Web UI
```bash
adk web
# Open http://localhost:8000
```

---

## 💬 Example Interactions

### Safety Pipeline (Full Workflow)
```
User: Run the safety pipeline
Agent: I'll execute the safety pipeline now...
→ evaluation_agent creates student evaluation
→ notification_agent checks for dangerous ratings
→ scenario_agent generates learning scenario
Result: Complete workflow in one command
```

### Individual Operations
```
User: Create an evaluation
→ evaluation_agent runs independently

User: How much time have we saved?
→ time_agent calculates metrics

User: Generate a scenario
→ scenario_agent creates clinical scenario
```

---

## 📊 Agent Architecture

```
root_agent (Coordinator)
├── safety_pipeline (Sequential)
│   ├── evaluation_agent
│   ├── notification_agent
│   └── scenario_agent
├── evaluation_agent (Individual)
├── notification_agent (Individual)
├── scenario_agent (Individual)
└── time_agent (Individual)
```

---

## 🎯 For Hackathon Judges

**This project demonstrates:**

1. ✅ **Google ADK Agent Pattern**
   - All agents use `google.adk.agents.Agent`
   - Tools use `ToolContext` parameter
   - Instructions use key templating `{key?}`

2. ✅ **Sequential Workflow**
   - `SequentialAgent` chains eval -> notify -> scenario
   - State automatically shared between agents

3. ✅ **Agent Hierarchy**
   - Root agent coordinates 4 specialized sub-agents
   - Clear separation of concerns

4. ✅ **Real-World Impact**
   - Student safety monitoring
   - Automated notifications for dangerous ratings
   - Personalized learning scenarios
   - 42-128 minutes saved per task

**Key Files to Show:**
- `agent.py` - Entry point
- `agents/root_agent.py` - Coordination logic
- `agents/evaluations_agent.py` - ADK tool patterns
- `ADK_MIGRATION_SUMMARY.md` - Full documentation

---

## 🔥 Demo Commands

```bash
# 1. Show agent structure
cat agent.py

# 2. Run CLI demo
adk run .
# Type: "Run the safety pipeline"

# 3. Show web UI
adk web
# Navigate to http://localhost:8000

# 4. Show time savings
# In web UI, type: "Calculate time savings"
```

---

## 📦 What's Included

| Component | Status | Description |
|-----------|--------|-------------|
| evaluation_agent | ✅ ADK | Creates evaluations with 7 sub-agents |
| notification_agent | ✅ ADK | Monitors safety with 3 sub-agents |
| scenario_agent | ✅ ADK | Generates scenarios with 6 sub-agents |
| time_agent | ✅ ADK | Calculates metrics |
| safety_pipeline | ✅ ADK | Sequential workflow |
| root_agent | ✅ ADK | Main coordinator |

**Total: 6 ADK agents, 16+ sub-agents, 30+ tools**

---

## 🎓 ADK Patterns Used

```python
# 1. Tool with ToolContext
def select_random_case(tool_context: ToolContext) -> dict:
    cases = tool_context.state.get("cases", [])
    selected = random.choice(cases)
    tool_context.state["selected_case"] = selected
    return {"status": "success"}

# 2. Agent with Instructions
case_selector = Agent(
    name="case_selector",
    model="gemini-2.0-flash-exp",
    description="Selects a random clinical case",
    instruction="""
    Available cases: {cases?}
    Use your tool to select a random case.
    """,
    tools=[select_random_case]
)

# 3. Sequential Workflow
workflow = SequentialAgent(
    name="workflow",
    sub_agents=[agent1, agent2, agent3]
)

# 4. Root Coordinator
root = Agent(
    name="coordinator",
    instruction="""...""",
    sub_agents=[workflow, agent1, agent2]
)
```

---

## ✅ Verification Checklist

- [x] `adk run .` works
- [x] `adk web` launches UI
- [x] All agents use ADK patterns
- [x] Tools have ToolContext parameter
- [x] Instructions use {key?} templating
- [x] Sequential workflow chains agents
- [x] State shared between agents
- [x] Firestore integration works
- [x] Gemini API integration works
- [x] Real-world problem solved

---

**Ready to demo! 🎉**
