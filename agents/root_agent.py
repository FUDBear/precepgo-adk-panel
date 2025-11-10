"""
PrecepGo ADK Panel - Root Agent
Coordinates all CRNA education agents using Google ADK framework.
"""

from google.adk.agents import Agent, SequentialAgent

# Import all sub-agents
from agents.evaluations_agent import evaluation_agent
from agents.notification_agent import notification_agent
from agents.scenario_agent import scenario_agent
from agents.time_agent import time_agent


# ===========================================
# WORKFLOW: Safety Pipeline
# ===========================================
# This workflow runs evaluation -> notification -> scenario
# demonstrating the Google ADK Sequential pattern

safety_pipeline = SequentialAgent(
    name="safety_pipeline",
    description="Complete safety workflow: creates evaluation, checks for dangerous ratings, sends notifications, and generates learning scenario",
    sub_agents=[
        evaluation_agent,     # Create student evaluation
        notification_agent,   # Check for dangerous ratings & notify
        scenario_agent        # Generate learning scenario
    ]
)


# ===========================================
# ROOT AGENT (Main Coordinator)
# ===========================================

root_agent = Agent(
    name="precepgo_coordinator",
    model="gemini-2.0-flash",
    description="Coordinates CRNA education agents for student safety, evaluations, scenarios, and analytics",
    instruction="""
    You are the PrecepGo ADK Panel coordinator for CRNA (Certified Registered Nurse Anesthetist) education.

    Your mission: Enhance student safety and learning through AI automation.

    **Your Capabilities:**

    1. **Safety Pipeline** (evaluation -> notification -> scenario)
       - Create student evaluations with realistic scores
       - Monitor for dangerous ratings that require immediate attention
       - Send safety notifications to administrators
       - Generate personalized learning scenarios

    2. **Individual Operations**
       - Create evaluations independently
       - Check notifications
       - Generate scenarios
       - Calculate time savings from automation

    3. **Analytics**
       - Track time saved vs manual processes
       - Report on evaluations, scenarios, and notifications created

    **When to transfer:**
    - For complete workflows: transfer to 'safety_pipeline'
    - For evaluations only: transfer to 'evaluation_agent'
    - For notification checks: transfer to 'notification_agent'
    - For scenario generation: transfer to 'scenario_agent'
    - For time savings reports: transfer to 'time_agent'

    **Example interactions:**
    User: "Run the safety pipeline"
    -> Transfer to safety_pipeline

    User: "Create an evaluation"
    -> Transfer to evaluation_agent

    User: "How much time have we saved?"
    -> Transfer to time_agent

    You ensure student safety through automated monitoring and personalized learning.
    """,
    sub_agents=[
        safety_pipeline,
        time_agent
        # Note: evaluation_agent, notification_agent, and scenario_agent
        # are accessible through safety_pipeline, so they should not be
        # listed here to avoid "already has a parent agent" error
    ]
)


# Export the root agent
__all__ = ["root_agent", "safety_pipeline"]
