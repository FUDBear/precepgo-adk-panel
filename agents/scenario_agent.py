"""
Scenario Agent - ADK Compliant
Generates clinical scenarios with patient matching and decision options.
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

# Import Gemini for scenario generation
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ===========================================
# TOOLS (Functions with ToolContext)
# ===========================================

def load_scenario_data_to_state(tool_context: ToolContext) -> dict:
    """Loads cases, patients, and students for scenario generation.

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
            tool_context.state["scenario_cases"] = cases

        # Load patient templates
        patients_path = os.path.join(data_dir, "patient_templates.json")
        if not os.path.exists(patients_path):
            raise FileNotFoundError(f"Patient templates file not found: {patients_path}")
        with open(patients_path, "r") as f:
            data = json.load(f)
            patients = data if isinstance(data, list) else data.get("patients", [])
            tool_context.state["patient_templates"] = patients

        # Load students
        students_path = os.path.join(data_dir, "students.json")
        if not os.path.exists(students_path):
            raise FileNotFoundError(f"Students file not found: {students_path}")
        with open(students_path, "r") as f:
            data = json.load(f)
            students = data.get("students", []) if isinstance(data, dict) else data
            tool_context.state["scenario_students"] = students

        return {
            "status": "success",
            "cases_loaded": len(cases),
            "patients_loaded": len(patients),
            "students_loaded": len(students),
            "data_dir": data_dir
        }
    except Exception as e:
        error_msg = f"Error loading scenario data: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def select_scenario_case(tool_context: ToolContext) -> dict:
    """Selects a random case for scenario generation.

    Returns:
        dict: Selected case info
    """
    cases = tool_context.state.get("scenario_cases", [])
    if not cases:
        return {"status": "error", "error_message": "No cases available"}

    selected_case = random.choice(cases)
    tool_context.state["scenario_case"] = selected_case

    return {
        "status": "success",
        "case_name": selected_case.get("name"),
        "case_code": selected_case.get("code"),
        "difficulty": selected_case.get("difficulty", "intermediate")
    }


def match_patient_to_case(tool_context: ToolContext) -> dict:
    """Matches a patient template to the selected case based on age and ASA.

    Returns:
        dict: Matched patient info
    """
    case = tool_context.state.get("scenario_case", {})
    patients = tool_context.state.get("patient_templates", [])

    if not patients:
        return {"status": "error", "error_message": "No patient templates available"}

    # Get case parameters
    case_min_age = case.get("min_age", 18)
    case_max_age = case.get("max_age", 100)
    case_asa = case.get("asa_classification", [1, 2, 3, 4])

    # Filter patients by age and ASA
    matching_patients = []
    for patient in patients:
        age = patient.get("age", 50)
        asa = patient.get("asa_classification", 2)

        if case_min_age <= age <= case_max_age and asa in case_asa:
            matching_patients.append(patient)

    # Select from matching or all patients
    selected_patient = random.choice(matching_patients if matching_patients else patients)
    tool_context.state["scenario_patient"] = selected_patient

    return {
        "status": "success",
        "patient_name": selected_patient.get("full_name"),
        "patient_age": selected_patient.get("age"),
        "asa": selected_patient.get("asa_classification"),
        "matched": len(matching_patients) > 0
    }


def select_target_student(tool_context: ToolContext) -> dict:
    """Selects a student to receive this scenario.
            
        Returns:
        dict: Selected student info
    """
    students = tool_context.state.get("scenario_students", [])
    if not students:
        return {"status": "error", "error_message": "No students available"}

    selected_student = random.choice(students)
    tool_context.state["scenario_student"] = selected_student

    return {
        "status": "success",
        "student_name": selected_student.get("name"),
        "student_id": selected_student.get("id"),
        "class_standing": selected_student.get("class_standing")
    }


def generate_scenario_with_gemini(tool_context: ToolContext) -> dict:
    """Generates a clinical scenario with decision options using Gemini Pro.
            
        Returns:
        dict: Generated scenario content
    """
    case = tool_context.state.get("scenario_case", {})
    patient = tool_context.state.get("scenario_patient", {})
    student = tool_context.state.get("scenario_student", {})

    if not GEMINI_AVAILABLE:
        return {
            "status": "error",
            "error_message": "Gemini not available"
        }

    try:
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel("gemini-2.0-flash")

        # Build comprehensive patient summary (like original)
        patient_weight = patient.get('weight', {})
        patient_summary = f"""Patient: {patient.get('full_name', 'Patient')}
Age: {patient.get('age', 'Unknown')} years
Weight: {patient_weight.get('kg', 'Unknown') if isinstance(patient_weight, dict) else 'Unknown'} kg ({patient_weight.get('lbs', 'Unknown') if isinstance(patient_weight, dict) else 'Unknown'} lbs)
ASA Classification: {patient.get('asa_classification', 'Unknown')}
Comorbidities: {', '.join(patient.get('comorbidities', [])) if patient.get('comorbidities') else 'None'}
Health Traits: {', '.join(patient.get('health_traits', [])) if patient.get('health_traits') else 'Standard'}
Medical History: {patient.get('medical_history', 'No significant medical history')}
Categories: {', '.join(patient.get('categories', [])) if patient.get('categories') else 'General'}"""

        # Build case summary
        case_summary = f"""Case: {case.get('name', 'Surgical Procedure')}
Code: {case.get('code', 'N/A')}
Description: {case.get('description', '')}
Keywords: {', '.join(case.get('keywords', [])) if case.get('keywords') else 'N/A'}
Difficulty: {case.get('difficulty', 'intermediate')}"""

        # Build student context
        student_context = ""
        if student:
            student_name = student.get('name', 'Student')
            class_standing = student.get('class_standing', '1st Year')
            student_context = f"""
**STUDENT CONTEXT:**
Student: {student_name} ({class_standing})
Student Level: {class_standing}

When generating this scenario, consider:
- The scenario should be challenging but appropriate for {class_standing}
- Focus on areas relevant to this student's level of training
- Provide clear learning points that address their educational needs
- Make the scenario realistic and clinically relevant"""

        prompt = f"""You are an expert CRNA clinical scenario designer. Create a realistic clinical scenario based on the following information:

**PATIENT INFORMATION:**
{patient_summary}

**SURGICAL CASE:**
{case_summary}
{student_context}

**YOUR TASK:**
Create a clinical scenario with TWO decision options for the CRNA student. The scenario should:
1. Present a realistic clinical situation involving this patient and case
2. Include detailed patient presentation, vital signs, and clinical context (2-3 paragraphs)
3. Present a critical decision point where the student must choose between two approaches
4. Both options should be plausible and defensible
5. Make it educational and challenging, appropriate for {student.get('class_standing', '1st Year') if student else 'CRNA students'}
6. Base all information on evidence-based anesthesia practice

**REQUIREMENTS:**
1. **scenario:** Write 2-3 detailed paragraphs describing the patient presentation, vital signs, current clinical situation, and the context leading to the decision point. Be specific and realistic with actual numbers (BP, HR, SpO2, etc.).

2. **decision_point:** State the specific critical decision the student must make (e.g., "Should you proceed with induction?", "How should you manage this airway?", "What monitoring is essential?", "How should you adjust the anesthetic plan?")

3. **option_a:** Provide a complete, detailed description of the first approach/decision (2-3 sentences explaining what the student would do, why they would do it, and the rationale). This must be a full description, NOT just a label.

4. **option_b:** Provide a complete, detailed description of the second approach/decision (2-3 sentences explaining what the student would do, why they would do it, and the rationale). This must be a full description, NOT just a label.

5. **best_answer:** State which option (A or B) is better. Use format "Option A" or "Option B".

6. **rationale:** Provide a comprehensive explanation (3-5 sentences) explaining why the best answer is correct, considering:
   - Patient-specific factors (age, comorbidities, ASA status)
   - Risks and benefits of each approach
   - Evidence-based practice considerations
   - Clinical guidelines and best practices
   - Why the other option is less optimal

7. **learning_points:** Provide 3-4 specific, actionable learning points as an array of strings that address key concepts from this scenario

**CRITICAL:** 
- Each option (option_a and option_b) must be a complete, detailed description - NOT just a label or single sentence
- Write full sentences explaining the approach, rationale, and what the student would actually do
- The scenario should be realistic and clinically relevant
- Include specific vital signs, medications, and clinical details

**OUTPUT FORMAT:** You MUST return ONLY valid JSON. No markdown, no code blocks, no explanations - just the raw JSON object.

Return ONLY this JSON structure (no other text):
{{
  "scenario": "detailed scenario text here (2-3 paragraphs with vital signs, patient presentation, clinical context)...",
  "decision_point": "the specific critical decision question",
  "option_a": "complete detailed description of option A approach (2-3 sentences explaining what the student would do and why)",
  "option_b": "complete detailed description of option B approach (2-3 sentences explaining what the student would do and why)",
  "best_answer": "Option A" or "Option B",
  "rationale": "comprehensive explanation (3-5 sentences) of why the best answer is correct, considering patient factors, risks, benefits, and evidence-based practice",
  "learning_points": ["point 1", "point 2", "point 3", "point 4"]
}}"""

        # Use structured output for better JSON parsing
        generation_config = genai.types.GenerationConfig(
            temperature=0.7,
            top_p=0.9,
            top_k=40,
            max_output_tokens=8192,
            response_mime_type="application/json"
        )

        # Safety settings
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]

        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
        )
        scenario_text = response.text.strip()
        
        # Debug: Print raw response
        print(f"🔍 Raw Gemini response (first 500 chars):\n{scenario_text[:500]}\n")

        # Try to parse as JSON (should be clean JSON since we used response_mime_type="application/json")
        scenario_json = None
        try:
            import re
            # Since we're using structured output, try parsing directly first
            try:
                scenario_json = json.loads(scenario_text)
                print("✅ Parsed JSON directly (structured output)")
            except json.JSONDecodeError:
                # Fallback: try to extract JSON from markdown code blocks
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', scenario_text, re.DOTALL)
                if json_match:
                    try:
                        scenario_json = json.loads(json_match.group(1))
                        print("✅ Parsed JSON from markdown code block")
                    except json.JSONDecodeError:
                        print("⚠️ JSON in markdown block failed to parse, trying other methods...")
                        json_match = None
                
                if not scenario_json:
                    # Try to find the largest JSON object in the text by counting braces
                    brace_count = 0
                    start_idx = -1
                    end_idx = -1
                    for i, char in enumerate(scenario_text):
                        if char == '{':
                            if brace_count == 0:
                                start_idx = i
                            brace_count += 1
                        elif char == '}':
                            brace_count -= 1
                            if brace_count == 0 and start_idx != -1:
                                end_idx = i + 1
                        break
            
                    if start_idx != -1 and end_idx != -1:
                        json_str = scenario_text[start_idx:end_idx]
                        try:
                            scenario_json = json.loads(json_str)
                            print("✅ Parsed JSON by counting braces")
                        except json.JSONDecodeError:
                            print("⚠️ Brace-counted JSON failed to parse")
                    
        except Exception as e:
            print(f"⚠️ JSON parsing exception: {e}")
            scenario_json = None
        
        if not scenario_json:
            print(f"⚠️ JSON parsing failed, attempting to extract fields manually from text...")
            print(f"⚠️ Full response length: {len(scenario_text)}")
            
            # Try to extract fields manually using more robust regex patterns
            scenario_json = {}
            
            # Extract scenario text - handle multi-line strings
            scenario_match = re.search(r'"scenario"\s*:\s*"((?:[^"\\]|\\.)*)"', scenario_text, re.DOTALL)
            if not scenario_match:
                # Try without quotes
                scenario_match = re.search(r'scenario["\']?\s*:\s*([^\n,}]+)', scenario_text, re.IGNORECASE | re.DOTALL)
            if scenario_match:
                scenario_json["scenario"] = scenario_match.group(1).strip().strip('"').strip("'")
            
            # Extract option_a - handle multi-line strings
            option_a_match = re.search(r'"option_a"\s*:\s*"((?:[^"\\]|\\.)*)"', scenario_text, re.DOTALL)
            if not option_a_match:
                option_a_match = re.search(r'"option_a"\s*:\s*"([^"]*(?:"[^"]*")*[^"]*)"', scenario_text, re.DOTALL)
            if not option_a_match:
                option_a_match = re.search(r'option\s*a["\']?\s*:\s*["\']?([^"\']+)', scenario_text, re.IGNORECASE | re.DOTALL)
            if option_a_match:
                scenario_json["option_a"] = option_a_match.group(1).strip().strip('"').strip("'")
            
            # Extract option_b - handle multi-line strings
            option_b_match = re.search(r'"option_b"\s*:\s*"((?:[^"\\]|\\.)*)"', scenario_text, re.DOTALL)
            if not option_b_match:
                option_b_match = re.search(r'"option_b"\s*:\s*"([^"]*(?:"[^"]*")*[^"]*)"', scenario_text, re.DOTALL)
            if not option_b_match:
                option_b_match = re.search(r'option\s*b["\']?\s*:\s*["\']?([^"\']+)', scenario_text, re.IGNORECASE | re.DOTALL)
            if option_b_match:
                scenario_json["option_b"] = option_b_match.group(1).strip().strip('"').strip("'")
            
            # Extract best_answer
            best_match = re.search(r'"best_answer"\s*:\s*"([^"]+)"', scenario_text, re.IGNORECASE)
            if not best_match:
                best_match = re.search(r'best\s*answer["\']?\s*:\s*["\']?(option\s*[ab])', scenario_text, re.IGNORECASE)
            if best_match:
                scenario_json["best_answer"] = best_match.group(1).strip().strip('"').strip("'")
            
            # Extract rationale - handle multi-line strings
            rationale_match = re.search(r'"rationale"\s*:\s*"((?:[^"\\]|\\.)*)"', scenario_text, re.DOTALL)
            if not rationale_match:
                rationale_match = re.search(r'"rationale"\s*:\s*"([^"]*(?:"[^"]*")*[^"]*)"', scenario_text, re.DOTALL)
            if not rationale_match:
                rationale_match = re.search(r'rationale["\']?\s*:\s*["\']?([^"\']+)', scenario_text, re.IGNORECASE | re.DOTALL)
            if rationale_match:
                scenario_json["rationale"] = rationale_match.group(1).strip().strip('"').strip("'")
            
            # Extract decision_point
            decision_match = re.search(r'"decision_point"\s*:\s*"((?:[^"\\]|\\.)*)"', scenario_text, re.DOTALL)
            if not decision_match:
                decision_match = re.search(r'decision\s*point["\']?\s*:\s*["\']?([^"\']+)', scenario_text, re.IGNORECASE | re.DOTALL)
            if decision_match:
                scenario_json["decision_point"] = decision_match.group(1).strip().strip('"').strip("'")
            
            # Extract learning_points (array)
            learning_match = re.search(r'"learning_points"\s*:\s*\[(.*?)\]', scenario_text, re.DOTALL)
            if learning_match:
                points_text = learning_match.group(1)
                points = re.findall(r'"([^"]+)"', points_text)
                if points:
                    scenario_json["learning_points"] = points
            
            # If we still don't have the scenario text, use the raw text
            if not scenario_json.get("scenario"):
                scenario_json["scenario"] = scenario_text
                
            print(f"📋 Extracted fields: {list(scenario_json.keys())}")
            print(f"📋 Option A length: {len(scenario_json.get('option_a', ''))}")
            print(f"📋 Option B length: {len(scenario_json.get('option_b', ''))}")
            print(f"📋 Rationale length: {len(scenario_json.get('rationale', ''))}")

        # Debug: Print what was generated BEFORE validation
        print(f"\n🔍 BEFORE VALIDATION - Generated scenario fields:")
        print(f"   - Has scenario: {bool(scenario_json.get('scenario'))}")
        print(f"   - Has option_a: {bool(scenario_json.get('option_a'))}")
        print(f"   - Has option_b: {bool(scenario_json.get('option_b'))}")
        print(f"   - Has rationale: {bool(scenario_json.get('rationale'))}")
        print(f"   - Has best_answer: {bool(scenario_json.get('best_answer'))}")
        print(f"   - Option A value: {scenario_json.get('option_a', '')[:100] if scenario_json.get('option_a') else 'MISSING'}")
        print(f"   - Option B value: {scenario_json.get('option_b', '')[:100] if scenario_json.get('option_b') else 'MISSING'}")
        print(f"   - Rationale value: {scenario_json.get('rationale', '')[:100] if scenario_json.get('rationale') else 'MISSING'}\n")

        # Validate that we have complete data
        if not scenario_json.get("scenario") or len(scenario_json.get("scenario", "")) < 50:
            print("⚠️ Scenario text is too short or missing")
            scenario_json["scenario"] = scenario_text[:500] if len(scenario_text) > 50 else "Scenario generation incomplete. Please try again."
        
        if not scenario_json.get("option_a") or len(scenario_json.get("option_a", "")) < 20:
            print("⚠️ Option A is missing or too short")
            scenario_json["option_a"] = "Detailed option A description not generated. Please regenerate the scenario."
        
        if not scenario_json.get("option_b") or len(scenario_json.get("option_b", "")) < 20:
            print("⚠️ Option B is missing or too short")
            scenario_json["option_b"] = "Detailed option B description not generated. Please regenerate the scenario."
        
        if not scenario_json.get("best_answer"):
            scenario_json["best_answer"] = "Option A"
        
        if not scenario_json.get("rationale"):
            scenario_json["rationale"] = "Clinical reasoning based on patient presentation and evidence-based practice."
        
        if not scenario_json.get("decision_point"):
            scenario_json["decision_point"] = "A critical clinical decision must be made."
        
        if not scenario_json.get("learning_points") or not isinstance(scenario_json.get("learning_points"), list):
            scenario_json["learning_points"] = ["Clinical reasoning", "Patient safety", "Evidence-based practice"]
        
        # Debug: Print what was generated AFTER validation
        print(f"✅ AFTER VALIDATION - Final scenario:")
        print(f"   - Scenario length: {len(scenario_json.get('scenario', ''))}")
        print(f"   - Option A length: {len(scenario_json.get('option_a', ''))}")
        print(f"   - Option B length: {len(scenario_json.get('option_b', ''))}")
        print(f"   - Rationale length: {len(scenario_json.get('rationale', ''))}")
        print(f"   - Best answer: {scenario_json.get('best_answer', '')}")
        print(f"   - Full scenario_json keys: {list(scenario_json.keys())}\n")
        
        tool_context.state["generated_scenario"] = scenario_json

        return {
            "status": "success",
            "scenario_length": len(scenario_text),
            "has_options": "option_a" in scenario_json and "option_b" in scenario_json,
            "option_a_length": len(scenario_json.get("option_a", "")),
            "option_b_length": len(scenario_json.get("option_b", ""))
        }
    except Exception as e:
        error_msg = f"Error generating scenario with Gemini: {str(e)}"
        print(f"⚠️ {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error_message": error_msg
        }


def save_scenario_to_firestore(tool_context: ToolContext) -> dict:
    """Saves the generated scenario to Firestore.
        
        Returns:
        dict: Save status and document ID
    """
    try:
        # Validate that we have all required data BEFORE saving
        case = tool_context.state.get("scenario_case", {})
        patient = tool_context.state.get("scenario_patient", {})
        student = tool_context.state.get("scenario_student", {})
        scenario = tool_context.state.get("generated_scenario", {})
        
        # Validate scenario data exists and is complete
        if not scenario:
            return {
                "status": "error",
                "error_message": "No scenario generated. Please run scenario_content_generator first."
            }
        
        if not scenario.get("scenario") or len(scenario.get("scenario", "")) < 50:
            return {
                "status": "error",
                "error_message": "Scenario text is missing or too short. Please regenerate."
            }
        
        if not scenario.get("option_a") or len(scenario.get("option_a", "")) < 20:
            return {
                "status": "error",
                "error_message": "Option A is missing or incomplete. Please regenerate."
            }
        
        if not scenario.get("option_b") or len(scenario.get("option_b", "")) < 20:
            return {
                "status": "error",
                "error_message": "Option B is missing or incomplete. Please regenerate."
            }
        
        # Use FIREBASE_PROJECT_ID if available, otherwise auto-detect
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if project_id:
            db = firestore.Client(project=project_id)
        else:
            db = firestore.Client()

        scenario_doc = {
            "case": {
                "name": case.get("name"),
                "code": case.get("code"),
                "description": case.get("description", "")
            },
            "patient": {
                "full_name": patient.get("full_name"),
                "age": patient.get("age"),
                "asa_classification": patient.get("asa_classification"),
                "medical_history": patient.get("medical_history", "")
            },
            "student": {
                "name": student.get("name"),
                "id": student.get("id"),
                "class_standing": student.get("class_standing")
            },
            "scenario": scenario.get("scenario", ""),
            "decision_point": scenario.get("decision_point", ""),
            "option_a": scenario.get("option_a", ""),
            "option_b": scenario.get("option_b", ""),
            "best_answer": scenario.get("best_answer", ""),
            "rationale": scenario.get("rationale", ""),
            "learning_points": scenario.get("learning_points", []),
            "created_at": SERVER_TIMESTAMP,
            "agent": "scenario_agent",
            "adk_version": "1.0"
        }
        
        # Debug: Print what we're saving
        print(f"\n💾 Saving scenario to Firestore:")
        print(f"   - Scenario length: {len(scenario.get('scenario', ''))}")
        print(f"   - Option A length: {len(scenario.get('option_a', ''))}")
        print(f"   - Option B length: {len(scenario.get('option_b', ''))}")
        print(f"   - Rationale length: {len(scenario.get('rationale', ''))}")
        print(f"   - Best answer: {scenario.get('best_answer', '')}")
        print(f"   - Has decision_point: {bool(scenario.get('decision_point'))}")
        print(f"   - Full scenario keys: {list(scenario.keys())}")
        print(f"   - Option A value (first 100 chars): {scenario.get('option_a', '')[:100] if scenario.get('option_a') else 'MISSING'}")
        print(f"   - Option B value (first 100 chars): {scenario.get('option_b', '')[:100] if scenario.get('option_b') else 'MISSING'}\n")

        doc_ref = db.collection("agent_scenarios").add(scenario_doc)
        doc_id = doc_ref[1].id

        tool_context.state["scenario_doc_id"] = doc_id

        return {
            "status": "success",
            "doc_id": doc_id,
            "case_name": case.get("name"),
            "student_name": student.get("name")
        }
    except Exception as e:
        error_msg = f"Error saving scenario: {str(e)}"
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

# Scenario Data Loader
scenario_data_loader = Agent(
    name="scenario_data_loader",
    model="gemini-2.0-flash",
    description="Loads cases, patients, and students for scenarios",
    instruction="""
    You load data needed for clinical scenario generation.
    
    IMPORTANT: You MUST use your load_scenario_data_to_state tool to load:
    1. Cases from data/cases.json
    2. Patient templates from data/patient_templates.json
    3. Students from data/students.json
    
    Load all three data files into the session state. Do not proceed until all data is loaded.
    """,
    tools=[load_scenario_data_to_state]
)

# Case Selector for Scenarios
scenario_case_selector = Agent(
    name="scenario_case_selector",
    model="gemini-2.0-flash",
    description="Selects a case for scenario generation",
    instruction="""
    You select a clinical case for scenario generation.
    
    IMPORTANT: You MUST use your select_scenario_case tool to select a case.
    
    Available cases: {scenario_cases?}
    
    Call your tool to select a random case.
    """,
    tools=[select_scenario_case]
)

# Patient Matcher
patient_matcher = Agent(
    name="patient_matcher",
    model="gemini-2.0-flash",
    description="Matches patients to cases based on age and ASA",
    instruction="""
    You match patient templates to clinical cases.
    
    IMPORTANT: You MUST use your match_patient_to_case tool to find a matching patient.
    
    Selected case: {scenario_case?}
    Available patients: {patient_templates?}
    
    Match based on age range and ASA classification.
    Call your tool to find a suitable patient.
    """,
    tools=[match_patient_to_case]
)

# Student Selector
scenario_student_selector = Agent(
    name="scenario_student_selector",
    model="gemini-2.0-flash",
    description="Selects a student to receive the scenario",
    instruction="""
    You select a student to receive this clinical scenario.
    
    IMPORTANT: You MUST use your select_target_student tool to select a student.
    
    Available students: {scenario_students?}
    
    Call your tool to select a student.
    """,
    tools=[select_target_student]
)

# Scenario Content Generator
scenario_content_generator = Agent(
    name="scenario_content_generator",
    model="gemini-2.0-flash",
    description="Generates scenario content with Gemini",
    instruction="""
    You generate detailed clinical scenarios with decision options.
    
    IMPORTANT: You MUST use your generate_scenario_with_gemini tool to generate the complete scenario.
    
    Case: {scenario_case?}
    Patient: {scenario_patient?}
    Student: {scenario_student?}
    
    The tool will generate:
    - A detailed patient presentation scenario (2-3 paragraphs)
    - A decision point question
    - Two complete options (A and B) with detailed descriptions
    - Best answer
    - Rationale
    - Learning points
    
    Call your tool now to generate the scenario. Do not proceed until the tool has been called.
    """,
    tools=[generate_scenario_with_gemini]
)

# Scenario Saver
scenario_saver = Agent(
    name="scenario_saver",
    model="gemini-2.0-flash",
    description="Saves scenarios to Firestore",
    instruction="""
    You save generated scenarios to Firestore.
    
    IMPORTANT: You MUST use your save_scenario_to_firestore tool to save the scenario.
    
    Case: {scenario_case?}
    Patient: {scenario_patient?}
    Student: {scenario_student?}
    Scenario: {generated_scenario?}
    
    Call your tool to save this scenario to the agent_scenarios collection.
    """,
    tools=[save_scenario_to_firestore]
)


# ===========================================
# WORKFLOW (Sequential execution)
# ===========================================

# Import image agent for automatic image generation
try:
    from agents.image_agent import image_generator
    IMAGE_AGENT_AVAILABLE = True
except ImportError:
    IMAGE_AGENT_AVAILABLE = False
    print("⚠️ Image agent not available - scenarios will be created without images")

# Build sub-agents list
scenario_sub_agents = [
    scenario_data_loader,
    scenario_case_selector,
    patient_matcher,
    scenario_student_selector,
    scenario_content_generator,
    scenario_saver
]

# Add image generation as final step if available
if IMAGE_AGENT_AVAILABLE:
    scenario_sub_agents.append(image_generator)
    print("✅ Image generation will run automatically after scenario creation")

scenario_agent = SequentialAgent(
    name="scenario_agent",
    description="Generates complete clinical scenarios with case selection, patient matching, content generation, Firestore storage, and automatic image generation",
    sub_agents=scenario_sub_agents
)


# Export the main agent
__all__ = ["scenario_agent"]
