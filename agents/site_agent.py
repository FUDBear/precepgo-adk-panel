"""
Site Agent - ADK Compliant
Analyzes evaluation data to generate site reports listing clinical sites, case types,
and preceptor information with student counts and case types they've precepted.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import defaultdict
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Google ADK imports
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import ToolContext

# Import Gemini for report generation
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ===========================================
# TOOLS (Functions with ToolContext)
# ===========================================

def load_students_data(tool_context: ToolContext) -> dict:
    """Loads students data to get site/hospital information.

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
            students = data.get("students", []) if isinstance(data, dict) else data
            tool_context.state["students"] = students
        
        return {
            "status": "success",
            "students_loaded": len(students),
            "data_dir": data_dir
        }
    except Exception as e:
        error_msg = f"Error loading students data: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def fetch_all_evaluations(tool_context: ToolContext) -> dict:
    """Fetches all evaluations from agent_evaluations collection.

    Returns:
        dict: Status and count of fetched evaluations
    """
    try:
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            db = firestore.Client(project=project_id)
        else:
            db = firestore.Client()
        
        evaluations_ref = db.collection("agent_evaluations")
        evaluations = []
        
        for doc in evaluations_ref.stream():
            eval_data = doc.to_dict()
            eval_data['doc_id'] = doc.id
            evaluations.append(eval_data)
        
        tool_context.state["evaluations"] = evaluations
        
        print(f"📊 Fetched {len(evaluations)} evaluations from agent_evaluations")
        
        return {
            "status": "success",
            "evaluations_count": len(evaluations)
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


def analyze_evaluations(tool_context: ToolContext) -> dict:
    """Analyzes evaluations to extract site and preceptor information.

    Returns:
        dict: Analysis results with sites and preceptors data
    """
    try:
        evaluations = tool_context.state.get("evaluations", [])
        students = tool_context.state.get("students", [])
        
        if not evaluations:
            return {
                "status": "error",
                "error_message": "No evaluations found. Run fetch_all_evaluations first."
            }
        
        # Build student site mapping
        student_site_map = {}
        for student in students:
            student_id = student.get('id')
            student_name = student.get('name')
            hospital = student.get('hospital') or 'Unknown Hospital'
            if student_id:
                student_site_map[student_id] = hospital
            if student_name:
                student_site_map[student_name] = hospital
        
        # Site analysis: {site_name: {case_types: set, total_evaluations: int}}
        sites_data = defaultdict(lambda: {'case_types': set(), 'total_evaluations': 0, 'preceptors': set()})
        
        # Preceptor analysis: {preceptor_name: {students: set, case_types: set, total_evaluations: int}}
        preceptors_data = defaultdict(lambda: {'students': set(), 'case_types': set(), 'total_evaluations': 0})
        
        # Process each evaluation
        for eval_data in evaluations:
            # Get site/hospital from student
            preceptee_id = eval_data.get('preceptee_user_id') or eval_data.get('preceptee_user_name')
            site_name = student_site_map.get(preceptee_id, 'Unknown Site')
            
            # Get preceptor info
            preceptor_name = eval_data.get('preceptor_name', 'Unknown Preceptor')
            preceptor_id = eval_data.get('preceptor_id', '')
            
            # Get case type
            case_type = eval_data.get('case_type', 'Unknown Case')
            
            # Update site data
            sites_data[site_name]['case_types'].add(case_type)
            sites_data[site_name]['total_evaluations'] += 1
            sites_data[site_name]['preceptors'].add(preceptor_name)
            
            # Update preceptor data
            preceptor_key = f"{preceptor_name} ({preceptor_id})" if preceptor_id else preceptor_name
            preceptors_data[preceptor_key]['students'].add(preceptee_id if preceptee_id else 'Unknown')
            preceptors_data[preceptor_key]['case_types'].add(case_type)
            preceptors_data[preceptor_key]['total_evaluations'] += 1
        
        # Convert sets to lists for JSON serialization
        sites_summary = []
        for site_name, data in sites_data.items():
            sites_summary.append({
                'site_name': site_name,
                'case_types': sorted(list(data['case_types'])),
                'total_evaluations': data['total_evaluations'],
                'unique_preceptors': len(data['preceptors']),
                'preceptor_names': sorted(list(data['preceptors']))
            })
        
        preceptors_summary = []
        for preceptor_key, data in preceptors_data.items():
            # Extract name from key (handle format "Name (ID)")
            preceptor_name = preceptor_key.split(' (')[0]
            preceptors_summary.append({
                'preceptor_name': preceptor_name,
                'student_count': len(data['students']),
                'case_types': sorted(list(data['case_types'])),
                'total_evaluations': data['total_evaluations']
            })
        
        # Sort by total evaluations (descending)
        sites_summary.sort(key=lambda x: x['total_evaluations'], reverse=True)
        preceptors_summary.sort(key=lambda x: x['total_evaluations'], reverse=True)
        
        analysis_data = {
            'sites': sites_summary,
            'preceptors': preceptors_summary,
            'total_evaluations': len(evaluations),
            'total_sites': len(sites_summary),
            'total_preceptors': len(preceptors_summary),
            'analyzed_at': datetime.now().isoformat()
        }
        
        tool_context.state["analysis_data"] = analysis_data
        
        print(f"✅ Analysis complete:")
        print(f"   - Sites found: {analysis_data['total_sites']}")
        print(f"   - Preceptors found: {analysis_data['total_preceptors']}")
        print(f"   - Total evaluations: {analysis_data['total_evaluations']}")
        
        return {
            "status": "success",
            "total_sites": analysis_data['total_sites'],
            "total_preceptors": analysis_data['total_preceptors'],
            "total_evaluations": analysis_data['total_evaluations']
        }
    except Exception as e:
        error_msg = f"Error analyzing evaluations: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def generate_ai_report(tool_context: ToolContext) -> dict:
    """Generates an AI-powered site report using Gemini.

    Returns:
        dict: Status and report text
    """
    try:
        analysis_data = tool_context.state.get("analysis_data")
        
        if not analysis_data:
            return {
                "status": "error",
                "error_message": "No analysis data found. Run analyze_evaluations first."
            }
        
        if not GEMINI_AVAILABLE:
            # Fallback to basic report
            report_text = _generate_basic_report(analysis_data)
            tool_context.state["report_text"] = report_text
            return {
                "status": "success",
                "report_type": "basic",
                "report_length": len(report_text)
            }
        
        try:
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            model = genai.GenerativeModel("gemini-2.0-flash")
            
            sites_text = "\n".join([
                f"- {site['site_name']}: {site['total_evaluations']} evaluations, "
                f"{len(site['case_types'])} case types, {site['unique_preceptors']} preceptors"
                for site in analysis_data['sites'][:20]  # Top 20 sites
            ])
            
            preceptors_text = "\n".join([
                f"- {preceptor['preceptor_name']}: {preceptor['total_evaluations']} evaluations, "
                f"{preceptor['student_count']} students, {len(preceptor['case_types'])} case types"
                for preceptor in analysis_data['preceptors'][:20]  # Top 20 preceptors
            ])
            
            prompt = f"""Generate a comprehensive site report for a CRNA program based on evaluation data.

**Summary Statistics:**
- Total Evaluations: {analysis_data['total_evaluations']}
- Total Clinical Sites: {analysis_data['total_sites']}
- Total Preceptors: {analysis_data['total_preceptors']}

**Clinical Sites Overview:**
{sites_text}

**Preceptor Overview:**
{preceptors_text}

Generate a professional site report that includes:
1. Executive Summary: Overview of the program's clinical sites and preceptor network
2. Clinical Sites Analysis: Detailed breakdown of each site including:
   - Case types performed at each site
   - Number of evaluations
   - Preceptor representation
   - Unique characteristics or specialties
3. Preceptor Analysis: Detailed breakdown of preceptors including:
   - Number of students precepted
   - Types of cases they've supervised
   - Experience level based on evaluation volume
   - Key strengths and specializations
4. Insights and Recommendations: AI-generated insights about the clinical training network,
   distribution of cases, preceptor utilization, and recommendations for program improvement

Write in a professional, analytical tone suitable for program administrators and accreditation review.
Include specific numbers and data points throughout the report."""

            response = model.generate_content(prompt)
            
            if response and response.text:
                report_text = response.text.strip()
                tool_context.state["report_text"] = report_text
                return {
                    "status": "success",
                    "report_type": "ai_generated",
                    "report_length": len(report_text)
                }
            else:
                # Fallback to basic report
                report_text = _generate_basic_report(analysis_data)
                tool_context.state["report_text"] = report_text
                return {
                    "status": "success",
                    "report_type": "basic",
                    "report_length": len(report_text)
                }
        except Exception as e:
            print(f"⚠️ Failed to generate AI report: {e}")
            # Fallback to basic report
            report_text = _generate_basic_report(analysis_data)
            tool_context.state["report_text"] = report_text
            return {
                "status": "success",
                "report_type": "basic_fallback",
                "report_length": len(report_text)
            }
    except Exception as e:
        error_msg = f"Error generating report: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def _generate_basic_report(analysis_data: Dict[str, Any]) -> str:
    """Generate a basic report without AI (fallback).

    Args:
        analysis_data: Analyzed data from evaluations

    Returns:
        Basic report text
    """
    report_lines = [
        "# Site Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Executive Summary",
        f"- Total Evaluations: {analysis_data['total_evaluations']}",
        f"- Total Clinical Sites: {analysis_data['total_sites']}",
        f"- Total Preceptors: {analysis_data['total_preceptors']}",
        "",
        "## Clinical Sites",
    ]
    
    for site in analysis_data['sites']:
        report_lines.append(f"\n### {site['site_name']}")
        report_lines.append(f"- Total Evaluations: {site['total_evaluations']}")
        report_lines.append(f"- Unique Preceptors: {site['unique_preceptors']}")
        report_lines.append(f"- Case Types ({len(site['case_types'])}):")
        for case_type in site['case_types'][:10]:  # Limit to 10 case types
            report_lines.append(f"  - {case_type}")
        if len(site['case_types']) > 10:
            report_lines.append(f"  ... and {len(site['case_types']) - 10} more")
    
    report_lines.append("\n## Preceptors")
    
    for preceptor in analysis_data['preceptors']:
        report_lines.append(f"\n### {preceptor['preceptor_name']}")
        report_lines.append(f"- Students Precepted: {preceptor['student_count']}")
        report_lines.append(f"- Total Evaluations: {preceptor['total_evaluations']}")
        report_lines.append(f"- Case Types ({len(preceptor['case_types'])}):")
        for case_type in preceptor['case_types'][:10]:  # Limit to 10 case types
            report_lines.append(f"  - {case_type}")
        if len(preceptor['case_types']) > 10:
            report_lines.append(f"  ... and {len(preceptor['case_types']) - 10} more")
    
    return "\n".join(report_lines)


def save_site_report(tool_context: ToolContext) -> dict:
    """Saves the generated site report to Firestore.

    Returns:
        dict: Status and document ID
    """
    try:
        analysis_data = tool_context.state.get("analysis_data")
        report_text = tool_context.state.get("report_text")
        
        if not analysis_data:
            return {
                "status": "error",
                "error_message": "No analysis data found. Run analyze_evaluations first."
            }
        
        if not report_text:
            return {
                "status": "error",
                "error_message": "No report text found. Run generate_ai_report first."
            }
        
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            db = firestore.Client(project=project_id)
        else:
            db = firestore.Client()
        
        report_data = {
            'report_text': report_text,
            'analysis_data': analysis_data,
            'generated_at': SERVER_TIMESTAMP,
            'created_at': SERVER_TIMESTAMP,
            'total_evaluations_analyzed': analysis_data['total_evaluations'],
            'report_version': '1.0'
        }
        
        report_ref = db.collection("agent_sites").add(report_data)[1]
        report_id = report_ref.id
        
        tool_context.state["report_doc_id"] = report_id
        
        print(f"✅ Report saved to Firestore: agent_sites/{report_id}")
        
        return {
            "status": "success",
            "doc_id": report_id,
            "total_sites": analysis_data['total_sites'],
            "total_preceptors": analysis_data['total_preceptors'],
            "total_evaluations": analysis_data['total_evaluations']
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

# Students Data Loader
students_loader = Agent(
    name="students_loader",
    model="gemini-2.0-flash",
    description="Loads students data for site mapping",
    instruction="""
    You load students data needed for site report generation.
    
    IMPORTANT: You MUST use your load_students_data tool to load students from data/students.json.
    
    Load the students data into the session state. Do not proceed until the data is loaded.
    """,
    tools=[load_students_data]
)

# Evaluations Fetcher
evaluations_fetcher = Agent(
    name="evaluations_fetcher",
    model="gemini-2.0-flash",
    description="Fetches all evaluations from Firestore",
    instruction="""
    You fetch all evaluations from the agent_evaluations collection.
    
    IMPORTANT: You MUST use your fetch_all_evaluations tool to fetch evaluations from Firestore.
    
    Fetch all evaluation documents and store them in the session state. Do not proceed until evaluations are fetched.
    """,
    tools=[fetch_all_evaluations]
)

# Evaluations Analyzer
evaluations_analyzer = Agent(
    name="evaluations_analyzer",
    model="gemini-2.0-flash",
    description="Analyzes evaluations to extract site and preceptor information",
    instruction="""
    You analyze evaluation data to extract site and preceptor information.
    
    IMPORTANT: You MUST use your analyze_evaluations tool to analyze the fetched evaluations.
    
    Available data:
    - Students: {students?}
    - Evaluations: {evaluations?}
    
    Call your tool to analyze the evaluations and extract site/preceptor data.
    """,
    tools=[analyze_evaluations]
)

# Report Generator
report_generator = Agent(
    name="report_generator",
    model="gemini-2.0-flash",
    description="Generates AI-powered site report",
    instruction="""
    You generate an AI-powered site report using Gemini.
    
    IMPORTANT: You MUST use your generate_ai_report tool to generate the report.
    
    Analysis data: {analysis_data?}
    
    Call your tool to generate a comprehensive site report based on the analysis data.
    """,
    tools=[generate_ai_report]
)

# Report Saver
report_saver = Agent(
    name="report_saver",
    model="gemini-2.0-flash",
    description="Saves site report to Firestore",
    instruction="""
    You save the generated site report to Firestore.
    
    IMPORTANT: You MUST use your save_site_report tool to save the report.
    
    Analysis data: {analysis_data?}
    Report text: {report_text?}
    
    Call your tool to save this report to the agent_sites collection.
    """,
    tools=[save_site_report]
)


# ===========================================
# WORKFLOW (Sequential execution)
# ===========================================

site_agent = SequentialAgent(
    name="site_agent",
    description="Generates comprehensive site reports analyzing clinical sites, preceptors, and case types from evaluation data",
    sub_agents=[
        students_loader,
        evaluations_fetcher,
        evaluations_analyzer,
        report_generator,
        report_saver
    ]
)


# Export the main agent
__all__ = ["site_agent"]
