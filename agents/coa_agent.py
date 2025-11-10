"""
COA Compliance Agent - ADK Compliant
Tracks COA Standard D requirements for CRNA students by mapping evaluation metrics
to COA standards and generating compliance reports.
"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Set
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Google ADK imports
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import ToolContext

# AC and PC Metric Definitions (matching evaluations_agent.py)
AC_METRICS = {
    "ac_0": "Procedural Room Readiness",
    "ac_1": "Pre-op Assessment",
    "ac_2": "Safely Transfers Care",
    "ac_3": "Medication Administration",
    "ac_4": "Regional Technique",
    "ac_5": "Anesthesia Induction",
    "ac_6": "Airway Management",
    "ac_7": "Ventilatory Management",
    "ac_8": "Procedure(s) Performed",
    "ac_9": "Patient Positioning",
    "ac_10": "Anesthetic Maintenance",
    "ac_11": "Responds to Condition Changes",
    "ac_12": "Emergence Technique",
}

PC_METRICS = {
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
    "pc_10": "Follows Universal Precautions",
}

# Combined metric lookup
ALL_METRICS = {**AC_METRICS, **PC_METRICS}


# ===========================================
# HELPER FUNCTIONS
# ===========================================

def _map_metric_name_to_field(metric_name: str) -> Optional[str]:
    """
    Map metric name from standards.json to actual evaluation field name.
    
    Examples:
        "pc_01" -> "pc_0"
        "pc_11" -> "pc_10" (pc_0 through pc_10 = 11 fields)
        "perf_01" -> "pc_0" (perf maps to pc)
        "ac_01" -> "ac_0"
    
    Args:
        metric_name: Metric name from standards.json (e.g., "pc_01", "perf_05")
    
    Returns:
        Actual evaluation field name (e.g., "pc_0", "ac_0") or None if invalid
    """
    # Handle pc_## format (pc_01 through pc_13)
    if metric_name.startswith("pc_"):
        try:
            num = int(metric_name.split("_")[1])
            if 1 <= num <= 13:
                # pc_01 -> pc_0, pc_02 -> pc_1, ..., pc_13 -> pc_12
                return f"pc_{num - 1}"
        except (ValueError, IndexError):
            pass
    
    # Handle perf_## format (perf_01 through perf_11) - maps to pc_0 through pc_10
    elif metric_name.startswith("perf_"):
        try:
            num = int(metric_name.split("_")[1])
            if 1 <= num <= 11:
                # perf_01 -> pc_0, perf_02 -> pc_1, ..., perf_11 -> pc_10
                return f"pc_{num - 1}"
        except (ValueError, IndexError):
            pass
    
    # Handle ac_## format (ac_01 through ac_13)
    elif metric_name.startswith("ac_"):
        try:
            num = int(metric_name.split("_")[1])
            if 1 <= num <= 13:
                # ac_01 -> ac_0, ac_02 -> ac_1, ..., ac_13 -> ac_12
                return f"ac_{num - 1}"
        except (ValueError, IndexError):
            pass
    
    return None


def _normalize_metric_value(value: Any) -> float:
    """
    Normalize metric value to a number for comparison.
    
    Args:
        value: Metric value (could be int, str, etc.)
    
    Returns:
        Numeric value (0 if invalid)
    """
    if value is None:
        return 0.0
    
    try:
        if isinstance(value, (int, float)):
            return float(value)
        elif isinstance(value, str):
            # Try to parse string numbers
            return float(value.strip())
        else:
            return 0.0
    except (ValueError, TypeError):
        return 0.0


def _check_metric_score(evaluation: Dict[str, Any], metric_key: str) -> bool:
    """
    Check if a metric has a score > 0 in the evaluation.
    
    Args:
        evaluation: Evaluation document dictionary
        metric_key: Metric key (e.g., "ac_0", "pc_5")
    
    Returns:
        True if metric score > 0, False otherwise
    """
    value = evaluation.get(metric_key)
    score = _normalize_metric_value(value)
    return score > 0


# ===========================================
# TOOLS (Functions with ToolContext)
# ===========================================

def load_coa_mapping(tool_context: ToolContext) -> dict:
    """Loads COA standards mapping from standards.json.

    Returns:
        dict: Status and count of loaded standards
    """
    try:
        # Get the directory where this file is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        
        # Try multiple possible paths
        data_paths = [
            os.path.join(project_root, "data"),
            os.path.join(current_dir, "..", "data"),
            "data",
            os.path.join(os.getcwd(), "data")
        ]
        
        data_dir = None
        for path in data_paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path) and os.path.isdir(abs_path):
                data_dir = abs_path
                break
        
        if not data_dir:
            raise FileNotFoundError(f"Could not find data directory. Tried: {data_paths}")
        
        # Load standards
        standards_path = os.path.join(data_dir, "standards.json")
        if not os.path.exists(standards_path):
            raise FileNotFoundError(f"Standards file not found: {standards_path}")
        
        with open(standards_path, "r") as f:
            data = json.load(f)
            
        # Handle both {"standards": [...]} and direct list formats
        if isinstance(data, dict) and "standards" in data:
            standards_list = data["standards"]
        elif isinstance(data, list):
            standards_list = data
        else:
            raise ValueError("Unexpected standards.json format")
        
        # Create mapping: {standard_id: {standard, metrics, ...}}
        mapping = {}
        for standard_data in standards_list:
            standard_id = standard_data.get("id")
            if not standard_id:
                continue
            
            mapping[standard_id] = {
                "id": standard_id,
                "standard": standard_data.get("standard", ""),
                "evaluation_metrics": standard_data.get("evaluation_metrics", [])
            }
        
        tool_context.state["coa_mapping"] = mapping
        
        print(f"✅ Loaded {len(mapping)} COA standards from standards.json")
        
        return {
            "status": "success",
            "standards_loaded": len(mapping)
        }
    except Exception as e:
        error_msg = f"Error loading COA mapping: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def load_students_for_coa(tool_context: ToolContext) -> dict:
    """Loads students data for COA compliance tracking.

    Returns:
        dict: Status and count of loaded students
    """
    try:
        # Get the directory where this file is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        
        # Try multiple possible paths
        data_paths = [
            os.path.join(project_root, "data"),
            os.path.join(current_dir, "..", "data"),
            "data",
            os.path.join(os.getcwd(), "data")
        ]
        
        data_dir = None
        for path in data_paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path) and os.path.isdir(abs_path):
                data_dir = abs_path
                break
        
        if not data_dir:
            raise FileNotFoundError(f"Could not find data directory. Tried: {data_paths}")
        
        # Load students
        students_path = os.path.join(data_dir, "students.json")
        if not os.path.exists(students_path):
            raise FileNotFoundError(f"Students file not found: {students_path}")
        
        with open(students_path, "r") as f:
            data = json.load(f)
            # Handle both {"students": [...]} and [...] formats
            if isinstance(data, dict) and "students" in data:
                students = data["students"]
            elif isinstance(data, list):
                students = data
            else:
                raise ValueError("Unexpected students.json format")
            
            tool_context.state["students"] = students
        
        return {
            "status": "success",
            "students_loaded": len(students)
        }
    except Exception as e:
        error_msg = f"Error loading students: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def fetch_student_evaluations(tool_context: ToolContext) -> dict:
    """Fetches evaluations for all students from Firestore.

    Returns:
        dict: Status and count of fetched evaluations
    """
    try:
        students = tool_context.state.get("students", [])
        
        if not students:
            return {
                "status": "error",
                "error_message": "No students found. Run load_students_for_coa first."
            }
        
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            db = firestore.Client(project=project_id)
        else:
            db = firestore.Client()
        
        all_evaluations = {}
        
        for student in students:
            student_id = student.get("id")
            student_name = student.get("name", "Unknown")
            
            if not student_id:
                continue
            
            evaluations = []
            try:
                evaluations_ref = db.collection('agent_evaluations')
                
                # Query by student_id first (more efficient)
                query_by_id = evaluations_ref.where('preceptee_user_id', '==', student_id).stream()
                for eval_doc in query_by_id:
                    eval_data = eval_doc.to_dict()
                    eval_data['doc_id'] = eval_doc.id
                    evaluations.append(eval_data)
                
                # Also query by student_name (in case some evaluations only have name)
                query_by_name = evaluations_ref.where('preceptee_user_name', '==', student_name).stream()
                for eval_doc in query_by_name:
                    eval_data = eval_doc.to_dict()
                    eval_data['doc_id'] = eval_doc.id
                    # Avoid duplicates
                    if not any(e.get('doc_id') == eval_doc.id for e in evaluations):
                        evaluations.append(eval_data)
                
                all_evaluations[student_id] = evaluations
                
            except Exception as e:
                print(f"⚠️ Error querying evaluations for student {student_id}: {e}")
                all_evaluations[student_id] = []
        
        tool_context.state["student_evaluations"] = all_evaluations
        
        total_evaluations = sum(len(evals) for evals in all_evaluations.values())
        print(f"📊 Fetched {total_evaluations} total evaluations for {len(all_evaluations)} students")
        
        return {
            "status": "success",
            "students_processed": len(all_evaluations),
            "total_evaluations": total_evaluations
        }
    except Exception as e:
        error_msg = f"Error fetching evaluations: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def calculate_compliance_scores(tool_context: ToolContext) -> dict:
    """Calculates COA compliance scores for all students.

    Returns:
        dict: Status and summary of compliance calculations
    """
    try:
        coa_mapping = tool_context.state.get("coa_mapping", {})
        students = tool_context.state.get("students", [])
        student_evaluations = tool_context.state.get("student_evaluations", {})
        student_ids_filter = tool_context.state.get("student_ids_filter")  # Optional filter
        
        if not coa_mapping:
            return {
                "status": "error",
                "error_message": "No COA mapping found. Run load_coa_mapping first."
            }
        
        if not students:
            return {
                "status": "error",
                "error_message": "No students found. Run load_students_for_coa first."
            }
        
        # Filter students if IDs provided
        students_to_process = students
        if student_ids_filter:
            students_to_process = [
                s for s in students
                if s.get("id") in student_ids_filter
            ]
        
        student_reports = []
        aggregated_scores = {}
        
        # Initialize all standards with 0 scores
        for standard_id in coa_mapping.keys():
            aggregated_scores[standard_id] = 0
        
        # Process each student
        for student in students_to_process:
            student_id = student.get("id")
            student_name = student.get("name", "Unknown")
            class_standing = student.get("class_standing", "Unknown")
            
            if not student_id:
                continue
            
            evaluations = student_evaluations.get(student_id, [])
            
            # Track scores for each standard: {standard_id: score_count}
            standard_scores = {}
            
            # Initialize all standards with 0 scores
            for standard_id in coa_mapping.keys():
                standard_scores[standard_id] = 0
            
            # Process each evaluation
            for evaluation in evaluations:
                # Check each COA standard
                for standard_id, standard_data in coa_mapping.items():
                    evaluation_metrics = standard_data.get("evaluation_metrics", [])
                    
                    # Check if any of the mapped metrics have score > 0
                    for metric_name in evaluation_metrics:
                        # Map metric name to actual evaluation field
                        field_name = _map_metric_name_to_field(metric_name)
                        if field_name and _check_metric_score(evaluation, field_name):
                            # This evaluation contributes +1 to this standard
                            standard_scores[standard_id] += 1
                            break  # Only count once per evaluation per standard
            
            # Generate simple score objects
            standard_score_list = [
                {
                    "id": standard_id,
                    "score": score
                }
                for standard_id, score in standard_scores.items()
            ]
            
            # Aggregate scores for consolidated report
            for score_obj in standard_score_list:
                standard_id = score_obj.get("id")
                score = score_obj.get("score", 0)
                if standard_id in aggregated_scores:
                    aggregated_scores[standard_id] += score
            
            student_report = {
                "student_id": student_id,
                "student_name": student_name,
                "class_standing": class_standing,
                "total_standards": len(coa_mapping),
                "total_score": sum(standard_scores.values()),
                "standard_scores": standard_score_list,
                "evaluations_processed": len(evaluations),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "agent": "COA Compliance Agent"
            }
            
            student_reports.append(student_report)
        
        # Generate consolidated standard scores
        standard_score_list = [
            {
                "id": standard_id,
                "score": score
            }
            for standard_id, score in aggregated_scores.items()
        ]
        
        consolidated_report = {
            "students_processed": len(student_reports),
            "total_standards": len(coa_mapping),
            "standard_scores": standard_score_list,
            "student_reports": student_reports,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent": "COA Compliance Agent"
        }
        
        tool_context.state["consolidated_report"] = consolidated_report
        tool_context.state["student_reports"] = student_reports
        
        print(f"✅ Calculated compliance for {len(student_reports)} student(s)")
        
        return {
            "status": "success",
            "students_processed": len(student_reports),
            "total_standards": len(coa_mapping),
            "total_evaluations": sum(r["evaluations_processed"] for r in student_reports)
        }
    except Exception as e:
        error_msg = f"Error calculating compliance: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def save_coa_report(tool_context: ToolContext) -> dict:
    """Saves the consolidated COA compliance report to Firestore.

    Returns:
        dict: Status and document ID
    """
    try:
        consolidated_report = tool_context.state.get("consolidated_report")
        
        if not consolidated_report:
            return {
                "status": "error",
                "error_message": "No consolidated report found. Run calculate_compliance_scores first."
            }
        
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            db = firestore.Client(project=project_id)
        else:
            db = firestore.Client()
        
        # Add timestamp
        report_data = consolidated_report.copy()
        report_data['created_at'] = SERVER_TIMESTAMP if SERVER_TIMESTAMP else datetime.now()
        
        # Create new document with auto-generated ID
        doc_ref = db.collection('agent_coa_reports').add(report_data)
        
        # doc_ref is a tuple (timestamp, DocumentReference)
        doc_id = doc_ref[1].id
        
        tool_context.state["report_doc_id"] = doc_id
        
        print(f"✅ Saved consolidated COA report to Firestore: agent_coa_reports/{doc_id}")
        
        return {
            "status": "success",
            "doc_id": doc_id,
            "students_processed": consolidated_report.get("students_processed", 0),
            "total_standards": consolidated_report.get("total_standards", 0)
        }
    except Exception as e:
        error_msg = f"Error saving report: {str(e)}"
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

# COA Mapping Loader
coa_mapping_loader = Agent(
    name="coa_mapping_loader",
    model="gemini-2.0-flash",
    description="Loads COA standards mapping from standards.json",
    instruction="""
    You load COA standards mapping data needed for compliance tracking.
    
    IMPORTANT: You MUST use your load_coa_mapping tool to load standards from data/standards.json.
    
    Load the COA mapping data into the session state. Do not proceed until the data is loaded.
    """,
    tools=[load_coa_mapping]
)

# Students Loader for COA
coa_students_loader = Agent(
    name="coa_students_loader",
    model="gemini-2.0-flash",
    description="Loads students data for COA compliance tracking",
    instruction="""
    You load students data needed for COA compliance tracking.
    
    IMPORTANT: You MUST use your load_students_for_coa tool to load students from data/students.json.
    
    Load the students data into the session state. Do not proceed until the data is loaded.
    """,
    tools=[load_students_for_coa]
)

# Evaluations Fetcher for COA
coa_evaluations_fetcher = Agent(
    name="coa_evaluations_fetcher",
    model="gemini-2.0-flash",
    description="Fetches evaluations for all students from Firestore",
    instruction="""
    You fetch evaluations for all students from Firestore.
    
    IMPORTANT: You MUST use your fetch_student_evaluations tool to fetch evaluations.
    
    Available students: {students?}
    
    Call your tool to fetch evaluations for all students from the agent_evaluations collection.
    """,
    tools=[fetch_student_evaluations]
)

# Compliance Calculator
compliance_calculator = Agent(
    name="compliance_calculator",
    model="gemini-2.0-flash",
    description="Calculates COA compliance scores for all students",
    instruction="""
    You calculate COA compliance scores for all students based on their evaluations.
    
    IMPORTANT: You MUST use your calculate_compliance_scores tool to calculate compliance.
    
    COA mapping: {coa_mapping?}
    Students: {students?}
    Student evaluations: {student_evaluations?}
    
    Call your tool to calculate compliance scores for all students.
    """,
    tools=[calculate_compliance_scores]
)

# Report Saver
coa_report_saver = Agent(
    name="coa_report_saver",
    model="gemini-2.0-flash",
    description="Saves COA compliance report to Firestore",
    instruction="""
    You save the consolidated COA compliance report to Firestore.
    
    IMPORTANT: You MUST use your save_coa_report tool to save the report.
    
    Consolidated report: {consolidated_report?}
    
    Call your tool to save this report to the agent_coa_reports collection.
    """,
    tools=[save_coa_report]
)


# ===========================================
# WORKFLOW (Sequential execution)
# ===========================================

coa_agent = SequentialAgent(
    name="coa_agent",
    description="Generates COA compliance reports by tracking evaluation metrics against COA Standard D requirements",
    sub_agents=[
        coa_mapping_loader,
        coa_students_loader,
        coa_evaluations_fetcher,
        compliance_calculator,
        coa_report_saver
    ]
)


# Export the main agent
__all__ = ["coa_agent"]
