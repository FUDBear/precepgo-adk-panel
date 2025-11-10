"""
Notification Agent - ADK Compliant
Monitors evaluations for dangerous ratings and creates notification records.
"""

import html
from datetime import datetime
from typing import Dict, Any, List
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Google ADK imports
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import ToolContext


# ===========================================
# TOOLS (Functions with ToolContext)
# ===========================================

def check_for_dangerous_ratings(tool_context: ToolContext) -> dict:
    """Checks if the evaluation has any dangerous (-1) PC ratings.

    Returns:
        dict: Status and list of dangerous fields
    """
    scores = tool_context.state.get("evaluation_scores", {})
    dangerous_fields = []

    # Check PC scores for -1 (dangerous rating)
    for i in range(11):
        pc_key = f"pc_{i}"
        if scores.get(pc_key) == -1:
            dangerous_fields.append(pc_key)

    tool_context.state["dangerous_fields"] = dangerous_fields
    tool_context.state["has_dangerous_ratings"] = len(dangerous_fields) > 0

    return {
        "status": "success",
        "has_dangerous": len(dangerous_fields) > 0,
        "dangerous_count": len(dangerous_fields),
        "fields": dangerous_fields
    }


def generate_notification_email_html(tool_context: ToolContext) -> dict:
    """Generates HTML email content for the notification.

    Returns:
        dict: Status and generated email HTML
    """
    dangerous_fields = tool_context.state.get("dangerous_fields", [])

    if not dangerous_fields:
        return {
            "status": "skipped",
            "message": "No dangerous ratings found"
        }

    # Get evaluation data from state
    student = tool_context.state.get("selected_student", {})
    case = tool_context.state.get("selected_case", {})
    preceptor = tool_context.state.get("selected_preceptor", {})
    eval_doc_id = tool_context.state.get("evaluation_doc_id", "unknown")
    comment = tool_context.state.get("preceptor_comment", "")

    # Escape HTML
    student_name = html.escape(student.get("name", "Unknown"))
    preceptor_name = html.escape(f"{preceptor.get('firstName', '')} {preceptor.get('lastName', '')}")
    case_name = html.escape(case.get("name", "Unknown"))
    comments_escaped = html.escape(comment).replace('\n', '<br>')

    # Metric names
    metric_names = {
        "pc_0": "Appropriate Intervention",
        "pc_1": "Appropriate Pain Control",
        "pc_2": "Receptive to Instruction",
        "pc_3": "Communicated Effectively",
        "pc_4": "Troubleshoots Effectively",
        "pc_5": "Calm/Professional Demeanor",
        "pc_6": "Recognizes Limitations",
        "pc_7": "Professionalism and Integrity",
        "pc_8": "Accountable for Care",
        "pc_9": "Documentation Reflects Care",
        "pc_10": "Follows Universal Precautions"
    }

    # Build HTML
    metrics_html = ""
    for field in dangerous_fields:
        metric_name = metric_names.get(field, field)
        metrics_html += f"""
            <div class="metric-item">
                <strong>{metric_name}</strong> <span class="negative-field">({field}) - DANGEROUS</span>
            </div>
        """

    email_html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .header {{ background-color: #dc3545; color: white; padding: 20px; }}
            .content {{ padding: 20px; }}
            .evaluation-info {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; }}
            .negative-metrics {{ background-color: #f8d7da; padding: 15px; border-radius: 5px; }}
            .negative-field {{ color: #dc3545; font-weight: bold; }}
            .metric-item {{ margin: 8px 0; padding: 8px; background-color: white; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>⚠️ Negative Evaluation Alert</h2>
        </div>
        <div class="content">
            <div class="evaluation-info">
                <h3>📋 Evaluation Information</h3>
                <p><strong>Student:</strong> {student_name}</p>
                <p><strong>Preceptor:</strong> {preceptor_name}</p>
                <p><strong>Case:</strong> {case_name}</p>
                <p><strong>Document ID:</strong> {eval_doc_id}</p>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>

            <div class="negative-metrics">
                <h3>⚠️ Dangerous Ratings</h3>
                <p>The following metrics received a DANGEROUS rating (-1):</p>
                {metrics_html}
            </div>

            <div>
                <h3>💬 Preceptor Comments</h3>
                <p>{comments_escaped if comments_escaped else '<em>No comments provided</em>'}</p>
            </div>
        </div>
    </body>
    </html>
    """

    tool_context.state["notification_email_html"] = email_html

    return {
        "status": "success",
        "email_length": len(email_html),
        "dangerous_count": len(dangerous_fields)
    }


def save_notification_to_firestore(tool_context: ToolContext) -> dict:
    """Saves notification record to Firestore.

    Returns:
        dict: Save status and document ID
    """
    dangerous_fields = tool_context.state.get("dangerous_fields", [])

    if not dangerous_fields:
        return {
            "status": "skipped",
            "message": "No dangerous ratings to notify about"
        }

    try:
        # Use FIREBASE_PROJECT_ID if available, otherwise auto-detect
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            db = firestore.Client(project=project_id)
        else:
            db = firestore.Client()

        student = tool_context.state.get("selected_student", {})
        case = tool_context.state.get("selected_case", {})
        preceptor = tool_context.state.get("selected_preceptor", {})
        eval_doc_id = tool_context.state.get("evaluation_doc_id", "unknown")
        email_html = tool_context.state.get("notification_email_html", "")

        notification = {
            "evaluation_doc_id": eval_doc_id,
            "preceptee_name": student.get("name"),
            "preceptee_id": student.get("id"),
            "preceptor_name": f"{preceptor.get('firstName', '')} {preceptor.get('lastName', '')}",
            "case_type": case.get("name"),
            "negative_fields": dangerous_fields,
            "email": email_html,
            "notification_sent_at": SERVER_TIMESTAMP,
            "created_at": SERVER_TIMESTAMP,
            "agent": "notification_agent",
            "adk_version": "1.0"
        }

        doc_ref = db.collection("agent_notifications").add(notification)
        doc_id = doc_ref[1].id

        tool_context.state["notification_doc_id"] = doc_id

        return {
            "status": "success",
            "doc_id": doc_id,
            "dangerous_count": len(dangerous_fields),
            "student_name": student.get("name")
        }
    except Exception as e:
        return {
            "status": "error",
            "error_message": str(e)
        }


# ===========================================
# AGENTS (ADK Agent instances)
# ===========================================

# Dangerous Rating Checker
dangerous_checker = Agent(
    name="dangerous_checker",
    model="gemini-2.0-flash",
    description="Checks evaluations for dangerous (-1) ratings",
    instruction="""
    You check evaluation scores for dangerous ratings that require notification.

    Evaluation scores: {evaluation_scores?}

    Check all PC (Professional Competency) scores for -1 values, which indicate dangerous behavior.
    Use your tool to identify dangerous ratings.
    """,
    tools=[check_for_dangerous_ratings]
)

# Email Generator
email_generator = Agent(
    name="email_generator",
    model="gemini-2.0-flash",
    description="Generates HTML email notifications for dangerous ratings",
    instruction="""
    You generate email notifications for dangerous evaluation ratings.

    Dangerous fields found: {dangerous_fields?}
    Has dangerous ratings: {has_dangerous_ratings?}

    Student: {selected_student?}
    Case: {selected_case?}
    Preceptor: {selected_preceptor?}

    Only generate email if dangerous ratings were found.
    Use your tool to create a professional HTML email notification.
    """,
    tools=[generate_notification_email_html]
)

# Notification Saver
notification_saver = Agent(
    name="notification_saver",
    model="gemini-2.0-flash",
    description="Saves notification records to Firestore",
    instruction="""
    You save notification records to Firestore.

    Dangerous fields: {dangerous_fields?}
    Email HTML: {notification_email_html?}

    Student: {selected_student?}
    Case: {selected_case?}
    Evaluation ID: {evaluation_doc_id?}

    Only save if dangerous ratings were found.
    Use your tool to save the notification to agent_notifications collection.
    """,
    tools=[save_notification_to_firestore]
)


# ===========================================
# WORKFLOW (Sequential execution)
# ===========================================

notification_agent = SequentialAgent(
    name="notification_agent",
    description="Monitors evaluations for dangerous ratings and creates notification records with HTML emails",
    sub_agents=[
        dangerous_checker,
        email_generator,
        notification_saver
    ]
)


# Export the main agent
__all__ = ["notification_agent"]
