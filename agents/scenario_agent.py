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
        
        print(f"✅ Clinical Scenario Agent initialized")
        print(f"   - Cases loaded: {len(self.cases)}")
        print(f"   - Patient templates loaded: {len(self.patient_templates)}")
        print(f"   - Vector Search: {'Available' if self.vector_tool else 'Not available'}")
        print(f"   - Gemini Agent: {'Available' if self.gemini_agent else 'Not available'}")
        print(f"   - State Agent: {'Available' if self.state_agent else 'Not available'}")
    
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
        save_to_firestore: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a complete clinical scenario.
        
        Args:
            case: Optional case to use (if None, selects randomly)
            patient: Optional patient to use (if None, matches to case)
            save_to_file: Whether to save scenario to Context/Scenario.md
            save_to_firestore: Whether to save scenario to Firestore
        
        Returns:
            Complete scenario data dictionary
        """
        if not self.gemini_agent:
            raise ValueError("Gemini Agent not available. Cannot generate scenario.")
        
        # Update state to GENERATING
        if self.state_agent:
            self.state_agent.set_agent_state("scenario_agent", StateAgent.STATE_GENERATING)
        
        try:
            # Step 1: Select case if not provided
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
            scenario_data = self.gemini_agent.generate_scenario(
                case=case,
                patient=patient,
                medical_content=medical_content
            )
            
            # Step 5: Save to file if requested
            firestore_id = None
            if save_to_file:
                self._save_scenario_to_file(scenario_data)
            
            # Step 6: Save to Firestore if requested
            if save_to_firestore and FIRESTORE_AVAILABLE:
                try:
                    firestore_service = get_firestore_service(force_refresh=True)
                    if firestore_service:
                        import copy
                        firestore_scenario = copy.deepcopy(scenario_data)
                        firestore_id = firestore_service.save_scenario(firestore_scenario)
                        print(f"✅ Scenario saved to Firestore: {firestore_id}")
                except Exception as firestore_error:
                    print(f"⚠️ Failed to save scenario to Firestore: {firestore_error}")
                    # Update state to ERROR
                    if self.state_agent:
                        self.state_agent.set_agent_error("scenario_agent", str(firestore_error))
            
            # Return complete scenario data
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
                    StateAgent.STATE_COMPLETED
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

