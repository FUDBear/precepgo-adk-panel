"""
Scenario Agent
Independent agent for generating clinical scenarios with decision options.
Handles case selection, patient matching, content retrieval, and scenario generation.
"""

import os
import json
import random
from datetime import datetime
from typing import Dict, Any, Optional

# Import dependencies
try:
    from gemini_agent import GeminiAgent, MODEL_GEMINI_PRO
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    MODEL_GEMINI_PRO = "models/gemini-2.5-pro"  # Fallback model name
    print("⚠️ Gemini Agent not available")

try:
    from vector_search_tool import VectorSearchTool
    VECTOR_SEARCH_AVAILABLE = True
except ImportError:
    VECTOR_SEARCH_AVAILABLE = False
    print("⚠️ Vector Search not available")

try:
    from firestore_service import get_firestore_service
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    print("⚠️ Firestore not available")

try:
    from agents.state_agent import StateAgent
    STATE_AGENT_AVAILABLE = True
except ImportError:
    STATE_AGENT_AVAILABLE = False
    print("⚠️ State Agent not available")

# Image Generation Agent import (optional - for auto-generating images after scenario creation)
try:
    from agents.image_agent import ImageGenerationAgent
    IMAGE_AGENT_AVAILABLE = True
except ImportError:
    IMAGE_AGENT_AVAILABLE = False
    ImageGenerationAgent = None
    print("⚠️ Image Generation Agent not available")


class ClinicalScenarioAgent:
    """
    Independent agent for generating clinical scenarios.
    Handles the complete workflow from case selection to scenario generation and storage.
    """
    
    def __init__(
        self,
        cases: Optional[list] = None,
        patient_templates: Optional[list] = None,
        model_name: Optional[str] = None
    ):
        """
        Initialize the Clinical Scenario Agent.
        
        Args:
            cases: List of cases (if None, will load from data/cases.json)
            patient_templates: List of patient templates (if None, will load from data/patient_templates.json)
            model_name: Gemini model to use for scenario generation (defaults to MODEL_GEMINI_PRO if available)
        """
        # Load cases if not provided, or normalize if provided
        if cases is None:
            self.cases = self._load_cases()
        else:
            # Normalize cases to ensure it's a list
            self.cases = self._normalize_cases(cases)
        
        self.patient_templates = patient_templates or self._load_patient_templates()
        self.model_name = model_name or (MODEL_GEMINI_PRO if GEMINI_AVAILABLE else "models/gemini-2.5-pro")
        
        # Load students for personalized scenario generation
        self.students = self._load_students()
        
        # Initialize Gemini Agent
        if GEMINI_AVAILABLE:
            self.gemini_agent = GeminiAgent(model_name=self.model_name)
        else:
            self.gemini_agent = None
            print("⚠️ Clinical Scenario Agent initialized without Gemini support")
        
        # Initialize Vector Search Tool
        if VECTOR_SEARCH_AVAILABLE:
            self.vector_tool = VectorSearchTool()
        else:
            self.vector_tool = None
        
        # Initialize Firestore client (for state tracking)
        self.db = None
        if FIRESTORE_AVAILABLE:
            try:
                from google.cloud import firestore
                project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
                if project_id:
                    self.db = firestore.Client(project=project_id)
                else:
                    self.db = firestore.Client()
            except Exception as e:
                print(f"⚠️ Firestore initialization failed: {e}")
                self.db = None
        
        # Initialize State Agent for state tracking (after Firestore is initialized)
        self.state_agent = None
        if STATE_AGENT_AVAILABLE and self.db:
            try:
                self.state_agent = StateAgent(firestore_db=self.db)
            except Exception as e:
                print(f"⚠️ State Agent failed to initialize: {e}")
                self.state_agent = None
        
        # Initialize Image Generation Agent (optional - for auto-generating images)
        self.image_agent = None
        if IMAGE_AGENT_AVAILABLE and self.db:
            try:
                # Get project ID for bucket configuration
                project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
                
                print(f"\n🎨 Initializing Image Generation Agent...")
                print(f"   - Project ID: {project_id}")
                print(f"   - Firestore DB: {'Available' if self.db else 'Not available'}")
                
                # Use explicit bucket URL if available, otherwise use the working bucket
                # Default to auth-demo-90be0.appspot.com which is the working bucket
                storage_bucket_url = os.getenv("STORAGE_BUCKET_URL")
                if not storage_bucket_url:
                    # Use the working bucket as default
                    storage_bucket_url = "gs://auth-demo-90be0.appspot.com/agent_assets"
                    print(f"   - Using default bucket URL: {storage_bucket_url}")
                else:
                    print(f"   - Using bucket URL from env: {storage_bucket_url}")
                
                # Parse bucket name from URL
                if storage_bucket_url.startswith("gs://"):
                    parts = storage_bucket_url.replace("gs://", "").split("/", 1)
                    storage_bucket_name = parts[0]
                    storage_folder = parts[1] if len(parts) > 1 else "agent_assets"
                else:
                    storage_bucket_name = storage_bucket_url
                    storage_folder = "agent_assets"
                
                print(f"   - Storage Bucket Name: {storage_bucket_name}")
                print(f"   - Storage Folder: {storage_folder}")
                
                self.image_agent = ImageGenerationAgent(
                    firestore_db=self.db,
                    project_id=project_id,
                    storage_bucket_name=storage_bucket_name,
                    storage_folder=storage_folder
                )
                
                print(f"   - Image Agent created: {'✅' if self.image_agent else '❌'}")
                
                # Check if image agent is fully ready (has model and bucket)
                if self.image_agent:
                    has_model = self.image_agent.imagen_model is not None
                    has_bucket = self.image_agent.bucket is not None
                    
                    print(f"   - Imagen Model: {'✅ Available' if has_model else '❌ Not available'}")
                    print(f"   - Storage Bucket: {'✅ Available' if has_bucket else '❌ Not available'}")
                    
                    if has_model and has_bucket:
                        print(f"✅ Image Generation Agent: Fully initialized (auto-generate images enabled)")
                        print(f"   - Storage Bucket: {storage_bucket_name}")
                        print(f"   - Storage Folder: {storage_folder}")
                    elif has_model:
                        print(f"⚠️ Image Generation Agent: Model available but bucket not ready (images will be skipped)")
                        self.image_agent = None  # Don't enable auto-generation if bucket not available
                    else:
                        print(f"⚠️ Image Generation Agent: Not fully initialized (missing model or bucket)")
                        self.image_agent = None
                else:
                    print(f"❌ Image Generation Agent: Failed to create")
            except Exception as e:
                print(f"⚠️ Image Generation Agent failed to initialize: {e}")
                import traceback
                traceback.print_exc()
                self.image_agent = None
        elif IMAGE_AGENT_AVAILABLE:
            print(f"   - Image Generation Agent: Not available (Firestore required)")
            print(f"     - IMAGE_AGENT_AVAILABLE: {IMAGE_AGENT_AVAILABLE}")
            print(f"     - self.db: {self.db is not None}")
        else:
            print(f"   - Image Generation Agent: Not available (IMAGE_AGENT_AVAILABLE=False)")
        
        print(f"✅ Clinical Scenario Agent initialized")
        print(f"   - Cases loaded: {len(self.cases)}")
        print(f"   - Patient templates loaded: {len(self.patient_templates)}")
        print(f"   - Students loaded: {len(self.students)}")
        print(f"   - Vector Search: {'Available' if self.vector_tool else 'Not available'}")
        print(f"   - Gemini Agent: {'Available' if self.gemini_agent else 'Not available'}")
        print(f"   - State Agent: {'Available' if self.state_agent else 'Not available'}")
        print(f"   - Image Generation Agent: {'✅ Available (auto-generate enabled)' if self.image_agent else 'Not available'}")
    
    def _normalize_cases(self, cases: Any) -> list:
        """
        Normalize cases data structure to ensure it's a list.
        Handles dict, list, or other structures.
        
        Args:
            cases: Cases data (can be dict, list, etc.)
            
        Returns:
            List of case dictionaries
        """
        if isinstance(cases, list):
            return cases
        elif isinstance(cases, dict):
            if 'procedures' in cases:
                return cases['procedures']
            else:
                # If dict values are lists, flatten them
                case_list = list(cases.values())
                if case_list and isinstance(case_list[0], list):
                    return [item for sublist in case_list for item in sublist]
                # If dict values are dicts, return them as list
                return case_list
        else:
            print(f"⚠️ Unexpected cases data type: {type(cases)}")
            return []
    
    def _load_cases(self) -> list:
        """Load cases from JSON file"""
        try:
            with open("data/cases.json", "r") as f:
                data = json.load(f)
            
            # Handle different JSON structures
            if isinstance(data, dict):
                if 'procedures' in data:
                    return data['procedures']
                else:
                    case_list = list(data.values())
                    if case_list and isinstance(case_list[0], list):
                        return [item for sublist in case_list for item in sublist]
                    return case_list
            elif isinstance(data, list):
                return data
            else:
                print("⚠️ Invalid cases.json structure")
                return []
        except FileNotFoundError:
            print("⚠️ data/cases.json not found")
            return []
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing data/cases.json: {e}")
            return []
    
    def _load_patient_templates(self) -> list:
        """Load patient templates from JSON file"""
        try:
            with open("data/patient_templates.json", "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print("⚠️ data/patient_templates.json not found")
            return []
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing data/patient_templates.json: {e}")
            return []
    
    def _load_students(self) -> list:
        """Load students from JSON file"""
        try:
            with open("data/students.json", "r") as f:
                data = json.load(f)
                if isinstance(data, dict) and "students" in data:
                    return data["students"]
                elif isinstance(data, list):
                    return data
                else:
                    return []
        except FileNotFoundError:
            print("⚠️ data/students.json not found")
            return []
        except json.JSONDecodeError as e:
            print(f"⚠️ Error parsing data/students.json: {e}")
            return []
    
    def _get_student_evaluations(self, student_id: str, student_name: str) -> list:
        """
        Get all evaluations for a student from Firestore.
        
        Args:
            student_id: Student ID
            student_name: Student name
            
        Returns:
            List of evaluation documents
        """
        if not self.db:
            return []
        
        try:
            evaluations = []
            collection_ref = self.db.collection('agent_evaluations')
            
            # Query by student ID
            query_by_id = collection_ref.where('preceptee_user_id', '==', student_id).stream()
            for doc in query_by_id:
                eval_data = doc.to_dict()
                eval_data['doc_id'] = doc.id
                if not any(e.get('doc_id') == doc.id for e in evaluations):
                    evaluations.append(eval_data)
            
            # Query by student name (in case ID doesn't match)
            query_by_name = collection_ref.where('preceptee_user_name', '==', student_name).stream()
            for doc in query_by_name:
                eval_data = doc.to_dict()
                eval_data['doc_id'] = doc.id
                if not any(e.get('doc_id') == doc.id for e in evaluations):
                    evaluations.append(eval_data)
            
            # Sort by completion_date if available (most recent first)
            evaluations.sort(
                key=lambda e: e.get('completion_date', ''),
                reverse=True
            )
            
            return evaluations
        except Exception as e:
            print(f"⚠️ Error fetching student evaluations: {e}")
            return []
    
    def _analyze_student_struggles(self, evaluations: list) -> Dict[str, Any]:
        """
        Analyze student evaluations to identify struggling areas.
        
        Args:
            evaluations: List of evaluation documents
            
        Returns:
            Dictionary with struggling areas, recent cases, and analysis
        """
        if not evaluations:
            return {
                "struggling_areas": [],
                "recent_cases": [],
                "weak_ac_scores": [],
                "weak_pc_scores": [],
                "focus_areas": [],
                "comments": []
            }
        
        struggling_areas = []
        recent_cases = []
        weak_ac_scores = []
        weak_pc_scores = []
        all_focus_areas = []
        all_comments = []
        
        for eval_data in evaluations[:10]:  # Analyze last 10 evaluations
            case_type = eval_data.get('case_type', '')
            if case_type:
                recent_cases.append(case_type)
            
            # Collect focus areas
            focus_areas = eval_data.get('focus_areas', '')
            if focus_areas:
                all_focus_areas.append(focus_areas)
            
            # Collect comments
            comments = eval_data.get('comments', '')
            if comments:
                all_comments.append(comments)
            
            # Find weak AC scores (<70)
            for i in range(13):
                ac_key = f"ac_{i}"
                score = eval_data.get(ac_key)
                if isinstance(score, (int, float)) and score < 70:
                    weak_ac_scores.append({
                        "metric": ac_key,
                        "score": score,
                        "case": case_type
                    })
            
            # Find weak PC scores (<3 and >0, meaning not N/A)
            for i in range(11):
                pc_key = f"pc_{i}"
                score = eval_data.get(pc_key)
                if isinstance(score, (int, float)) and 0 < score < 3:
                    weak_pc_scores.append({
                        "metric": pc_key,
                        "score": score,
                        "case": case_type
                    })
        
        # Extract struggling areas from focus areas and comments
        struggling_keywords = []
        for focus_area in all_focus_areas:
            if focus_area:
                # Extract key phrases (simplified)
                struggling_keywords.extend(focus_area.lower().split(';'))
        
        for comment in all_comments:
            if comment:
                # Look for negative indicators
                negative_indicators = ['needs improvement', 'struggled', 'difficulty', 'challenge', 'concern', 'should focus']
                comment_lower = comment.lower()
                for indicator in negative_indicators:
                    if indicator in comment_lower:
                        struggling_keywords.append(indicator)
        
        return {
            "struggling_areas": list(set(struggling_keywords[:10])),  # Unique keywords
            "recent_cases": list(set(recent_cases[:10])),  # Unique recent cases
            "weak_ac_scores": weak_ac_scores[:10],
            "weak_pc_scores": weak_pc_scores[:10],
            "focus_areas": all_focus_areas[:5],
            "comments": all_comments[:5]
        }
    
    def _select_case_for_student(self, student: Dict[str, Any], analysis: Dict[str, Any]) -> tuple:
        """
        Select a case that would benefit the student based on their evaluations.
        
        Args:
            student: Student information
            analysis: Analysis of student's struggles
            
        Returns:
            Tuple of (selected_case, rationale)
        """
        recent_cases = analysis.get("recent_cases", [])
        struggling_areas = analysis.get("struggling_areas", [])
        weak_ac_scores = analysis.get("weak_ac_scores", [])
        weak_pc_scores = analysis.get("weak_pc_scores", [])
        
        rationale_parts = []
        
        # If student has recent cases, prioritize those types for reinforcement
        if recent_cases:
            # Try to find a case matching recent case types
            recent_case_name = recent_cases[0]  # Most recent
            matching_cases = [
                case for case in self.cases
                if recent_case_name.lower() in case.get('name', '').lower() or
                   any(keyword.lower() in recent_case_name.lower() for keyword in case.get('keywords', []))
            ]
            
            if matching_cases:
                selected_case = random.choice(matching_cases)
                rationale_parts.append(f"Student recently completed '{recent_case_name}' cases and could benefit from additional practice")
                return selected_case, " ".join(rationale_parts)
        
        # Otherwise, look for cases that match struggling areas
        if struggling_areas or weak_ac_scores or weak_pc_scores:
            # Try to find cases matching struggling keywords
            struggling_text = " ".join(struggling_areas[:5]).lower()
            matching_cases = []
            
            for case in self.cases:
                case_text = f"{case.get('name', '')} {case.get('description', '')} {' '.join(case.get('keywords', []))}".lower()
                # Check if any struggling keyword matches case keywords
                for keyword in struggling_areas[:5]:
                    if keyword in case_text:
                        matching_cases.append(case)
                        break
            
            if matching_cases:
                selected_case = random.choice(matching_cases)
                rationale_parts.append(f"Student has areas for improvement that align with '{selected_case.get('name')}' cases")
                if weak_ac_scores:
                    rationale_parts.append(f"Specifically struggling with: {', '.join([s['metric'] for s in weak_ac_scores[:3]])}")
                if weak_pc_scores:
                    rationale_parts.append(f"Behavioral areas needing attention: {', '.join([s['metric'] for s in weak_pc_scores[:2]])}")
                return selected_case, " ".join(rationale_parts)
        
        # Fallback: Select random case
        selected_case = random.choice(self.cases)
        rationale_parts.append(f"Selected '{selected_case.get('name')}' to provide diverse clinical exposure")
        return selected_case, " ".join(rationale_parts)
    
    def match_patient_to_case(self, case: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Match a patient from patient_templates.json that fits the case type.
        
        Args:
            case: Case information from cases.json
            
        Returns:
            Matching patient or None
        """
        if not self.patient_templates:
            return None
        
        case_keywords = [k.lower() for k in case.get('keywords', [])]
        case_name = case.get('name', '').lower()
        case_description = case.get('description', '').lower()
        
        # Create a combined search text
        search_text = ' '.join([case_name, case_description] + case_keywords)
        
        # Score each patient based on category/keyword matches
        scored_patients = []
        for patient in self.patient_templates:
            score = 0
            patient_categories = [c.lower() for c in patient.get('categories', [])]
            patient_comorbidities = [c.lower() for c in patient.get('comorbidities', [])]
            
            # Check for category matches (e.g., "Pediatric", "Cardiac", "Orthopedic")
            category_keywords = {
                'pediatric': ['pediatric', 'ped', 'child', 'infant', 'adolescent'],
                'cardiac': ['cardiac', 'heart', 'cardiac surgery', 'cabg', 'valve'],
                'orthopedic': ['orthopedic', 'ortho', 'knee', 'hip', 'shoulder', 'fracture'],
                'trauma': ['trauma', 'emergency', 'injury'],
                'bariatric': ['bariatric', 'obesity', 'gastric'],
                'neurosurgical': ['neurosurgical', 'neuro', 'brain', 'spine', 'craniotomy'],
                'thoracic': ['thoracic', 'lung', 'pulmonary', 'lobectomy'],
                'vascular': ['vascular', 'artery', 'vein', 'aneurysm'],
                'ent': ['ent', 'ear', 'nose', 'throat', 'laryngectomy', 'thyroid'],
                'obstetric': ['obstetric', 'ob', 'c-section', 'cesarean', 'delivery']
            }
            
            # Match case keywords to patient categories
            for category, keywords in category_keywords.items():
                if any(kw in search_text for kw in keywords):
                    if category in patient_categories:
                        score += 10
            
            # Check for specific keyword matches in comorbidities
            for keyword in case_keywords:
                if keyword in ' '.join(patient_comorbidities):
                    score += 5
            
            scored_patients.append((score, patient))
        
        # Sort by score and return top match
        scored_patients.sort(key=lambda x: x[0], reverse=True)
        
        if scored_patients and scored_patients[0][0] > 0:
            return scored_patients[0][1]
        
        # Fallback: return random patient
        return random.choice(self.patient_templates) if self.patient_templates else None
    
    def get_medical_content_for_scenario(
        self,
        case: Dict[str, Any],
        patient: Dict[str, Any]
    ) -> str:
        """
        Get relevant medical content from Vector Search for the case and patient.
        
        Args:
            case: Case information
            patient: Patient information
            
        Returns:
            Combined medical content string
        """
        if not self.vector_tool:
            return "Medical content unavailable - Vector Search not configured"
        
        # Build search queries from case and patient
        search_queries = []
        
        # Add case keywords
        search_queries.extend(case.get('keywords', [])[:3])
        
        # Add case name
        search_queries.append(case.get('name', ''))
        
        # Add patient comorbidities
        search_queries.extend(patient.get('comorbidities', [])[:2])
        
        # Add patient categories
        category_keywords = {
            'Pediatric': 'pediatric anesthesia',
            'Cardiac': 'cardiac anesthesia',
            'Orthopedic': 'orthopedic anesthesia',
            'Trauma': 'trauma anesthesia',
            'Bariatric': 'bariatric anesthesia',
            'Neurosurgical': 'neurosurgical anesthesia',
            'Thoracic': 'thoracic anesthesia',
            'Vascular': 'vascular anesthesia',
            'ENT': 'ENT anesthesia',
            'Obstetric': 'obstetric anesthesia'
        }
        
        for category in patient.get('categories', []):
            if category in category_keywords:
                search_queries.append(category_keywords[category])
        
        # Remove duplicates
        search_queries = list(dict.fromkeys([q for q in search_queries if q]))
        
        # Perform Vector Search for each query
        all_content = []
        
        for query in search_queries[:5]:  # Limit to 5 queries
            try:
                results = self.vector_tool.search(query=query, num_results=3)
                if results.get('success') and results.get('num_results', 0) > 0:
                    documents = results['results']['documents']
                    all_content.extend(documents)
            except Exception as e:
                print(f"⚠️ Vector Search error for '{query}': {e}")
                continue
        
        # Combine and return
        combined_content = "\n\n".join(all_content[:10])  # Limit to 10 chunks
        return combined_content if combined_content else "No relevant medical content found"
    
    def select_case(self) -> Dict[str, Any]:
        """
        Select a random case from available cases.
        
        Returns:
            Selected case dictionary
        """
        if not self.cases:
            raise ValueError("No cases available. Please ensure data/cases.json exists and contains valid cases.")
        
        return random.choice(self.cases)
    
    def generate_scenario(
        self,
        case: Optional[Dict[str, Any]] = None,
        patient: Optional[Dict[str, Any]] = None,
        save_to_file: bool = True,
        save_to_firestore: bool = True,
        use_student_selection: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a complete clinical scenario.
        Optionally selects a student and analyzes their evaluations to create a personalized scenario.
        
        Args:
            case: Optional case to use (if None, selects based on student or randomly)
            patient: Optional patient to use (if None, matches to case)
            save_to_file: Whether to save scenario to Context/Scenario.md
            save_to_firestore: Whether to save scenario to Firestore
            use_student_selection: Whether to select a student and personalize the scenario
        
        Returns:
            Complete scenario data dictionary with student info and rationale
        """
        if not self.gemini_agent:
            raise ValueError("Gemini Agent not available. Cannot generate scenario.")
        
        # Update state to GENERATING
        if self.state_agent:
            self.state_agent.set_agent_state("scenario_agent", StateAgent.STATE_ACTIVE)
        
        selected_student = None
        case_rationale = None
        student_analysis = None
        
        try:
            # Step 0: Select student and analyze evaluations if requested
            if use_student_selection and self.students and self.db:
                selected_student = random.choice(self.students)
                student_id = selected_student.get("id")
                student_name = selected_student.get("name")
                
                print(f"👨‍🎓 Selected student: {student_name} ({student_id})")
                
                # Get student evaluations
                evaluations = self._get_student_evaluations(student_id, student_name)
                print(f"📊 Found {len(evaluations)} evaluation(s) for student")
                
                # Analyze struggles
                student_analysis = self._analyze_student_struggles(evaluations)
                
                # Select case based on student's needs
                if not case:
                    case, case_rationale = self._select_case_for_student(selected_student, student_analysis)
                    print(f"📋 Selected case: {case.get('name', 'Unknown')}")
                    print(f"💡 Rationale: {case_rationale}")
            
            # Step 1: Select case if not provided and not already selected
            if not case:
                case = self.select_case()
                print(f"📋 Selected case: {case.get('name', 'Unknown')}")
            
            # Step 2: Match patient to case if not provided
            if not patient:
                patient = self.match_patient_to_case(case)
                if not patient:
                    raise ValueError("No matching patient found for case")
            print(f"👤 Matched patient: {patient.get('full_name', 'Unknown')}")
            
            # Step 3: Get medical content from Vector Search
            print("🔍 Searching Vector DB for medical content...")
            medical_content = self.get_medical_content_for_scenario(case, patient)
            
            if not medical_content or medical_content == "No relevant medical content found":
                print("⚠️ Limited medical content found, using basic case description")
                medical_content = f"{case.get('description', '')}\n\nKeywords: {', '.join(case.get('keywords', []))}"
            
            # Step 4: Generate scenario using Gemini Agent
            print("🤖 Generating scenario with Gemini Agent...")
            
            # Build context about student struggles if available
            student_context = ""
            if selected_student and student_analysis:
                student_context = f"""
**STUDENT CONTEXT:**
Student: {selected_student.get('name')} ({selected_student.get('class_standing')})
Recent Cases: {', '.join(student_analysis.get('recent_cases', [])[:3]) if student_analysis.get('recent_cases') else 'None'}
Areas for Improvement: {', '.join(student_analysis.get('struggling_areas', [])[:3]) if student_analysis.get('struggling_areas') else 'None'}
Weak Performance Areas: {len(student_analysis.get('weak_ac_scores', []))} AC metrics, {len(student_analysis.get('weak_pc_scores', []))} PC metrics need improvement

When generating this scenario, consider:
- The student may benefit from practicing this type of case
- Focus on areas where they've shown weakness in evaluations
- Provide clear learning points that address their specific needs
- Make the scenario challenging but appropriate for their class standing
"""
            
            scenario_data = self.gemini_agent.generate_scenario(
                case=case,
                patient=patient,
                medical_content=medical_content,
                student_context=student_context if student_context else None
            )
            
            # Step 5: Add student selection info to scenario data (before saving to Firestore)
            if selected_student:
                scenario_data["student"] = {
                    "id": selected_student.get("id"),
                    "name": selected_student.get("name"),
                    "class_standing": selected_student.get("class_standing"),
                    "hospital": selected_student.get("hospital")
                }
                scenario_data["case_rationale"] = case_rationale
                if student_analysis:
                    scenario_data["student_analysis"] = {
                        "recent_cases": student_analysis.get("recent_cases", [])[:5],
                        "struggling_areas": student_analysis.get("struggling_areas", [])[:5],
                        "weak_ac_count": len(student_analysis.get("weak_ac_scores", [])),
                        "weak_pc_count": len(student_analysis.get("weak_pc_scores", []))
                    }
            
            # Step 6: Save to file if requested
            firestore_id = None
            if save_to_file:
                self._save_scenario_to_file(scenario_data)
            
            # Step 7: Save to Firestore if requested (includes student info)
            if save_to_firestore and FIRESTORE_AVAILABLE:
                try:
                    firestore_service = get_firestore_service(force_refresh=True)
                    if firestore_service:
                        import copy
                        firestore_scenario = copy.deepcopy(scenario_data)
                        firestore_id = firestore_service.save_scenario(firestore_scenario)
                        print(f"✅ Scenario saved to Firestore: {firestore_id}")
                        
                        # Step 7a: Auto-generate image for the scenario (if image agent is available)
                        print(f"\n{'='*60}")
                        print(f"🎨 Image Generation Check")
                        print(f"{'='*60}")
                        print(f"   - firestore_id: {firestore_id}")
                        print(f"   - self.image_agent exists: {self.image_agent is not None}")
                        
                        if firestore_id:
                            if self.image_agent:
                                print(f"   - Image agent available: ✅")
                                print(f"   - imagen_model available: {self.image_agent.imagen_model is not None}")
                                print(f"   - bucket available: {self.image_agent.bucket is not None}")
                                
                                # Check if image agent is fully ready
                                if not self.image_agent.imagen_model:
                                    print(f"   ⚠️ Skipping auto-image generation: Imagen model not available")
                                elif not self.image_agent.bucket:
                                    print(f"   ⚠️ Skipping auto-image generation: Storage bucket not available")
                                else:
                                    try:
                                        print(f"\n🎨 Starting auto-image generation for scenario {firestore_id}...")
                                        image_result = self.image_agent.process_scenario_document(firestore_id)
                                        
                                        print(f"\n📊 Image Generation Result:")
                                        print(f"   - Success: {image_result.get('success')}")
                                        print(f"   - Skipped: {image_result.get('skipped', False)}")
                                        print(f"   - Error: {image_result.get('error', 'None')}")
                                        
                                        if image_result.get("success"):
                                            image_url = image_result.get("image_url")
                                            if image_url:
                                                print(f"✅ Image generated successfully: {image_url[:80]}...")
                                                # Add image URL to result
                                                scenario_data["image"] = image_url
                                                
                                                # Also update the Firestore document with the image URL
                                                try:
                                                    from google.cloud.firestore_v1 import SERVER_TIMESTAMP
                                                    scenario_ref = self.db.collection("agent_scenarios").document(firestore_id)
                                                    scenario_ref.update({
                                                        "image": image_url,
                                                        "image_generated_at": SERVER_TIMESTAMP,
                                                        "updated_at": SERVER_TIMESTAMP
                                                    })
                                                    print(f"✅ Updated Firestore document with image URL")
                                                except Exception as update_error:
                                                    print(f"⚠️ Failed to update Firestore document: {update_error}")
                                            else:
                                                print(f"⚠️ Image generation succeeded but no URL returned")
                                        else:
                                            error_msg = image_result.get("error", "Unknown error")
                                            print(f"⚠️ Image generation failed: {error_msg}")
                                            # Don't fail the scenario creation if image generation fails
                                    except Exception as image_error:
                                        print(f"⚠️ Exception during auto-image generation: {image_error}")
                                        import traceback
                                        traceback.print_exc()
                                        # Don't fail the scenario creation if image generation fails
                            else:
                                print(f"   ⚠️ Image agent not available: self.image_agent is None")
                                print(f"   - IMAGE_AGENT_AVAILABLE: {IMAGE_AGENT_AVAILABLE}")
                                print(f"   - self.db: {self.db is not None}")
                        else:
                            print(f"   ⚠️ No firestore_id available, skipping image generation")
                        print(f"{'='*60}\n")
                except Exception as firestore_error:
                    print(f"⚠️ Failed to save scenario to Firestore: {firestore_error}")
                    import traceback
                    traceback.print_exc()
                    # Update state to ERROR
                    if self.state_agent:
                        self.state_agent.set_agent_error("scenario_agent", str(firestore_error))
            
            # Return complete scenario data (already includes student info and image URL if generated)
            result = {
                **scenario_data,
                "firestore_id": firestore_id,
                "saved_to_firestore": firestore_id is not None,
                "saved_to_file": save_to_file
            }
            
            # Update state to COMPLETED and store result
            if self.state_agent:
                self.state_agent.set_agent_result(
                    "scenario_agent",
                    {
                        "firestore_id": firestore_id,
                        "case_name": case.get('name'),
                        "saved_to_file": save_to_file
                    },
                    StateAgent.STATE_IDLE
                )
            
            return result
            
        except Exception as e:
            # Update state to ERROR
            if self.state_agent:
                self.state_agent.set_agent_error("scenario_agent", str(e))
            raise
    
    def _save_scenario_to_file(self, scenario_data: Dict[str, Any]) -> str:
        """
        Save scenario to Context/Scenario.md file.
        
        Args:
            scenario_data: Scenario data dictionary
            
        Returns:
            File path where scenario was saved
        """
        output_filename = "Context/Scenario.md"
        
        # Ensure Context directory exists
        os.makedirs("Context", exist_ok=True)
        
        with open(output_filename, "w") as f:
            f.write(f"# Clinical Scenario: {scenario_data.get('case', {}).get('name', 'Unknown Case')}\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Case Information
            case_info = scenario_data.get('case', {})
            f.write(f"## Case Information\n\n")
            f.write(f"**Case:** {case_info.get('name', 'Unknown')}\n")
            f.write(f"**Code:** {case_info.get('code', 'N/A')}\n")
            f.write(f"**Description:** {case_info.get('description', 'N/A')}\n\n")
            
            # Patient Information
            patient_info = scenario_data.get('patient', {})
            f.write(f"## Patient Information\n\n")
            f.write(f"**Name:** {patient_info.get('name', 'Unknown')}\n")
            f.write(f"**Age:** {patient_info.get('age', 'Unknown')} years\n")
            f.write(f"**Categories:** {', '.join(patient_info.get('categories', []))}\n\n")
            
            # Scenario
            f.write(f"## Scenario\n\n")
            f.write(f"{scenario_data.get('scenario', 'No scenario provided')}\n\n")
            
            # Options
            f.write(f"## Decision Options\n\n")
            
            option_a = scenario_data.get('option_a', {})
            f.write(f"### Option A: {option_a.get('title', 'Option A')}\n\n")
            f.write(f"{option_a.get('description', 'No description')}\n\n")
            if option_a.get('considerations'):
                f.write(f"**Considerations:**\n")
                for consideration in option_a.get('considerations', []):
                    f.write(f"- {consideration}\n")
                f.write(f"\n")
            
            option_b = scenario_data.get('option_b', {})
            f.write(f"### Option B: {option_b.get('title', 'Option B')}\n\n")
            f.write(f"{option_b.get('description', 'No description')}\n\n")
            if option_b.get('considerations'):
                f.write(f"**Considerations:**\n")
                for consideration in option_b.get('considerations', []):
                    f.write(f"- {consideration}\n")
                f.write(f"\n")
            
            # Best Answer
            best_answer = scenario_data.get('best_answer', {})
            if best_answer:
                f.write(f"## Best Answer\n\n")
                f.write(f"**Recommended Option:** Option {best_answer.get('option', 'N/A')}\n\n")
                f.write(f"**Rationale:**\n\n")
                f.write(f"{best_answer.get('rationale', 'No rationale provided')}\n\n")
            
            # Learning Points
            if scenario_data.get('learning_points'):
                f.write(f"## Learning Points\n\n")
                for point in scenario_data.get('learning_points', []):
                    f.write(f"- {point}\n")
                f.write(f"\n")
            
            # References
            if scenario_data.get('references'):
                f.write(f"## References\n\n")
                f.write(f"{scenario_data.get('references')}\n\n")
            
            f.write(f"---\n\n")
            f.write(f"**Created:** {datetime.now().strftime('%B %d, %Y')}\n")
            f.write(f"**File Location:** {os.path.abspath(output_filename)}\n")
            f.write(f"**Source:** Vector Search - Barash Clinical Anesthesia, 9th Edition\n")
        
        print(f"✅ Scenario saved to {output_filename}")
        return output_filename


# Convenience function for easy importing
def create_scenario_agent(
    cases: Optional[list] = None,
    patient_templates: Optional[list] = None,
    model_name: Optional[str] = None
) -> ClinicalScenarioAgent:
    """
    Create a Clinical Scenario Agent instance.
    
    Args:
        cases: Optional list of cases
        patient_templates: Optional list of patient templates
        model_name: Gemini model to use (defaults to MODEL_GEMINI_PRO if available)
        
    Returns:
        ClinicalScenarioAgent instance
    """
    return ClinicalScenarioAgent(
        cases=cases,
        patient_templates=patient_templates,
        model_name=model_name
    )
