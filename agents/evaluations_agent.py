"""
Evaluations Agent - ADK Compliant
Generates student evaluations using Google ADK framework patterns.
"""

import os
import json
import random
from datetime import datetime
from typing import Dict, Any, List
from google.cloud import firestore
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Google ADK imports
from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import ToolContext

# Import Gemini for comment generation
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ===========================================
# TOOLS (Functions with ToolContext)
# ===========================================

def load_data_to_state(tool_context: ToolContext) -> dict:
    """Loads cases, students, and preceptors into state.

    Returns:
        dict: Status and counts of loaded data
    """
    try:
        # Get the directory where this file is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)  # Go up one level from agents/ to project root
        
        # Try multiple possible paths
        data_paths = [
            os.path.join(project_root, "data"),
            os.path.join(current_dir, "..", "data"),
            "data",  # Relative to current working directory
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
        
        # Load cases
        cases_path = os.path.join(data_dir, "cases.json")
        if not os.path.exists(cases_path):
            raise FileNotFoundError(f"Cases file not found: {cases_path}")
        with open(cases_path, "r") as f:
            data = json.load(f)
            cases = data.get("procedures", []) if isinstance(data, dict) else data
            tool_context.state["cases"] = cases

        # Load students
        students_path = os.path.join(data_dir, "students.json")
        if not os.path.exists(students_path):
            raise FileNotFoundError(f"Students file not found: {students_path}")
        with open(students_path, "r") as f:
            data = json.load(f)
            students = data.get("students", []) if isinstance(data, dict) else data
            tool_context.state["students"] = students

        # Load preceptors
        sites_path = os.path.join(data_dir, "sites.json")
        if not os.path.exists(sites_path):
            raise FileNotFoundError(f"Sites file not found: {sites_path}")
        with open(sites_path, "r") as f:
            data = json.load(f)
            preceptors = data.get("preceptors", []) if isinstance(data, dict) else data
            tool_context.state["preceptors"] = preceptors

        return {
            "status": "success",
            "cases_loaded": len(cases),
            "students_loaded": len(students),
            "preceptors_loaded": len(preceptors),
            "data_dir": data_dir
        }
    except Exception as e:
        error_msg = f"Error loading data: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def select_random_case(tool_context: ToolContext) -> dict:
    """Selects a random clinical case.

    Returns:
        dict: Selected case info
    """
    cases = tool_context.state.get("cases", [])
    if not cases:
        return {"status": "error", "error_message": "No cases available"}

    selected_case = random.choice(cases)
    tool_context.state["selected_case"] = selected_case

    return {
        "status": "success",
        "case_name": selected_case.get("name"),
        "case_code": selected_case.get("code")
    }


def select_random_student(tool_context: ToolContext) -> dict:
    """Selects a random student.

    Returns:
        dict: Selected student info
    """
    students = tool_context.state.get("students", [])
    if not students:
        return {"status": "error", "error_message": "No students available"}

    selected_student = random.choice(students)
    tool_context.state["selected_student"] = selected_student

    return {
        "status": "success",
        "student_name": selected_student.get("name"),
        "student_id": selected_student.get("id"),
        "class_standing": selected_student.get("class_standing")
    }


def select_matching_preceptor(tool_context: ToolContext) -> dict:
    """Selects a preceptor, preferably matching student's hospital.

    Returns:
        dict: Selected preceptor info
    """
    preceptors = tool_context.state.get("preceptors", [])
    student = tool_context.state.get("selected_student", {})

    if not preceptors:
        return {"status": "error", "error_message": "No preceptors available"}

    # Try to match by hospital
    student_hospital = student.get("hospital", "")
    matching_preceptors = []

    if student_hospital:
        hospital_name = student_hospital.split(',')[0].strip().upper()
        for preceptor in preceptors:
            for site in preceptor.get("assignedSites", []):
                site_name = site.get("hospitalName", "").upper()
                if hospital_name in site_name or site_name in hospital_name:
                    matching_preceptors.append(preceptor)
                    break

    # Select from matching or all preceptors
    selected_preceptor = random.choice(matching_preceptors if matching_preceptors else preceptors)
    tool_context.state["selected_preceptor"] = selected_preceptor
    
    # Find the primary site for this preceptor
    primary_site = None
    assigned_sites = selected_preceptor.get("assignedSites", [])
    for site in assigned_sites:
        if site.get("primarySite", False):
            primary_site = site
            break
    
    # Store primary site in state for later use
    if primary_site:
        tool_context.state["primary_site"] = primary_site

    return {
        "status": "success",
        "preceptor_name": f"{selected_preceptor.get('firstName', '')} {selected_preceptor.get('lastName', '')}",
        "preceptor_email": selected_preceptor.get("email", ""),
        "primary_site": primary_site.get("hospitalName", "") if primary_site else None
    }


def generate_evaluation_scores(tool_context: ToolContext) -> dict:
    """Generates realistic AC and PC scores based on class standing.

    Returns:
        dict: Generated scores
    """
    student = tool_context.state.get("selected_student", {})
    class_standing_str = student.get("class_standing", "1st Year")

    # Convert class standing to numeric (1-4)
    class_standing = 1
    if "2nd" in class_standing_str or "second" in class_standing_str.lower():
        class_standing = 2
    elif "3rd" in class_standing_str or "third" in class_standing_str.lower():
        class_standing = 3
    elif "4th" in class_standing_str or "fourth" in class_standing_str.lower():
        class_standing = 4

    # Generate AC scores (multiples of 10: 20, 30, 40, etc., up to 100)
    # Higher class standing = higher base scores
    ac_scores = {}
    base_ac_tens = 5 + (class_standing * 1)  # Base in tens: 6-9 (60-90)
    
    for i in range(13):
        # 90% normal range, 10% N/A
        if random.random() < 0.9:
            # Generate score as multiple of 10
            # Range: base_ac_tens to 10 (representing 60-100 for most students)
            score_tens = random.randint(base_ac_tens, 10)
            ac_scores[f"ac_{i}"] = score_tens * 10
        else:
            ac_scores[f"ac_{i}"] = -1  # N/A

    # Generate PC scores (1-5 scale, 0=N/A, -1=dangerous)
    # Make negative evaluations rare (5% total: 2% dangerous + 3% needs improvement)
    pc_scores = {}
    overall_negative_roll = random.random()
    
    # Determine if this is a negative evaluation (5% chance)
    is_negative_eval = overall_negative_roll < 0.05
    
    for i in range(11):
        roll = random.random()
        
        if is_negative_eval:
            # For negative evaluations, distribute the negative scores
            if roll < 0.4:  # 40% of scores in negative eval are dangerous
                pc_scores[f"pc_{i}"] = -1
            elif roll < 0.6:  # 20% are needs improvement
                pc_scores[f"pc_{i}"] = random.randint(1, 2)
            elif roll < 0.7:  # 10% are N/A
                pc_scores[f"pc_{i}"] = 0
            else:  # 30% are still good (3-5)
                pc_scores[f"pc_{i}"] = random.randint(3, 5)
        else:
            # For normal evaluations (95% of cases)
            if roll < 0.08:  # 8% N/A
                pc_scores[f"pc_{i}"] = 0
            elif roll < 0.15:  # 7% needs improvement (but not dangerous)
                pc_scores[f"pc_{i}"] = random.randint(2, 3)  # Lower end but not dangerous
            else:  # 85% good performance (3-5)
                pc_scores[f"pc_{i}"] = random.randint(3, 5)

    scores = {**ac_scores, **pc_scores}
    tool_context.state["evaluation_scores"] = scores

    return {
        "status": "success",
        "ac_count": len(ac_scores),
        "pc_count": len(pc_scores),
        "has_dangerous": any(v == -1 for k, v in pc_scores.items())
    }


def generate_preceptor_comment(tool_context: ToolContext) -> dict:
    """Generates a realistic preceptor comment using Gemini Pro, styled after real preceptor comments.

    Returns:
        dict: Generated comment
    """
    case = tool_context.state.get("selected_case", {})
    student = tool_context.state.get("selected_student", {})
    scores = tool_context.state.get("evaluation_scores", {})
    preceptor = tool_context.state.get("selected_preceptor", {})

    # Calculate averages
    ac_values = [scores.get(f"ac_{i}", 70) for i in range(13) if scores.get(f"ac_{i}", -1) > 0]
    pc_values = [scores.get(f"pc_{i}", 3) for i in range(11) if scores.get(f"pc_{i}", 0) > 0]

    avg_ac = sum(ac_values) / len(ac_values) if ac_values else 70
    avg_pc = sum(pc_values) / len(pc_values) if pc_values else 3
    has_dangerous = any(scores.get(f"pc_{i}", 0) == -1 for i in range(11))

    # Load comment examples for style reference
    comment_examples = []
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        examples_path = os.path.join(project_root, "data", "comments_example.json")
        if os.path.exists(examples_path):
            with open(examples_path, "r") as f:
                examples_data = json.load(f)
                comment_examples = examples_data.get("examples", [])
    except Exception as e:
        print(f"⚠️ Could not load comment examples: {e}")

    # Generate comment with Gemini Pro
    if GEMINI_AVAILABLE:
        try:
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            model = genai.GenerativeModel("gemini-2.0-flash")

            student_name = student.get("name", "the student")
            case_name = case.get("name", "this clinical case")
            class_standing = student.get("class_standing", "N/A")
            
            # Build examples text for the prompt
            examples_text = ""
            if comment_examples:
                examples_text = "\n\nHere are examples of real preceptor comments to match the style:\n"
                for i, ex in enumerate(comment_examples[:5], 1):  # Use first 5 examples
                    examples_text += f"\nExample {i} ({ex.get('case', 'N/A')}):\n{ex.get('comment', '')}\n"
            
            # Determine performance context
            if has_dangerous:
                performance_note = "The student had some concerning safety behaviors that required intervention."
            elif avg_ac < 70 or avg_pc < 2.5:
                performance_note = "The student's performance needs improvement in several areas."
            elif avg_ac >= 85 and avg_pc >= 4:
                performance_note = "The student demonstrated excellent clinical performance."
            else:
                performance_note = "The student demonstrated satisfactory performance with room for growth."
            
            prompt = f"""You are a CRNA preceptor writing a real evaluation comment after a clinical case. Write in a conversational, direct style like real preceptors do.

Student: {student_name}
Case Type: {case_name}
Class Standing: {class_standing}
Average Technical Skills: {avg_ac:.0f}/100
Average Professional Behavior: {avg_pc:.1f}/5
Performance Context: {performance_note}

{examples_text}

Write a preceptor comment that:
1. Uses the student's actual name naturally (like "Sara did well" or "[Name] demonstrated...")
2. Is conversational and direct - write like you're talking to a colleague, not formal
3. Mentions specific things that happened during the case (e.g., "Had to take over 1 intubation", "Nice spinal", "first time doing shoulders")
4. Includes specific technical details relevant to the case type
5. Mixes positive observations with constructive feedback naturally
6. Can be brief (1-2 sentences) or longer (3-5 sentences) depending on what happened
7. Avoids generic phrases like "continue developing clinical skills" or "demonstrated satisfactory performance"
8. Sounds authentic - real preceptors are direct and specific

Write the comment now (just the comment text, no quotes or formatting):"""

            response = model.generate_content(prompt)
            comment = response.text.strip()
            
            # Clean up the comment - remove any quotes or extra formatting
            if comment.startswith('"') and comment.endswith('"'):
                comment = comment[1:-1]
            if comment.startswith("'") and comment.endswith("'"):
                comment = comment[1:-1]
            
            # Remove any markdown formatting
            comment = comment.replace("**", "").replace("*", "")
            
            # Ensure it doesn't fall back to generic format
            if len(comment) < 50 or "Student performed" in comment or "demonstrated satisfactory performance" in comment.lower():
                # Retry with simpler, more direct prompt
                prompt2 = f"""Write a real preceptor comment for {student_name} after a {case_name} case.

{examples_text}

Be direct and conversational. Mention specific things that happened. Use the student's name naturally. Write like a real preceptor would - brief, specific, and authentic."""
                response2 = model.generate_content(prompt2)
                comment = response2.text.strip()
                if comment.startswith('"') and comment.endswith('"'):
                    comment = comment[1:-1]
                if comment.startswith("'") and comment.endswith("'"):
                    comment = comment[1:-1]
                
        except Exception as e:
            print(f"⚠️ Error generating comment with Gemini: {e}")
            import traceback
            traceback.print_exc()
            # Better fallback that matches the style
            student_name = student.get("name", "The student")
            case_name = case.get("name", "this case")
            if has_dangerous:
                comment = f"Had to intervene during {case_name} due to safety concerns. {student_name} handled the situation appropriately and took direction well."
            elif avg_ac < 70:
                comment = f"{student_name} showed potential during the {case_name} but needs more practice with technical skills. Keep working on it."
            elif avg_ac >= 85:
                comment = f"Nice work on the {case_name}! {student_name} handled it well and demonstrated strong clinical skills."
            else:
                comment = f"{student_name} did well during the {case_name}. Continue building on these skills."
    else:
        # Fallback when Gemini is not available
        student_name = student.get("name", "The student")
        case_name = case.get("name", "this case")
        if has_dangerous:
            comment = f"Had to intervene during {case_name} due to safety concerns. {student_name} handled the situation appropriately and took direction well."
        elif avg_ac < 70:
            comment = f"{student_name} showed potential during the {case_name} but needs more practice with technical skills. Keep working on it."
        elif avg_ac >= 85:
            comment = f"Nice work on the {case_name}! {student_name} handled it well and demonstrated strong clinical skills."
        else:
            comment = f"{student_name} did well during the {case_name}. Continue building on these skills."

    tool_context.state["preceptor_comment"] = comment

    return {
        "status": "success",
        "comment_preview": comment[:100] + "..." if len(comment) > 100 else comment,
        "performance_level": "negative" if has_dangerous or avg_ac < 70 or avg_pc < 2.5 else "positive"
    }


def save_evaluation_to_firestore(tool_context: ToolContext) -> dict:
    """Saves the complete evaluation to Firestore.

    Returns:
        dict: Save status and document ID
    """
    try:
        # Validate required state data
        case = tool_context.state.get("selected_case", {})
        student = tool_context.state.get("selected_student", {})
        preceptor = tool_context.state.get("selected_preceptor", {})
        scores = tool_context.state.get("evaluation_scores", {})
        comment = tool_context.state.get("preceptor_comment", "")
        primary_site = tool_context.state.get("primary_site", {})
        
        if not case:
            return {
                "status": "error",
                "error_message": "No case selected. Please run case_selector first."
            }
        if not student:
            return {
                "status": "error",
                "error_message": "No student selected. Please run student_selector first."
            }
        if not preceptor:
            return {
                "status": "error",
                "error_message": "No preceptor selected. Please run preceptor_selector first."
            }
        if not scores:
            return {
                "status": "error",
                "error_message": "No scores generated. Please run score_generator first."
            }
        
        # Use FIREBASE_PROJECT_ID if available, otherwise auto-detect
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            db = firestore.Client(project=project_id)
        else:
            db = firestore.Client()

        # Build site information from primary site
        site_info = {}
        if primary_site:
            site_info = {
                "site": primary_site.get("hospitalName", ""),
                "site_id": primary_site.get("hospitalId", ""),
                "site_city": primary_site.get("city", ""),
                "site_state": primary_site.get("state", "")
            }
        
        evaluation = {
            "case_type": case.get("name"),
            "case_code": case.get("code"),
            "preceptee_user_name": student.get("name"),
            "preceptee_user_id": student.get("id"),
            "class_standing": student.get("class_standing"),
            "preceptor_name": f"{preceptor.get('firstName', '')} {preceptor.get('lastName', '')}",
            "preceptor_email": preceptor.get("email", ""),
            "comments": comment,
            **scores,
            **site_info,  # Include site information
            "completion_date": SERVER_TIMESTAMP,
            "created_at": SERVER_TIMESTAMP,
            "agent": "evaluations_agent",
            "adk_version": "1.0"
        }

        doc_ref = db.collection("agent_evaluations").add(evaluation)
        doc_id = doc_ref[1].id

        tool_context.state["evaluation_doc_id"] = doc_id

        return {
            "status": "success",
            "doc_id": doc_id,
            "case_type": case.get("name"),
            "student_name": student.get("name")
        }
    except Exception as e:
        error_msg = f"Error saving evaluation: {str(e)}"
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

# Data Loader
data_loader = Agent(
    name="data_loader",
    model="gemini-2.0-flash",
    description="Loads cases, students, and preceptors from JSON files",
    instruction="""
    You are responsible for loading the data needed for evaluations.
    
    IMPORTANT: You MUST use your load_data_to_state tool to load:
    1. Cases from data/cases.json
    2. Students from data/students.json  
    3. Preceptors from data/sites.json
    
    Load all three data files into the session state. Do not proceed until all data is loaded.
    """,
    tools=[load_data_to_state]
)

# Case Selector
case_selector = Agent(
    name="case_selector",
    model="gemini-2.0-flash",
    description="Selects a random clinical case",
    instruction="""
    You select a clinical case for evaluation.

    Available cases: {cases?}

    Use your tool to select a random case.
    """,
    tools=[select_random_case]
)

# Student Selector
student_selector = Agent(
    name="student_selector",
    model="gemini-2.0-flash",
    description="Selects a random student",
    instruction="""
    You select a student for evaluation.

    Available students: {students?}

    Use your tool to select a random student.
    """,
    tools=[select_random_student]
)

# Preceptor Selector
preceptor_selector = Agent(
    name="preceptor_selector",
    model="gemini-2.0-flash",
    description="Selects a preceptor matching the student's hospital",
    instruction="""
    You select a preceptor for evaluation.

    Selected student: {selected_student?}
    Available preceptors: {preceptors?}

    Use your tool to find a matching preceptor.
    """,
    tools=[select_matching_preceptor]
)

# Score Generator
score_generator = Agent(
    name="score_generator",
    model="gemini-2.0-flash",
    description="Generates realistic evaluation scores",
    instruction="""
    You generate evaluation scores for CRNA students.

    Student: {selected_student?}
    Case: {selected_case?}

    Generate AC (Anesthesia Competency) and PC (Professional Competency) scores.
    Higher class standings should have higher average scores.
    """,
    tools=[generate_evaluation_scores]
)

# Comment Generator
comment_generator = Agent(
    name="comment_generator",
    model="gemini-2.0-flash",
    description="Generates preceptor comments",
    instruction="""
    You generate realistic preceptor evaluation comments.

    Case: {selected_case?}
    Student: {selected_student?}
    Scores: {evaluation_scores?}

    Write a professional, constructive comment about the student's performance.
    """,
    tools=[generate_preceptor_comment]
)

# Evaluation Saver
evaluation_saver = Agent(
    name="evaluation_saver",
    model="gemini-2.0-flash",
    description="Saves evaluations to Firestore",
    instruction="""
    You save completed evaluations to Firestore.

    Case: {selected_case?}
    Student: {selected_student?}
    Preceptor: {selected_preceptor?}
    Scores: {evaluation_scores?}
    Comment: {preceptor_comment?}

    Use your tool to save this evaluation to the agent_evaluations collection.
    """,
    tools=[save_evaluation_to_firestore]
)


# ===========================================
# WORKFLOW (Sequential execution)
# ===========================================

evaluation_agent = SequentialAgent(
    name="evaluation_agent",
    description="Creates complete student evaluations with case, student, preceptor, scores, comments, and saves to Firestore",
    sub_agents=[
        data_loader,
        case_selector,
        student_selector,
        preceptor_selector,
        score_generator,
        comment_generator,
        evaluation_saver
    ]
)


# Export the main agent
__all__ = ["evaluation_agent"]
