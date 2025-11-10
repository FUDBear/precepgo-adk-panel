"""
Time Savings Agent - ADK Compliant
Calculates time savings from automation.
"""

import os
from datetime import datetime
from typing import Dict, Any
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Google ADK imports
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import ToolContext


# ===========================================
# TOOLS (Functions with ToolContext)
# ===========================================

def calculate_time_savings(tool_context: ToolContext) -> dict:
    """Calculates time savings from agent automation.
    
    Returns:
        dict: Time savings metrics
    """
    try:
        # Use FIREBASE_PROJECT_ID if available, otherwise auto-detect
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            db = firestore.Client(project=project_id)
        else:
            db = firestore.Client()

        # Count documents from each collection
        eval_docs = list(db.collection("agent_evaluations").stream())
        scenario_docs = list(db.collection("agent_scenarios").stream())
        notification_docs = list(db.collection("agent_notifications").stream())

        eval_count = len(eval_docs)
        scenario_count = len(scenario_docs)
        notification_count = len(notification_docs)

        # Time benchmarks (in minutes)
        EVAL_TIME = 42  # Minutes per evaluation
        SCENARIO_TIME = 128  # Minutes per scenario
        NOTIFICATION_TIME = 44  # Minutes per notification

        # Calculate savings
        eval_savings = eval_count * EVAL_TIME
        scenario_savings = scenario_count * SCENARIO_TIME
        notification_savings = notification_count * NOTIFICATION_TIME

        total_minutes = eval_savings + scenario_savings + notification_savings
        total_hours = total_minutes / 60
        total_days = total_hours / 8  # 8-hour work day

        # Store in state
        tool_context.state["time_savings_metrics"] = {
            "evaluations_created": eval_count,
            "scenarios_created": scenario_count,
            "notifications_sent": notification_count,
            "total_tasks": eval_count + scenario_count + notification_count,
            "total_minutes_saved": round(total_minutes, 2),
            "total_hours_saved": round(total_hours, 2),
            "total_days_saved": round(total_days, 2)
        }

        print(f"✅ Calculated time savings: {round(total_hours, 2)} hours ({round(total_days, 2)} days)")

        return {
            "status": "success",
            "total_hours_saved": round(total_hours, 2),
            "total_tasks": eval_count + scenario_count + notification_count,
            "evaluations": eval_count,
            "scenarios": scenario_count,
            "notifications": notification_count
        }
    except Exception as e:
        error_msg = f"Error calculating time savings: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def save_time_savings_report(tool_context: ToolContext) -> dict:
    """Saves time savings report to Firestore.
        
        Returns:
        dict: Save status and document ID
    """
    try:
        metrics = tool_context.state.get("time_savings_metrics", {})
        
        if not metrics:
            return {
                "status": "error",
                "error_message": "No time savings metrics found. Run calculate_time_savings first."
            }

        # Use FIREBASE_PROJECT_ID if available, otherwise auto-detect
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            db = firestore.Client(project=project_id)
        else:
            db = firestore.Client()

        report = {
            **metrics,
            "generated_at": SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now(),
            "agent": "time_agent",
            "adk_version": "1.0"
        }

        doc_ref = db.collection("agent_time_savings").add(report)
        doc_id = doc_ref[1].id

        tool_context.state["time_savings_doc_id"] = doc_id

        print(f"✅ Saved time savings report to Firestore: agent_time_savings/{doc_id}")

        return {
            "status": "success",
            "doc_id": doc_id,
            "total_hours_saved": metrics.get("total_hours_saved", 0)
        }
    except Exception as e:
        error_msg = f"Error saving time savings report: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


# ===========================================
# AGENTS (ADK Agent instances)
# ===========================================

# Time Savings Calculator
time_calculator = Agent(
    name="time_calculator",
    model="gemini-2.0-flash",
    description="Calculates time savings from agent automation",
    instruction="""
    You calculate time savings achieved by the agent system.
    
    IMPORTANT: You MUST use your calculate_time_savings tool to calculate the metrics.
    
    Calculate savings for:
    - Evaluations (42 min each)
    - Scenarios (128 min each)
    - Notifications (44 min each)
    
    Call your tool to calculate time savings metrics.
    """,
    tools=[calculate_time_savings]
            )
            
# Report Saver
time_report_saver = Agent(
    name="time_report_saver",
    model="gemini-2.0-flash",
    description="Saves time savings report to Firestore",
    instruction="""
    You save the calculated time savings report to Firestore.
    
    IMPORTANT: You MUST use your save_time_savings_report tool to save the report.
    
    Time savings metrics: {time_savings_metrics?}
    
    Call your tool to save the report to the agent_time_savings collection.
    """,
    tools=[save_time_savings_report]
)


# ===========================================
# WORKFLOW (Sequential execution)
# ===========================================

time_agent = SequentialAgent(
    name="time_agent",
    description="Calculates and reports time savings from AI automation by counting agent-generated documents and calculating total time saved",
    sub_agents=[
        time_calculator,
        time_report_saver
    ]
)


# Export the main agent
__all__ = ["time_agent"]
